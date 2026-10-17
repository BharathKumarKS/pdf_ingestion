"""Data contracts for the re-ingest chunking pipeline (E1/E2/E3).

Mirrors the class repo's ``Labs/Week_6/sv_rag_pipeline/src/svrag/models.py``. ``ParentChunk``
is produced by ``parent_chunker.py`` (E2); the child/enriched contracts arrive with the
semantic chunker (E1) and the late-chunk embedder (E3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParentChunk:
    """A Docling ``HybridChunker`` parent — a section-sized, heading-bounded span.

    ``page_map`` is the §D4 fix: it maps a character offset **in ``text``** to the PDF page
    that character came from, read off Docling's per-element provenance instead of inferred
    from a chunk's start offset (``chunker._page_for_offset``, which is off by 0/−1 on ~45%
    of pages). A parent that crosses a page break carries a boundary entry at the exact
    character where the page changes.
    """

    parent_id: int
    text: str
    headings: list[str] = field(default_factory=list)
    page_map: dict[int, int] = field(default_factory=dict)

    @property
    def page_numbers(self) -> list[int]:
        """PDF pages this parent touches, ascending and de-duplicated."""
        return sorted(set(self.page_map.values()))

    def page_for_offset(self, offset: int) -> Optional[int]:
        """PDF page for a character offset in ``text`` — the last boundary at or before it."""
        page: Optional[int] = None
        for start in sorted(self.page_map):
            if start <= offset:
                page = self.page_map[start]
            else:
                break
        return page
