"""Tests for the E1 semantic chunker (``src/pdf_ingestion/chunker.py``).

Two layers:

* the **contract** of the parent-aware path — children are parent-relative, tile their parent
  exactly, never cross a parent boundary, carry the parent's id/text, and take their page
  number from the parent's provenance map. These use synthetic parents and are asserted
  model-independently (only the *shape* of chonkie's output is relied on, not where it cuts).
* one ``slow`` test over the real ``test_book.pdf`` parents.

Note: these load chonkie's default segmentation model (``minishlab/potion-base-32M``), which is
cached locally after the first run — the same footing as the Docling model loads the existing
Phase-1 tests already trigger.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings
from src.pdf_ingestion.chunker import SemanticChunker
from src.pdf_ingestion.models import ParentChunk
from src.pdf_ingestion.parent_chunker import ParentChunker

TEST_BOOK = (
    Path(__file__).resolve().parents[1] / "data" / "base_textbooks" / "test_book.pdf"
)

# Two alternating sentences — chonkie cuts this into several children (verified 2026-10-17).
PROSE = (
    "The normal force is an object's resistance to things going through it. "
    "Friction opposes motion and depends on the surfaces in contact. "
) * 6


def _cfg(**over) -> Settings:
    # min_chunk_tokens=0 by default: these tests pin the *structure* of chonkie's output, and
    # the production default (32) would merge the smaller semantic children together. The
    # merge behaviour itself is pinned by its own test below.
    base: dict = dict(semantic_threshold=0.8, chunk_size=512, min_chunk_tokens=0)
    base.update(over)
    return Settings(**base)


def _parent(pid: int, text: str, page_map: dict[int, int] | None = None) -> ParentChunk:
    return ParentChunk(parent_id=pid, text=text, page_map=page_map or {0: 1})


# ── Contract: spans are parent-relative and tile the parent ──────────────────

def test_children_tile_their_parent():
    parent = _parent(0, PROSE)
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", [parent])

    assert len(children) > 1                       # semantic chunking does split this text
    assert children[0].char_start == 0
    assert children[-1].char_end == len(parent.text)
    for child in children:
        assert parent.text[child.char_start:child.char_end].strip() == child.text
    # contiguous — no gaps, no overlaps
    assert all(
        children[i].char_end == children[i + 1].char_start
        for i in range(len(children) - 1)
    )


def test_no_child_crosses_a_parent_boundary():
    parents = [_parent(0, PROSE), _parent(1, PROSE[:400]), _parent(2, PROSE[:200])]
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", parents)

    by_parent = {p.parent_id: p for p in parents}
    for child in children:
        owner = by_parent[child.parent_id]
        assert child.char_end <= len(owner.text)
        assert child.text in owner.text
    # parents are processed in order, so parent_id is non-decreasing
    ids = [c.parent_id for c in children]
    assert ids == sorted(ids)


def test_children_carry_parent_context():
    parent = _parent(7, PROSE)
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", [parent])
    assert all(c.parent_id == 7 for c in children)
    assert all(c.parent_text == PROSE for c in children)
    assert all(c.is_content is True for c in children)   # prose parent → content (E5)


def test_chunk_index_is_global_and_sequential():
    parents = [_parent(0, PROSE), _parent(1, PROSE[:400]), _parent(2, PROSE[:200])]
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", parents)
    assert [c.chunk_index for c in children] == list(range(len(children)))


def test_page_number_comes_from_the_parent_provenance_map():
    # A boundary at char 400, so the children that start at/after it must report page 2.
    parent = _parent(0, PROSE, page_map={0: 1, 400: 2})
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", [parent])

    for child in children:
        assert child.page_number == parent.page_for_offset(child.char_start)
    assert {c.page_number for c in children} == {1, 2}


def test_micro_chunks_merge_into_the_previous_child_of_the_same_parent():
    # min_chunk_tokens above any child's size forces every child to merge forwards.
    parents = [_parent(0, PROSE), _parent(1, PROSE[:400])]
    children = SemanticChunker(_cfg(min_chunk_tokens=10_000)).chunk_parents(
        "doc", "global", parents
    )

    assert [c.parent_id for c in children] == [0, 1]      # one merged child per parent
    assert len(children) == 2
    assert children[0].char_end == len(parents[0].text)   # merged child spans the parent


def test_empty_parent_is_skipped():
    parents = [_parent(0, "   "), _parent(1, PROSE[:400])]
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", parents)
    assert children
    assert all(c.parent_id == 1 for c in children)


# ── Real document (slow) ────────────────────────────────────────────────────

@pytest.mark.slow
def test_test_book_parents_yield_children_with_pages():
    doc, parents = ParentChunker(_cfg()).convert(str(TEST_BOOK))
    children = SemanticChunker(_cfg()).chunk_parents("doc", "global", parents)

    assert len(children) > len(parents)              # semantic chunking splits parents
    assert [c.chunk_index for c in children] == list(range(len(children)))

    by_parent = {p.parent_id: p for p in parents}
    for child in children:
        owner = by_parent[child.parent_id]
        assert child.text in owner.text
        assert child.char_end <= len(owner.text)
        assert child.parent_text == owner.text
        assert child.page_number is not None
        assert 1 <= child.page_number <= len(doc.pages)
