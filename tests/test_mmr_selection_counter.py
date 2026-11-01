"""`DocumentStore.mmr_selections` — the per-query MMR-fired counter (§I96's class, for MMR).

**Why it exists.** `_mmr_select` returns `top_k` SELECTED candidates, so a query MMR fires on has a
different pool **membership**, not merely a different order. §I99's fusion-order run contrasts the
pool's ORDER, and its G3 asserts that the order-only arm (O1 = `mmr_enabled=False`) has an IDENTICAL
page set to the reference — which is only true on the queries MMR did not fire on. Without this
counter the run cannot tell those queries apart and would assert an invariance it does not have.

The discriminating test is `test_fires_when_deduped_exceeds_fetch_k` — it fails against code that
never increments the counter (the silent-no-op class).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np


def _hits(n_pages: int):
    """`n_pages` hits, one per distinct page — so dedup keeps all of them."""
    return [{"chunk_id": f"c{i}", "page_number": 100 + i, "text": f"t{i}", "score": 1.0}
            for i in range(n_pages)]


def _store(settings, monkeypatch, n_pages: int, fetch_k: int, mmr_enabled: bool = True):
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={"mmr_enabled": mmr_enabled, "da_enabled": False})
    store = DocumentStore(cfg)
    monkeypatch.setattr(store, "search", lambda *a, **k: _hits(n_pages))
    monkeypatch.setattr(store, "search_da", lambda *a, **k: [])
    store.search_with_das(np.ones(cfg.dense_dim, dtype=np.float32),
                          query_text="q", tenant_id="global", fetch_k=fetch_k)
    return store


def test_fires_when_deduped_exceeds_fetch_k(settings, monkeypatch):
    store = _store(settings, monkeypatch, n_pages=30, fetch_k=10)
    assert store.mmr_selections == 1, "MMR fired but the counter did not move"


def test_does_not_fire_when_deduped_is_within_fetch_k(settings, monkeypatch):
    store = _store(settings, monkeypatch, n_pages=5, fetch_k=10)
    assert store.mmr_selections == 0


def test_does_not_fire_when_disabled(settings, monkeypatch):
    store = _store(settings, monkeypatch, n_pages=30, fetch_k=10, mmr_enabled=False)
    assert store.mmr_selections == 0, "the flag is off — MMR must not run and must not be counted"


def test_counter_accumulates_across_calls(settings, monkeypatch):
    """It is a run TOTAL, like `colbert_dropouts`: per-query attribution comes from the delta."""
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={"mmr_enabled": True, "da_enabled": False})
    store = DocumentStore(cfg)
    monkeypatch.setattr(store, "search", lambda *a, **k: _hits(30))
    monkeypatch.setattr(store, "search_da", lambda *a, **k: [])
    for _ in range(3):
        store.search_with_das(np.ones(cfg.dense_dim, dtype=np.float32),
                              query_text="q", tenant_id="global", fetch_k=10)
    assert store.mmr_selections == 3
