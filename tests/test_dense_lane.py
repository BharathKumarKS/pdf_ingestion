"""The dense-lane move (§I12 / §I47) — the derived collections and their dimension guard.

`derivative_artifacts` and `concept_embeddings` used to be created at the retired 768d
`embedding_dim` while every query against them carried the dense lane's 1024d, so both lanes
returned nothing on every `evaluate_rag.py` query — silently, as a WARNING per query (§I47).
These tests pin the two halves of the fix that are checkable offline:

  * the collections are now created at ``dense_dim``, and
  * ``_assert_collection_dim`` refuses a stale collection **loudly and with the fix**, instead of
    letting a bare Qdrant 400 be the only symptom.
"""
from __future__ import annotations

import pytest


# ── The collections are created in the dense lane ────────────────────────────

def _vector_size(client, name: int) -> int:
    return int(client.get_collection(name).config.params.vectors.size)


def test_derived_collections_are_created_at_dense_dim(settings):
    """Both derived collections must be `dense_dim`, NOT the legacy `embedding_dim`."""
    from src.core.database import get_qdrant

    cfg = settings
    # The split is the whole point of the test — fail loudly if the fixture stops expressing it.
    assert cfg.embedding_dim != cfg.dense_dim, "fixture no longer models the 768/1024 split"

    client = get_qdrant(cfg)
    for name in (cfg.da_collection, cfg.concept_collection):
        size = _vector_size(client, name)
        assert size == cfg.dense_dim, f"{name} is {size}d, expected dense_dim {cfg.dense_dim}d"
        assert size != cfg.embedding_dim, f"{name} is still on the retired {cfg.embedding_dim}d lane"


# ── The dimension guard ──────────────────────────────────────────────────────

class _FakeQdrant:
    """Returns a configured vector size, or raises when asked."""

    def __init__(self, size=None, error=None):
        self._size, self._error = size, error

    def get_collection(self, _name):
        if self._error is not None:
            raise self._error
        from types import SimpleNamespace
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
            vectors=SimpleNamespace(size=self._size))))

    def close(self):
        pass


def test_guard_passes_when_the_dimension_matches():
    from src.pdf_ingestion.graph_builder import GraphBuilder

    GraphBuilder._assert_collection_dim(_FakeQdrant(size=1024), "concept_embeddings", 1024)


def test_guard_raises_on_a_stale_collection_and_names_the_fix():
    """The defect §I47 hid for a week: 768d collection, 1024d query."""
    from src.pdf_ingestion.graph_builder import GraphBuilder

    with pytest.raises(RuntimeError) as excinfo:
        GraphBuilder._assert_collection_dim(_FakeQdrant(size=768), "concept_embeddings", 1024)

    msg = str(excinfo.value)
    assert "768d" in msg and "1024d" in msg
    # It must tell the operator what to DO, not just what is wrong.
    assert "drop" in msg.lower()
    assert "reset_for_reingest" in msg
    assert "Nothing was written" in msg


def test_guard_is_silent_when_the_collection_is_unreadable():
    """An absent collection (or a named-vector layout) is `ensure_*`'s business, not a failure."""
    from src.pdf_ingestion.graph_builder import GraphBuilder

    GraphBuilder._assert_collection_dim(_FakeQdrant(error=RuntimeError("not found")), "x", 1024)


def test_guard_is_silent_on_a_named_vector_layout():
    """`knowledge_base` is named-vector; `vectors.size` does not exist there."""
    from types import SimpleNamespace

    from src.pdf_ingestion.graph_builder import GraphBuilder

    class _Named:
        def get_collection(self, _n):
            return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
                vectors={"dense_64": object(), "dense_1024": object()})))

    GraphBuilder._assert_collection_dim(_Named(), "knowledge_base", 1024)


# ── The graph build refuses BEFORE the expensive half ────────────────────────

def test_build_graph_checks_the_dimension_before_extracting(settings, monkeypatch):
    """A stale collection must fail at the start, not after hours of concept extraction."""
    from src.pdf_ingestion.graph_builder import GraphBuilder

    cfg = settings.model_copy(update={"use_stub_embedder": False})
    calls = {"extract": 0}

    gb = GraphBuilder(settings=cfg)
    monkeypatch.setattr(gb, "_get_driver", lambda: object())
    monkeypatch.setattr(
        GraphBuilder, "_assert_collection_dim",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stale collection"))),
    )
    monkeypatch.setattr(gb, "_extract_concepts",
                        lambda _t: calls.__setitem__("extract", calls["extract"] + 1))

    class _Chunk:
        id = "c1"
        text = "x"
        page_number = 1
        chunk_index = 0

    with pytest.raises(RuntimeError, match="stale collection"):
        gb.build_graph(document_id="d", tenant_id="global", chunks=[_Chunk()])
    assert calls["extract"] == 0, "extraction ran despite the guard — it is too late to help"
