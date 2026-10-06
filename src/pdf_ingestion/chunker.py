"""Size-based sentence chunker (Chonkie ``SentenceChunker``) with char-span tracking.

This is **not** semantic chunking. It splits on sentence boundaries to a token budget
(``chunk_size`` / ``chunk_overlap``). Topic-aware splitting would be
``chonkie.SemanticChunker`` — which this project does not use.

Char spans are preserved on every chunk, but nothing currently consumes them for late
chunking: the embedder encodes each chunk in isolation (see ``embedder.py``, "no
late-chunking"). They are kept for page attribution, and as the hook a late-chunking
implementation would need.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from src.core.config import Settings, get_settings


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


# ── Chunker ───────────────────────────────────────────────────────────────

class SemanticChunker:
    """
    Sentence-boundary chunking to a token budget.

    Splits with ``chonkie.SentenceChunker`` (chunk_size / chunk_overlap), then merges
    micro-chunks into the preceding chunk rather than dropping them. There is no second
    semantic pass: an earlier design called for one, but only pass 1 was ever built.

    Preserves char_start / char_end on every chunk. A previous docstring claimed these
    feed "late-chunking windows" through a Jina embedder; that pipeline does not exist
    (the embedder is Nomic and encodes each chunk independently).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._chunker = None

    def _get_chunker(self):
        if self._chunker is None:
            from chonkie import SentenceChunker as ChonkieSentenceChunker
            self._chunker = ChonkieSentenceChunker(
                chunk_size=self._cfg.chunk_size,
                chunk_overlap=self._cfg.chunk_overlap,
                min_sentences_per_chunk=1,
            )
            logger.info(
                "SentenceChunker ready (chunk_size={}, overlap={})",
                self._cfg.chunk_size,
                self._cfg.chunk_overlap,
            )
        return self._chunker

    def chunk_document(
        self,
        document_id: str,
        tenant_id: str,
        full_text: str,
        page_map: dict[int, int] | None = None,
    ) -> list[TextChunk]:
        """
        Chunk ``full_text`` into spans.

        Args:
            document_id: Parent document UUID.
            tenant_id:   "global" or user id.
            full_text:   Raw text from the parser (markdown-formatted).
            page_map:    char_offset → page_number mapping for page attribution.
                         If None, page_number is left as None.

        Returns:
            Ordered list of TextChunk with char spans preserved.
        """
        if not full_text.strip():
            logger.warning("Empty document text for {}", document_id)
            return []

        chunker = self._get_chunker()
        raw_chunks = chunker.chunk(full_text)

        chunks: list[TextChunk] = []
        for idx, rc in enumerate(raw_chunks):
            text = rc.text.strip()
            if not text:
                continue

            token_count = getattr(rc, "token_count", len(text.split()))
            if token_count < self._cfg.min_chunk_tokens:
                # Merge micro-chunks into the previous chunk rather than dropping
                if chunks:
                    prev = chunks[-1]
                    chunks[-1] = TextChunk(
                        chunk_id=prev.chunk_id,
                        document_id=prev.document_id,
                        tenant_id=prev.tenant_id,
                        chunk_index=prev.chunk_index,
                        text=prev.text + " " + text,
                        char_start=prev.char_start,
                        char_end=getattr(rc, "end_index", prev.char_end),
                        token_count=prev.token_count + token_count,
                        page_number=prev.page_number,
                    )
                    continue
                # No previous chunk: promote the micro-chunk rather than drop it

            char_start = getattr(rc, "start_index", 0)
            char_end   = getattr(rc, "end_index",   char_start + len(text))
            page_num   = _page_for_offset(char_start, page_map) if page_map else None

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
                    page_number=page_num,
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
