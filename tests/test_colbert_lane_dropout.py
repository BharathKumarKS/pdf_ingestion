"""§I96 — the ColBERT lane can drop out SILENTLY and change the pool; it is now COUNTED.

``store._qdrant_search`` wraps the ColBERT query in a ``try``; on ANY exception it logs an ERROR
and simply OMITS the ColBERT ``Prefetch``, so the RRF fusion runs over **dense + SPLADE only**.
The lane set is an input to the fusion, so a dropout changes which chunks are shortlisted, hence
which PAGES come back, hence every pool-dependent number — and before this counter, nothing
outside the log text could see it (it cost T4's first full run G6/G6b on one query, 1/665).

These tests pin the counter the way ``reranker.fallbacks`` is pinned (§I55): the failure is
counted, the counter accumulates across queries, and it does NOT fire on the two healthy paths
(a successful ColBERT call, and the file-backed branch where the lane is never attempted).

The discriminating test is ``test_colbert_failure_increments_the_counter``: delete the
``self.colbert_dropouts += 1`` in the ``except`` and it fails on a successful funnel run.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np


class _CapturingQdrant:
    """Named-vector collection + records every ``query_points`` call."""

    def __init__(self):
        self.calls: list[dict] = []

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
            vectors={"dense_64": object(), "dense_1024": object()})))

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])

    def close(self):
        pass


def _run_funnel(settings, monkeypatch, *, colbert_raises: bool, qdrant_host: str | None):
    """Drive ``_qdrant_search`` once; return (store, recorded query_points calls).

    ``qdrant_host`` non-None makes the funnel treat Qdrant as SERVER-backed (``is_local`` False),
    which is the only path on which the ColBERT lane is ever attempted.
    """
    from src.pdf_ingestion import colbert_embedder as _ce
    from src.pdf_ingestion.store import DocumentStore

    overrides: dict = {"colbert_enabled": True}
    if qdrant_host is not None:
        overrides["qdrant_host"] = qdrant_host
    cfg = settings.model_copy(update=overrides)

    if colbert_raises:
        def _boom(_cfg):
            raise RuntimeError("colbert endpoint timed out")
        monkeypatch.setattr(_ce, "get_colbert_embedder", _boom)
    else:
        def _ok(_cfg):
            return SimpleNamespace(
                embed_query=lambda _q: np.zeros((2, 128), dtype=np.float32))
        monkeypatch.setattr(_ce, "get_colbert_embedder", _ok)

    store = DocumentStore(cfg)
    fake = _CapturingQdrant()
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


# ── the counter fires on the swallow ─────────────────────────────────────────

def test_colbert_failure_increments_the_counter(settings, monkeypatch):
    """THE discriminating test — a lane-reduced call must be visible, not just logged."""
    store, calls = _run_funnel(
        settings, monkeypatch, colbert_raises=True, qdrant_host="10.0.10.65")

    assert store.colbert_dropouts == 1, (
        "the ColBERT failure was swallowed with no counter — a lane-reduced pool is invisible")
    assert store.last_colbert_dropout and "timed out" in store.last_colbert_dropout
    assert "colbert" not in _uses(calls), "the failed lane must not have been queried"


def test_the_pool_is_built_from_a_reduced_lane_set_on_dropout(settings, monkeypatch):
    """The point of the counter: on a dropout the fusion sees dense+SPLADE, not all three."""
    _store, dropped = _run_funnel(
        settings, monkeypatch, colbert_raises=True, qdrant_host="10.0.10.65")
    _store2, healthy = _run_funnel(
        settings, monkeypatch, colbert_raises=False, qdrant_host="10.0.10.65")

    assert "colbert" not in _uses(dropped)
    assert "colbert" in _uses(healthy), "the healthy path must actually query the lane"
    assert len(healthy) == len(dropped) + 1, "the dropout removes exactly one lane query"


def test_the_counter_accumulates_across_queries(settings, monkeypatch):
    """A run's total is the counter; a per-query delta is what isolates one query's call."""
    from src.pdf_ingestion import colbert_embedder as _ce
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={"colbert_enabled": True, "qdrant_host": "10.0.10.65"})

    def _boom(_cfg):
        raise RuntimeError("colbert endpoint timed out")
    monkeypatch.setattr(_ce, "get_colbert_embedder", _boom)

    store = DocumentStore(cfg)
    monkeypatch.setattr(store, "_qdrant", _CapturingQdrant())

    for _ in range(3):
        store._qdrant_search(
            np.ones(cfg.dense_dim, dtype=np.float32),
            filter_=None, limit=cfg.reranker_fetch_k, query_text="q")

    assert store.colbert_dropouts == 3, "the counter must not reset between queries"


# ── the two healthy paths must NOT increment ─────────────────────────────────

def test_a_successful_colbert_call_does_not_increment(settings, monkeypatch):
    store, calls = _run_funnel(
        settings, monkeypatch, colbert_raises=False, qdrant_host="10.0.10.65")
    assert store.colbert_dropouts == 0
    assert store.last_colbert_dropout is None
    assert "colbert" in _uses(calls)


def test_file_backed_qdrant_is_not_a_dropout(settings, monkeypatch):
    """The local branch NEVER ATTEMPTS the lane (no Rust MaxSim) — that is not a swallowed failure.

    It is warned about separately (``_warned_colbert_local``); counting it here would make every
    local run look like it had dropped a lane.
    """
    store, calls = _run_funnel(
        settings, monkeypatch, colbert_raises=True, qdrant_host=None)
    assert store.colbert_dropouts == 0, "a never-attempted lane is not a dropout"
    assert store._warned_colbert_local is True
    assert "colbert" not in _uses(calls)


def test_the_counter_starts_at_zero(settings):
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(settings)
    assert store.colbert_dropouts == 0
    assert store.last_colbert_dropout is None
