"""
Phase A tests: DA indexing, RRF, MMR, search_with_das.
All use stubs — no model downloads or network calls required.
"""
from __future__ import annotations

import uuid
import numpy as np
import pytest

from src.pdf_ingestion.store import DocumentStore


# ── RRF tests ─────────────────────────────────────────────────────────────────

def test_rrf_merge_single_list():
    items = [
        {"chunk_id": "a", "score": 0.9, "text": "alpha"},
        {"chunk_id": "b", "score": 0.8, "text": "beta"},
    ]
    merged = DocumentStore._rrf_merge(items)
    assert [m["chunk_id"] for m in merged] == ["a", "b"]
    assert all("rrf_score" in m for m in merged)


def test_rrf_merge_two_lists_boosts_overlap():
    list1 = [
        {"chunk_id": "a", "score": 0.9, "text": "alpha"},
        {"chunk_id": "b", "score": 0.5, "text": "beta"},
    ]
    list2 = [
        {"chunk_id": "b", "score": 0.8, "text": "beta"},  # b appears in both
        {"chunk_id": "c", "score": 0.7, "text": "gamma"},
    ]
    merged = DocumentStore._rrf_merge(list1, list2)
    ids = [m["chunk_id"] for m in merged]
    # b appears in both lists → higher RRF score than c (only in list2)
    assert ids.index("b") < ids.index("c")


def test_rrf_merge_empty_list_ignored():
    items = [{"chunk_id": "a", "score": 0.9, "text": "alpha"}]
    merged = DocumentStore._rrf_merge(items, [])
    assert len(merged) == 1
    assert merged[0]["chunk_id"] == "a"


def test_rrf_merge_skips_items_without_chunk_id():
    items = [
        {"chunk_id": "a", "score": 0.9, "text": "alpha"},
        {"score": 0.8, "text": "no chunk id"},  # missing chunk_id
    ]
    merged = DocumentStore._rrf_merge(items)
    assert len(merged) == 1


# ── MMR tests ─────────────────────────────────────────────────────────────────

def _make_candidates(texts: list[str], scores: list[float]) -> list[dict]:
    return [
        {"chunk_id": str(i), "text": t, "rrf_score": s}
        for i, (t, s) in enumerate(zip(texts, scores))
    ]


def test_mmr_returns_top_k():
    candidates = _make_candidates(
        ["physics energy", "energy momentum", "wave frequency", "optics light"],
        [0.9, 0.8, 0.7, 0.6],
    )
    selected = DocumentStore._mmr_select(candidates, top_k=2)
    assert len(selected) == 2


def test_mmr_passthrough_when_fewer_than_top_k():
    candidates = _make_candidates(["alpha", "beta"], [0.9, 0.8])
    selected = DocumentStore._mmr_select(candidates, top_k=5)
    assert len(selected) == 2


def test_mmr_prefers_diverse_over_redundant():
    # Two near-identical chunks and one diverse chunk
    candidates = _make_candidates(
        [
            "kinetic energy equals half mass velocity squared",
            "kinetic energy equals half mass velocity squared formula",  # near-duplicate
            "electromagnetic wave speed in vacuum",                       # diverse
        ],
        [0.9, 0.85, 0.7],
    )
    selected = DocumentStore._mmr_select(candidates, top_k=2, lambda_=0.5)
    ids = [s["chunk_id"] for s in selected]
    # First pick is always highest relevance (chunk 0)
    assert ids[0] == "0"
    # Second pick should prefer the diverse chunk (2) over near-duplicate (1)
    assert ids[1] == "2"


# ── search_with_das integration (stub) ────────────────────────────────────────

@pytest.fixture()
def stub_store(tmp_path, monkeypatch):
    """DocumentStore with stubs and in-memory Qdrant."""
    import os
    monkeypatch.setenv("USE_STUB_EMBEDDER", "true")
    monkeypatch.setenv("USE_STUB_LLM", "true")
    monkeypatch.setenv("USE_STUB_COLPALI", "true")
    monkeypatch.setenv("USE_STUB_GRAPH", "true")
    monkeypatch.setenv("USE_STUB_SPLADE", "true")
    monkeypatch.setenv("USE_STUB_COLBERT", "true")
    monkeypatch.setenv("QDRANT_IN_MEMORY", "true")
    monkeypatch.setenv("SQLITE_URL", f"sqlite:///{tmp_path}/test.db")

    from src.core.config import get_settings
    get_settings.cache_clear()
    from src.core.database import reset_singletons
    reset_singletons()

    cfg = get_settings()
    from src.core.database import get_engine
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(get_engine(cfg))

    store = DocumentStore(cfg)
    yield store

    get_settings.cache_clear()
    reset_singletons()


def test_search_with_das_returns_list(stub_store):
    q_vec = np.random.rand(768).astype(np.float32)
    results = stub_store.search_with_das(q_vec, query_text="kinetic energy", tenant_id="global")
    assert isinstance(results, list)


def test_search_with_das_da_disabled(stub_store, monkeypatch):
    monkeypatch.setattr(stub_store._cfg, "da_enabled", False)
    q_vec = np.random.rand(768).astype(np.float32)
    results = stub_store.search_with_das(q_vec, query_text="test", tenant_id="global")
    assert isinstance(results, list)


def test_resolve_da_parents_empty(stub_store):
    result = stub_store._resolve_da_parents([])
    assert result == []


def test_resolve_da_parents_unknown_chunk(stub_store):
    # DA hit referencing a chunk_id that doesn't exist → silently skipped
    result = stub_store._resolve_da_parents([
        {"chunk_id": "nonexistent-uuid", "score": 0.8, "card_type": "definition", "tenant_id": "global"}
    ])
    assert result == []


# ── Chapter filter (imported from indexing script) ────────────────────────────

def test_chapter_filter_passes_normal_chunk():
    from scripts.index_derivative_artifacts import _is_chapter_chunk
    text = "## 10-1 Conservation of Energy\n\nThe work-energy theorem states that..."
    assert _is_chapter_chunk(text) is True


def test_chapter_filter_blocks_preface():
    from scripts.index_derivative_artifacts import _is_chapter_chunk
    text = "## Preface\n\nThis volume covers the fundamentals of classical mechanics..."
    assert _is_chapter_chunk(text) is False


def test_chapter_filter_blocks_bibliography():
    from scripts.index_derivative_artifacts import _is_chapter_chunk
    text = "## Bibliography\n\nFeynman, R.P. (1963). The Feynman Lectures..."
    assert _is_chapter_chunk(text) is False


def test_chapter_filter_blocks_toc():
    from scripts.index_derivative_artifacts import _is_chapter_chunk
    text = "table of contents\n\nChapter 1 ... 10\nChapter 2 ... 24"
    assert _is_chapter_chunk(text) is False
