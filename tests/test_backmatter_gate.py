"""Index-page probe (P0-9 Session 3b).

The judge is an 8B VLM and it is inconsistent on the book's index — it returned NO
on p944 for one question and YES for another, which leaked an index page into the
labels. ``scripts/validate_eval_calibration.py`` therefore caps index/back-matter
pages at PARTIAL *deterministically* (by structure), and ``store.py`` excludes back
matter from retrieval. These tests pin both, with synthetic text so no PDF is needed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load_scanner():
    path = _ROOT / "scripts" / "validate_eval_calibration.py"
    spec = importlib.util.spec_from_file_location("vec_under_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vec = _load_scanner()

_PROSE = "The total energy of the system is conserved in all interactions.\n"
# "Term, <page-ref>" lines — what an index page is made of.
_INDEX = "".join(f"Term {i}, 12-{i} ff\n" for i in range(1, 13))


class _FakeStore:
    """Minimal PageStore stand-in: 1-indexed page texts."""

    def __init__(self, pages: list[str]):
        self._pages = pages
        self.n_pages = len(pages)

    def text(self, page_number: int) -> str:
        return self._pages[page_number - 1]


# ── Structural predicate ─────────────────────────────────────────────────────

def test_is_index_like_flags_index_layout():
    assert vec.is_index_like(_INDEX) is True


def test_is_index_like_ignores_prose():
    assert vec.is_index_like(_PROSE * 12) is False


def test_is_index_like_flags_explicit_heading():
    assert vec.is_index_like("## Index -1\n" + _PROSE * 10) is True


def test_back_matter_start_finds_trailing_run():
    pages = [_PROSE * 12] * 7 + [_INDEX] * 3   # content 1-7, index 8-10
    assert vec.back_matter_start(_FakeStore(pages)) == 8


def test_back_matter_start_ignores_prose_only_book():
    assert vec.back_matter_start(_FakeStore([_PROSE * 12] * 10)) == 11  # nothing gated


# ── Gate: an index YES must be capped, a content YES must not ─────────────────

def test_apply_page_gate_caps_index_yes():
    store = _FakeStore([_PROSE * 12] * 7 + [_INDEX] * 3)
    verdict, reason = vec.apply_page_gate(9, _INDEX, "YES", "mentions it", store)
    assert verdict == "PARTIAL"
    assert "back-matter" in reason


def test_apply_page_gate_leaves_content_yes():
    store = _FakeStore([_PROSE * 12] * 7 + [_INDEX] * 3)
    verdict, _ = vec.apply_page_gate(3, _PROSE * 12, "YES", "answers it", store)
    assert verdict == "YES"


def test_apply_page_gate_does_not_touch_no_or_partial():
    store = _FakeStore([_PROSE * 12] * 7 + [_INDEX] * 3)
    assert vec.apply_page_gate(9, _INDEX, "NO", "x", store)[0] == "NO"
    assert vec.apply_page_gate(9, _INDEX, "PARTIAL", "x", store)[0] == "PARTIAL"


# ── Retrieval: back matter must not come back from search() ──────────────────

class _Hit:
    def __init__(self, point_id, score, payload):
        self.id, self.score, self.payload = point_id, score, payload


class _Resp:
    def __init__(self, points):
        self.points = points


def test_search_excludes_back_matter(settings, monkeypatch):
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={"min_content_page": 30, "max_content_page": 936})
    store = DocumentStore(cfg)

    hits = [
        _Hit(1, 0.9, {"page_number": 100, "source_type": "base_textbook", "text": "content"}),
        _Hit(2, 0.8, {"page_number": 950, "source_type": "base_textbook", "text": "index"}),  # back matter
        _Hit(3, 0.7, {"page_number": 10, "source_type": "base_textbook", "text": "toc"}),     # front matter
    ]
    monkeypatch.setattr(store, "_qdrant_search", lambda **kw: _Resp(hits))

    out = store.search(np.zeros(cfg.embedding_dim, dtype=np.float32), tenant_id="global",
                       source_type="base_textbook", limit=10, query_text="energy")
    pages = [r["page_number"] for r in out]
    assert pages == [100], pages
