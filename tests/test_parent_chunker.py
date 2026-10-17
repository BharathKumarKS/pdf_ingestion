"""Tests for ``src/pdf_ingestion/parent_chunker.py`` (E2 — Docling parents + page provenance).

The page-map logic is pinned offline with lightweight fakes — no Docling, no parse — because
the interesting behaviour is the translation from Docling's per-element ``prov`` charspans to
character offsets in the serialised chunk text. One ``slow`` test runs the real converter
against ``data/base_textbooks/test_book.pdf`` and is the plan's Step 2 verification.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.config import Settings
from src.pdf_ingestion.models import ParentChunk
from src.pdf_ingestion.parent_chunker import ParentChunker, _build_page_map

TEST_BOOK = (
    Path(__file__).resolve().parents[1] / "data" / "base_textbooks" / "test_book.pdf"
)


# ── Fakes: just enough of DocChunk / DocItem / ProvenanceItem ────────────────

def _prov(page_no: int, charspan: tuple[int, int]) -> SimpleNamespace:
    return SimpleNamespace(page_no=page_no, charspan=charspan)


def _item(ref: str, *provs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(self_ref=ref, prov=list(provs))


def _chunk(text: str, *items: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(text=text, meta=SimpleNamespace(doc_items=list(items)))


# ── Page map ────────────────────────────────────────────────────────────────

def test_page_map_records_a_boundary_at_each_element():
    text = "AlphaBetaGamma"
    chunk = _chunk(
        text,
        _item("#/a", _prov(1, (0, 5))),
        _item("#/b", _prov(2, (0, 4))),
        _item("#/c", _prov(2, (0, 5))),
    )
    page_map = _build_page_map(chunk, {"#/a": "Alpha", "#/b": "Beta", "#/c": "Gamma"})
    assert page_map == {0: 1, 5: 2, 9: 2}


def test_page_map_splits_one_element_across_a_page_break():
    """An element crossing pages carries one prov entry per page — charspan is per-element."""
    text = "ABCDEFGHIJ"
    chunk = _chunk(text, _item("#/x", _prov(1, (0, 3)), _prov(2, (3, 10))))
    page_map = _build_page_map(chunk, {"#/x": text})
    assert page_map == {0: 1, 3: 2}


def test_formula_element_without_text_still_contributes_its_page():
    """Formula items have no text but do have provenance — place them at the cursor."""
    text = "Intro[FORMULA]End"
    chunk = _chunk(
        text,
        _item("#/1", _prov(1, (0, 5))),
        _item("#/f", _prov(2, (0, 20))),   # text=None in the real document
        _item("#/3", _prov(3, (0, 3))),
    )
    page_map = _build_page_map(chunk, {"#/1": "Intro", "#/3": "End"})
    assert page_map == {0: 1, 5: 2, 14: 3}


def test_page_map_anchors_offset_zero_when_no_element_claims_it():
    chunk = _chunk("...tail", _item("#/x", _prov(7, (0, 4))))
    page_map = _build_page_map(chunk, {"#/x": "tail"})
    assert page_map[0] == 7


def test_page_map_is_empty_for_an_element_less_chunk():
    assert _build_page_map(_chunk("", ), {}) == {}


# ── ParentChunk contract ────────────────────────────────────────────────────

def test_page_for_offset_returns_the_last_boundary_at_or_before():
    parent = ParentChunk(parent_id=0, text="0123456789", page_map={0: 1, 5: 2})
    assert parent.page_for_offset(0) == 1
    assert parent.page_for_offset(4) == 1
    assert parent.page_for_offset(5) == 2
    assert parent.page_for_offset(999) == 2


def test_page_for_offset_is_none_without_a_map():
    assert ParentChunk(parent_id=0, text="x").page_for_offset(0) is None


def test_page_numbers_are_sorted_and_deduplicated():
    parent = ParentChunk(parent_id=0, text="x", page_map={0: 3, 5: 1, 9: 3})
    assert parent.page_numbers == [1, 3]


# ── Converter wiring ────────────────────────────────────────────────────────

def test_missing_file_raises_before_any_docling_work():
    with pytest.raises(FileNotFoundError, match="PDF not found"):
        ParentChunker(settings=Settings()).convert("/nonexistent/file.pdf")


# ── The Step 2 verification (real Docling parse; slow) ──────────────────────

@pytest.mark.slow
def test_convert_test_book_parents_carry_pages():
    """test_book.pdf → 42 parents, every one with ≥1 in-range page and a heading stack.

    The plan's Step 2 says 43; that figure was measured with Docling's *default* chunker
    (``max_tokens=512``). At the configured ``parent_max_tokens=5000`` the count is **42**
    (verified Docling 2.117, 2026-10-17).
    """
    doc, parents = ParentChunker(settings=Settings()).convert(str(TEST_BOOK))

    assert len(parents) == 42
    assert [p.parent_id for p in parents] == list(range(42))
    assert all(p.text.strip() for p in parents)

    page_count = len(doc.pages)
    for parent in parents:
        assert parent.page_numbers, f"parent {parent.parent_id} has no page"
        assert min(parent.page_numbers) >= 1
        assert max(parent.page_numbers) <= page_count
        assert parent.page_for_offset(0) is not None

    assert any(p.headings for p in parents)          # heading hierarchy survives
    assert parents[0].headings == ["Newton's Three Laws"]
