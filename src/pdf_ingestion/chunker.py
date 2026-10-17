"""Topic-coherent semantic chunking (chonkie ``SemanticChunker``), parent-aware — E1.

This replaces the size-based ``chonkie.SentenceChunker`` (chunk_size / chunk_overlap) that
cut mid-thought: *"…Now we would like to sho"*. ``SemanticChunker`` splits where the
similarity between neighbouring sentence windows drops, so a child is a complete claim
(measured on the same text: 12 size-based chunks → 19 semantic ones, avg 436 → 261 chars).

Two entry points:

* :meth:`SemanticChunker.chunk_parents` — the E1/E2 path. Children are cut **inside each
  Docling parent**, so a child never crosses a section boundary, and it carries the parent's
  id and text plus a page number read from the parent's provenance map (§D4).
* :meth:`SemanticChunker.chunk_document` — the flat full-text path, kept for the current
  ``store.py`` ingest call site until Step 7 rewires it. It uses the same semantic chunker;
  only the parent context is absent (``parent_id`` / ``parent_text`` stay ``None``).

The segmentation embedding model is chonkie's default (``minishlab/potion-base-32M``, a local
static model — cached, no network, no cluster round-trip). It scores sentence-to-sentence
similarity during *segmentation* only; the vectors that are actually indexed come from the
cluster dense embedder (``cluster_embedder.py``, R2). Keeping the two separate is deliberate:
segmenting a 968-page book through the cluster would be one HTTP call per sentence window.

``char_start`` / ``char_end`` are relative to the enclosing text — the parent in
``chunk_parents``, the full document in ``chunk_document``. A child's ``page_number`` comes
from the parent's provenance char→page map, not from ``_page_for_offset`` (which stays only
for the legacy flat path; §D4 is closed out in Step 6).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Optional

from loguru import logger

from src.core.config import Settings, get_settings
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
                    is_content=True,
                )
            )
        return out

    # -- Legacy flat path (store.py until Step 7) ------------------------------

    def chunk_document(
        self,
        document_id: str,
        tenant_id: str,
        full_text: str,
        page_map: dict[int, int] | None = None,
    ) -> list[TextChunk]:
        """
        Chunk ``full_text`` into spans, without parent context.

        Args:
            document_id: Parent document UUID.
            tenant_id:   "global" or user id.
            full_text:   Raw text from the parser (markdown-formatted).
            page_map:    char_offset → page_number mapping for page attribution.
                         If None, page_number is left as None.

        Returns:
            Ordered list of TextChunk with char spans relative to ``full_text``.
        """
        if not full_text.strip():
            logger.warning("Empty document text for {}", document_id)
            return []

        chunks: list[TextChunk] = []
        for raw in self._get_chunker().chunk(full_text):
            text = raw.text.strip()
            if not text:
                continue

            token_count = getattr(raw, "token_count", len(text.split()))
            char_start = getattr(raw, "start_index", 0)
            char_end = getattr(raw, "end_index", char_start + len(text))

            if token_count < self._cfg.min_chunk_tokens and chunks:
                # Merge micro-chunks into the previous chunk rather than dropping
                prev = chunks[-1]
                chunks[-1] = replace(
                    prev,
                    text=prev.text + " " + text,
                    char_end=char_end,
                    token_count=prev.token_count + token_count,
                )
                continue
            # No previous chunk: promote the micro-chunk rather than drop it

            chunks.append(
                TextChunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    tenant_id=tenant_id,
                    chunk_index=len(chunks),
                    text=text,
                    char_start=char_start,
                    char_end=char_end,
                    token_count=token_count,
                    page_number=_page_for_offset(char_start, page_map) if page_map else None,
                )
            )

        logger.success(
            "Chunked document {} → {} chunks (min_tokens={})",
            document_id, len(chunks), self._cfg.min_chunk_tokens,
        )
        return chunks

    def build_page_map(
        self, full_text: str, pages: list
    ) -> dict[int, int]:
        """
        Build a char_offset → page_number lookup by searching for each
        page's text within the concatenated full_text.
        """
        page_map: dict[int, int] = {}
        cursor = 0
        for page in pages:
            if not page.text:
                continue
            pos = full_text.find(page.text[:100], cursor)
            if pos != -1:
                page_map[pos] = page.page_number
                cursor = pos + max(len(page.text[:100]), 1)
        return page_map


def _page_for_offset(char_offset: int, page_map: dict[int, int]) -> Optional[int]:
    """Return the page number for a character offset using the page_map."""
    page_num = None
    for offset, pg in sorted(page_map.items()):
        if char_offset >= offset:
            page_num = pg
        else:
            break
    return page_num
