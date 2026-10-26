"""§I66 — the downstream widths (the fusion output, the re-score cut) are SETTINGS, and the
funnel reads them.

§I66 decomposed the retrieval loss and fingered the **fusion output width** — not the 64d prefetch
(§I61/§I65) and not the full-dimension re-score cut — as the binding constraint: at exact prefetch
the fusion's own loss *grows* (0.143 -> 0.222), because feeding the fusion more candidates does not
grow its output. The product endpoint cannot be tested on that lever unless the widths are config
values (a one-variable A/B, and a revert, rather than a code edit). These tests pin the wiring:

  * the dense funnel's OUTPUT width is ``cfg.mmr_candidates`` (the client-side slice of the fused list);
  * the full-dimension re-score cut is ``cfg.dense_rescore_limit``;
  * the DA lane's depth is its OWN setting ``cfg.da_fetch_k`` — NOT ``fetch_k``;
  * ``reranker_fetch_k`` truncates the pool, so raising ``mmr_candidates`` alone does NOT widen the
    fusion: the two must move together (this is the trap the pre-registration records);
  * nothing else in the funnel scales with any of them.

The discriminating tests are the ones that fail against the old code: with the hardcoded ``500``
the re-score-cut tests fail; with the DA lane reading ``fetch_k`` the decoupling test fails.

⚠️ §I68 CHANGED TWO THINGS THESE TESTS INSPECT. (a) The lanes are now queried individually and fused
client-side with ``store._rrf_merge``, so the DENSE lane is the FIRST call and its re-score cut is
that call's own ``limit`` — no longer ``calls[0]["prefetch"][0].limit``. (b) The fusion's OUTPUT
width is no longer a server-side ``limit``: it is the ``[:limit]`` slice of the merged list, so the
width tests assert on the returned point count.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest


class _CapturingQdrant:
    """Named-vector collection + records every ``query_points`` call.

    ``n_points`` > 0 makes each lane return that many (capped at the lane's own limit) synthetic
    hits, so the client-side fusion has something to merge and the output width is observable.
    """

    def __init__(self, n_points: int = 0):
        self.calls: list[dict] = []
        self._n = n_points

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
            vectors={"dense_64": object(), "dense_1024": object()})))

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        if not self._n:
            return SimpleNamespace(points=[])
        lane = len(self.calls) - 1
        k = min(self._n, kwargs.get("limit") or self._n)
        return SimpleNamespace(points=[
            SimpleNamespace(id=f"p{lane}-{i}", score=1.0 - i * 1e-6,
                            payload={"chunk_id": f"c{lane}-{i}", "page_number": i,
                                     "text": f"passage {lane}-{i}"})
            for i in range(k)])

    def close(self):
        pass


def _run_funnel(settings, monkeypatch, n_points: int = 0, **overrides):
    """Drive ``_qdrant_search`` once; return (cfg, recorded calls, the fused response)."""
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update=overrides) if overrides else settings
    store = DocumentStore(cfg)
    fake = _CapturingQdrant(n_points)
    monkeypatch.setattr(store, "_qdrant", fake)

    resp = store._qdrant_search(
        np.ones(cfg.dense_dim, dtype=np.float32),
        filter_=None,
        limit=cfg.mmr_candidates,
        query_text="what is kinetic energy",
    )
    assert fake.calls, "the funnel issued no query_points call"
    return cfg, fake.calls, resp


def _dense_lane(calls: list[dict]) -> dict:
    """The dense lane is the FIRST call — the only one carrying a nested low->full prefetch."""
    assert calls[0].get("prefetch"), "the dense lane must carry its low-dim inner prefetch"
    return calls[0]


def _inner_prefetch_limit(kwargs: dict) -> int:
    """The 64d lane's own depth — the leaf inside the dense lane's ``prefetch``."""
    return kwargs["prefetch"][0].limit


def _outer_rescore_limit(kwargs: dict) -> int:
    """The dense lane's full-dimension re-score cut — the lane call's own ``limit``."""
    return kwargs["limit"]


def _fake_hits(n: int) -> list[dict]:
    """n hits with distinct pages and descending scores (so dedup keeps them all)."""
    return [{"chunk_id": f"c{i}", "page_number": i, "text": f"passage {i}",
             "score": 1.0 - i * 1e-4} for i in range(n)]


def _run_search_with_das(settings, monkeypatch, **overrides):
    """Drive ``search_with_das`` with a stubbed dense funnel + DA lane; return (cfg, seen)."""
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update=overrides) if overrides else settings
    store = DocumentStore(cfg)
    seen: dict = {}

    def fake_search(_vec, tenant_id=None, limit=10, query_text=None, source_type=None):
        seen["dense_limit"] = limit
        return _fake_hits(limit)

    def fake_da(_vec, tenant_id="global", limit=None):
        seen["da_limit"] = limit
        return []

    monkeypatch.setattr(store, "search", fake_search)
    monkeypatch.setattr(store, "search_da", fake_da)
    out = store.search_with_das(np.ones(cfg.dense_dim, dtype=np.float32), query_text="q")
    return cfg, seen, out


# ── defaults: the shipped values, so the default path is byte-identical ────────

def test_defaults_are_the_shipped_values():
    from src.core.config import Settings

    s = Settings()
    assert s.dense_rescore_limit == 500, "the re-score cut default must be the shipped 500"
    assert s.da_fetch_k == 100, "the DA lane default must be the value it had while coupled"
    assert s.mmr_candidates == 100, "the fusion-output width default must be the shipped 100"
    assert s.reranker_fetch_k == 100, "the pool truncation default must be the shipped 100"


# ── the full-dimension re-score cut is a setting ──────────────────────────────

def test_outer_rescore_cut_is_read_from_config(settings, monkeypatch):
    cfg, calls, _resp = _run_funnel(settings, monkeypatch)
    assert _outer_rescore_limit(_dense_lane(calls)) == cfg.dense_rescore_limit == 500


def test_raising_the_rescore_cut_raises_the_outer_prefetch(settings, monkeypatch):
    """§I66's L-arm: 500 -> 2000 must reach Qdrant. Fails if the value is hardcoded."""
    cfg, calls, _resp = _run_funnel(settings, monkeypatch, dense_rescore_limit=2000)
    assert cfg.dense_rescore_limit == 2000
    assert _outer_rescore_limit(_dense_lane(calls)) == 2000


# ── the fusion output width is mmr_candidates ─────────────────────────────────

def test_dense_funnel_output_width_is_mmr_candidates(settings, monkeypatch):
    """The fused list is sliced to ``cfg.mmr_candidates`` — the RRF fusion's output width."""
    cfg, _calls, resp = _run_funnel(settings, monkeypatch, n_points=1000)
    assert len(resp.points) == cfg.mmr_candidates == 100


def test_raising_mmr_candidates_raises_the_funnel_output(settings, monkeypatch):
    cfg, _calls, resp = _run_funnel(settings, monkeypatch, n_points=1000, mmr_candidates=300)
    assert cfg.mmr_candidates == 300
    assert len(resp.points) == 300


# ── nothing else scales with any of them ──────────────────────────────────────

def test_the_rest_of_the_funnel_is_pinned(settings, monkeypatch):
    """Single-variable: the widths move; the inner lane and depth do not."""
    _cfg, base, base_resp = _run_funnel(settings, monkeypatch, n_points=1000)
    _cfg, raised, raised_resp = _run_funnel(
        settings, monkeypatch, n_points=1000, mmr_candidates=300, dense_rescore_limit=2000)

    for calls in (base, raised):
        dense = _dense_lane(calls)
        assert dense["prefetch"][0].using == "dense_64", "the inner stage must stay the 64d lane"
        assert _inner_prefetch_limit(dense) == settings.dense_prefetch_limit == 1000, \
            "the 64d prefetch depth must not scale with the downstream widths"

    assert _outer_rescore_limit(_dense_lane(base)) == 500
    assert _outer_rescore_limit(_dense_lane(raised)) == 2000
    assert len(base_resp.points) == 100
    assert len(raised_resp.points) == 300


@pytest.mark.parametrize("limit", [500, 1000, 2000])
def test_every_rescore_arm_is_reachable(settings, monkeypatch, limit):
    _cfg, calls, _resp = _run_funnel(settings, monkeypatch, dense_rescore_limit=limit)
    assert _outer_rescore_limit(_dense_lane(calls)) == limit


@pytest.mark.parametrize("width", [100, 300, 500])
def test_every_width_arm_is_reachable(settings, monkeypatch, width):
    _cfg, _calls, resp = _run_funnel(settings, monkeypatch, n_points=1000, mmr_candidates=width)
    assert len(resp.points) == width


# ── the DA lane is decoupled from the fusion width ────────────────────────────

def test_da_lane_depth_is_its_own_setting(settings, monkeypatch):
    cfg, seen, _out = _run_search_with_das(
        settings, monkeypatch, da_enabled=True, da_fetch_k=100, reranker_fetch_k=100)
    assert seen["da_limit"] == cfg.da_fetch_k == 100


def test_raising_the_fusion_width_does_not_move_the_da_lane(settings, monkeypatch):
    """The discriminating test: with the old coupling the DA limit would follow fetch_k to 500."""
    cfg, seen, _out = _run_search_with_das(
        settings, monkeypatch, da_enabled=True, da_fetch_k=100, reranker_fetch_k=500,
        mmr_candidates=500)
    assert seen["da_limit"] == 100, \
        "the DA lane must be pinned by da_fetch_k, not dragged along by the fusion width"


# ── the trap: the two width knobs must move together ──────────────────────────

def test_pool_is_clipped_to_fetch_k_when_only_the_feed_is_widened(settings, monkeypatch):
    """mmr_candidates=500 feeds 500, but reranker_fetch_k=100 truncates the pool back to 100."""
    _cfg, seen, out = _run_search_with_das(
        settings, monkeypatch, da_enabled=False, mmr_candidates=500, reranker_fetch_k=100,
        mmr_enabled=False)
    assert seen["dense_limit"] == 500, "the feed widened"
    assert len(out) == 100, "…but the pool is still clipped to fetch_k"


def test_pool_is_clipped_when_only_the_truncation_is_widened(settings, monkeypatch):
    """fetch_k=500 with mmr_candidates=100: the feed only ever offers 100, so the pool is 100."""
    _cfg, seen, out = _run_search_with_das(
        settings, monkeypatch, da_enabled=False, mmr_candidates=100, reranker_fetch_k=500,
        mmr_enabled=False)
    assert seen["dense_limit"] == 100, "the feed did not widen"
    assert len(out) == 100, "the pool cannot exceed what the feed offered"


def test_both_width_knobs_together_widen_the_pool(settings, monkeypatch):
    """W on both = the actual §I66 lever: a wider fusion output."""
    _cfg, seen, out = _run_search_with_das(
        settings, monkeypatch, da_enabled=False, mmr_candidates=500, reranker_fetch_k=500,
        mmr_enabled=False)
    assert seen["dense_limit"] == 500
    assert len(out) == 500
