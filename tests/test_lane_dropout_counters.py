"""§I96 extended — the DA, RAPTOR and GRAPH lanes can also drop out SILENTLY; each is now COUNTED.

The ColBERT lane got its counter first (it cost T4's first full run G6/G6b on one query). The same
class of silent degradation sits on three more lanes:

  * `store.search_da`      catches and returns []   (DA lane)      -> `store.da_dropouts`
  * `store.search_raptor`  the CALLER catches       (overview lane) -> `store.raptor_dropouts`
                                     (counted AND re-raised, so caller behaviour is unchanged)
  * `GraphBuilder.graph_search` catches and returns [] (multihop lane) -> `builder.graph_dropouts`
  * `store._qdrant_search` the SPLADE Prefetch is omitted on failure (sparse lane) -> `store.sparse_dropouts`

Each test drives the REAL swallow point with the failure forced, and each has a negative control
(success -> the counter must NOT move). Deleting the corresponding `+= 1` reddens exactly its own
test — that is the mutation the log records.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np


class _RaisingQdrant:
    """A Qdrant client whose query_points always fails (the lane is down)."""

    def __init__(self):
        self.calls = 0

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
            vectors={"dense_full": object(), "dense_64": object()})))

    def query_points(self, **kw):
        self.calls += 1
        raise RuntimeError("lane endpoint unreachable")

    def close(self):
        pass


class _OkQdrant(_RaisingQdrant):
    def query_points(self, **kw):
        self.calls += 1
        return SimpleNamespace(points=[SimpleNamespace(id=1, score=0.9, payload={"chunk_id": "c1"})])


def _store(settings, fake):
    from src.pdf_ingestion.store import DocumentStore
    s = DocumentStore(settings.model_copy(update={"da_enabled": True}))
    s._qdrant = fake
    return s


# ── DA lane ──────────────────────────────────────────────────────────────────

def test_da_failure_increments_the_counter(settings):
    s = _store(settings, _RaisingQdrant())
    out = s.search_da(np.ones(768, dtype=np.float32), tenant_id="global", limit=5)
    assert out == []
    assert s.da_dropouts == 1, "the DA lane was skipped with no counter"
    assert s.last_da_dropout and "unreachable" in s.last_da_dropout


def test_da_success_does_not_increment(settings):
    s = _store(settings, _OkQdrant())
    out = s.search_da(np.ones(768, dtype=np.float32), tenant_id="global", limit=5)
    assert len(out) == 1
    assert s.da_dropouts == 0


# ── RAPTOR lane ──────────────────────────────────────────────────────────────

def test_raptor_failure_increments_and_re_raises(settings):
    s = _store(settings, _RaisingQdrant())
    raised = False
    try:
        s.search_raptor(np.ones(768, dtype=np.float32), tenant_id="global")
    except Exception:
        raised = True
    assert raised, "search_raptor must RE-RAISE (caller behaviour unchanged)"
    assert s.raptor_dropouts == 1, "the RAPTOR lane failed with no counter"
    assert s.last_raptor_dropout and "unreachable" in s.last_raptor_dropout


def test_raptor_success_does_not_increment(settings):
    s = _store(settings, _OkQdrant())
    out = s.search_raptor(np.ones(768, dtype=np.float32), tenant_id="global")
    assert len(out) == 1
    assert s.raptor_dropouts == 0


# ── graph lane ───────────────────────────────────────────────────────────────

def test_graph_failure_increments_the_counter(settings):
    from src.pdf_ingestion.graph_builder import GraphBuilder
    g = GraphBuilder(settings)

    def _boom():
        raise RuntimeError("memgraph unreachable")
    g._get_driver = _boom

    out = g.graph_search("why is entropy irreversible", tenant_id="global")
    assert out == []
    assert g.graph_dropouts == 1, "the graph lane returned [] with no counter"
    assert g.last_graph_dropout and "unreachable" in g.last_graph_dropout


# ── SPLADE (sparse) lane ──────────────────────────────────────────────────────
#
# The sparse lane is the fourth §I96 swallow point, and the one that is DOWN on the cluster as of
# 2026-11-05: its `except` omits the sparse `Prefetch`, so the RRF fusion silently runs over a
# reduced lane set. The sparse embedder is reached through `get_splade_embedder`, so forcing that
# getter to raise drives the REAL swallow point without a live cluster.


class _FunnelQdrant:
    """A named-vector collection + records every ``query_points`` call (for the fusion funnel)."""

    def __init__(self):
        self.calls: list[dict] = []

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
            vectors={"dense_64": object(), "dense_full": object()})))

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])

    def close(self):
        pass


def _run_sparse_funnel(settings, monkeypatch, *, sparse_raises: bool):
    """Drive ``_qdrant_search`` once with the sparse lane on; return (store, recorded calls)."""
    from src.pdf_ingestion import splade_embedder as _se
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={"splade_enabled": True})

    if sparse_raises:
        def _boom(_cfg):
            raise RuntimeError("sparse endpoint timed out")
        monkeypatch.setattr(_se, "get_splade_embedder", _boom)
    else:
        def _ok(_cfg):
            from src.pdf_ingestion.splade_embedder import SparseVector
            return SimpleNamespace(encode_sparse=lambda _t: SparseVector(
                indices=[1, 2], values=[0.5, 0.5]))
        monkeypatch.setattr(_se, "get_splade_embedder", _ok)

    store = DocumentStore(cfg)
    fake = _FunnelQdrant()
    monkeypatch.setattr(store, "_qdrant", fake)

    store._qdrant_search(
        np.ones(cfg.dense_dim, dtype=np.float32),
        filter_=None,
        limit=cfg.reranker_fetch_k,
        query_text="what is kinetic energy",
    )
    assert fake.calls, "the funnel issued no query_points call"
    return store, fake.calls


def _uses(calls: list[dict]) -> list[str]:
    return [str(c.get("using")) for c in calls]


def test_sparse_failure_increments_the_counter(settings, monkeypatch):
    """THE discriminating test for the sparse lane — a lane-reduced call must be visible, not just logged."""
    store, calls = _run_sparse_funnel(settings, monkeypatch, sparse_raises=True)
    assert store.sparse_dropouts == 1, (
        "the SPLADE failure was swallowed with no counter — a lane-reduced pool is invisible")
    assert store.last_sparse_dropout and "timed out" in store.last_sparse_dropout
    assert "sparse" not in _uses(calls), "the failed lane must not have been queried"


def test_sparse_success_does_not_increment(settings, monkeypatch):
    store, calls = _run_sparse_funnel(settings, monkeypatch, sparse_raises=False)
    assert store.sparse_dropouts == 0
    assert store.last_sparse_dropout is None
    assert "sparse" in _uses(calls), "the healthy path must actually query the lane"


def test_sparse_counter_accumulates_across_queries(settings, monkeypatch):
    """A run's total is the counter; a per-query delta isolates one query's call."""
    from src.pdf_ingestion import splade_embedder as _se
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={"splade_enabled": True})

    def _boom(_cfg):
        raise RuntimeError("sparse endpoint timed out")
    monkeypatch.setattr(_se, "get_splade_embedder", _boom)

    store = DocumentStore(cfg)
    monkeypatch.setattr(store, "_qdrant", _FunnelQdrant())
    for _ in range(3):
        store._qdrant_search(np.ones(cfg.dense_dim, dtype=np.float32),
                             filter_=None, limit=cfg.reranker_fetch_k, query_text="q")
    assert store.sparse_dropouts == 3, "the counter must not reset between queries"


def test_counters_start_at_zero(settings):
    from src.pdf_ingestion.graph_builder import GraphBuilder
    from src.pdf_ingestion.store import DocumentStore
    s = DocumentStore(settings)
    g = GraphBuilder(settings)
    assert (s.da_dropouts, s.raptor_dropouts, s.colbert_dropouts, s.sparse_dropouts) == (0, 0, 0, 0)
    assert s.last_sparse_dropout is None
    assert (g.graph_dropouts, g.last_graph_dropout) == (0, None)
