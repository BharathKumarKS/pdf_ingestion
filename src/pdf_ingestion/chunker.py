"""Topic-coherent semantic chunking (chonkie ``SemanticChunker``), parent-aware — E1.

This replaces the size-based ``chonkie.SentenceChunker`` (chunk_size / chunk_overlap) that
cut mid-thought: *"…Now we would like to sho"*. ``SemanticChunker`` splits where the
similarity between neighbouring sentence windows drops, so a child is a complete claim
(measured on the same text: 12 size-based chunks → 19 semantic ones, avg 436 → 261 chars).

One entry point: :meth:`SemanticChunker.chunk_parents` — children are cut **inside each
Docling parent**, so a child never crosses a section boundary, and it carries the parent's
id and text plus a page number read from the parent's provenance map (§D4).

The flat full-text path (``chunk_document`` / ``build_page_map`` / ``_page_for_offset``) was
removed in Step 7 with the rewire of ``store.ingest_pdf`` to the parent-aware pipeline: it
had no parent context, and its page numbers were off by 0/−1 on ~45% of pages (§D4).

The segmentation embedding model is chonkie's default (``minishlab/potion-base-32M``, a local
static model — cached, no network, no cluster round-trip). It scores sentence-to-sentence
similarity during *segmentation* only; the vectors that are actually indexed come from the
cluster dense embedder (``cluster_embedder.py``, R2). Keeping the two separate is deliberate:
segmenting a 968-page book through the cluster would be one HTTP call per sentence window.

``char_start`` / ``char_end`` are relative to the enclosing parent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Optional

from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion import content_filter
from src.pdf_ingestion.models import ParentChunk


# ── Data contract ─────────────────────────────────────────────────────────

@dataclass
class TextChunk:
    chunk_id: str
    document_id: str
    tenant_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int
    page_number: Optional[int]
    # E2/E1 hierarchy. Defaulted so the existing call sites (card_generator, embedder,
    # store, tests) keep constructing TextChunk unchanged.
    parent_id: Optional[int] = None
    parent_text: Optional[str] = None
    # E5 — front/back-matter classification, set at ingest in Step 5. Defaults to content.
    is_content: bool = True


# ── Chunker ───────────────────────────────────────────────────────────────

class SemanticChunker:
    """Chonkie ``SemanticChunker``: topic-coherent children, optionally inside parents.

    Micro-chunks below ``min_chunk_tokens`` are merged into the preceding chunk rather than
    dropped (and never across a parent boundary).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._chunker = None

    def _get_chunker(self):
        if self._chunker is None:
            from chonkie import SemanticChunker as ChonkieSemanticChunker

            self._chunker = ChonkieSemanticChunker(
                threshold=self._cfg.semantic_threshold,
                chunk_size=self._cfg.chunk_size,
            )
            logger.info(
                "chonkie SemanticChunker ready (threshold={}, chunk_size={})",
                self._cfg.semantic_threshold,
                self._cfg.chunk_size,
            )
        return self._chunker

    # -- E1/E2: children inside parents ----------------------------------------

    def chunk_parents(
        self,
        document_id: str,
        tenant_id: str,
        parents: list[ParentChunk],
    ) -> list[TextChunk]:
        """Cut every parent into semantic children, in order, with parent context attached.

        ``chunk_index`` is global across the document; ``char_start``/``char_end`` are
        relative to the child's own parent.
        """
        chunks: list[TextChunk] = []
        for parent in parents:
            chunks.extend(
                self._chunk_one_parent(document_id, tenant_id, parent, len(chunks))
            )
        logger.success(
            "Chunked document {} → {} children from {} parents",
            document_id, len(chunks), len(parents),
        )
        return chunks

    def _chunk_one_parent(
        self,
        document_id: str,
        tenant_id: str,
        parent: ParentChunk,
        offset: int,
    ) -> list[TextChunk]:
        if not parent.text.strip():
            logger.warning("Empty parent text (parent_id={})", parent.parent_id)
            return []

        out: list[TextChunk] = []
        for raw in self._get_chunker().chunk(parent.text):
            text = raw.text.strip()
            if not text:
                continue

            token_count = getattr(raw, "token_count", len(text.split()))
            char_start = getattr(raw, "start_index", 0)
            char_end = getattr(raw, "end_index", char_start + len(text))

            if token_count < self._cfg.min_chunk_tokens and out:
                # Merge into the previous child of the SAME parent, so no child ever spans
                # two parents. ``page_number`` is deliberately left as the previous child's:
                # it is the page of the merged child's START, which is the convention every
                # page_number in this codebase follows (it is derived from char_start).
                prev = out[-1]
                out[-1] = replace(
                    prev,
                    text=prev.text + " " + text,
                    char_end=char_end,
                    token_count=prev.token_count + token_count,
                )
                continue

            out.append(
                TextChunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    tenant_id=tenant_id,
                    chunk_index=offset + len(out),
                    text=text,
                    char_start=char_start,
                    char_end=char_end,
                    token_count=token_count,
                    page_number=parent.page_for_offset(char_start),
                    parent_id=parent.parent_id,
                    parent_text=parent.text,
                    is_content=content_filter.is_content(text),
                )
            )
        return out

