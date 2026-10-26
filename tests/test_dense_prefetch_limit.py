"""§I61 — the 64d dense prefetch depth is a SETTING, and the funnel reads it.

The dense funnel is ``[dense_64(prefetch) -> dense_dim(rescore, 500)]`` in
``store._qdrant_search``. The inner prefetch depth was a hardcoded ``1000``; §I61 measured that
this — not the MRL width — is what loses pool coverage on the filtered HNSW path, and that raising
it recovers the loss. The raise is only a one-variable A/B (and a revert) if the depth is a
config value, so these tests pin the wiring:

  * the inner prefetch depth is ``cfg.dense_prefetch_limit``, and
  * everything else in the funnel is untouched by it (the outer re-score limit stays 500, and the
    inner prefetch is still the 64d lane).

The discriminating test is the second one: with the old hardcoded ``1000`` it fails, because
setting the field changes nothing.

⚠️ §I68 CHANGED THE CALL SHAPE these tests inspect. The funnel used to fuse the live lanes in ONE
server-side ``query_points(query=FusionQuery(fusion=Fusion.RRF))`` call; it now queries each lane
individually and fuses them client-side with ``store._rrf_merge`` (Qdrant's server-side RRF was
measured non-deterministic — the same query returned a different fused set on consecutive calls).
So the DENSE lane is the FIRST call, and its inner 64d stage is the leaf
``calls[0]["prefetch"][0]`` — no longer ``calls[0]["prefetch"][0].prefetch[0]``.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest


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


def _run_funnel(settings, monkeypatch, **overrides):
    """Drive ``_qdrant_search`` once and return the recorded ``query_points`` calls."""
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update=overrides) if overrides else settings
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
    return cfg, fake.calls


def _dense_lane(calls: list[dict]) -> dict:
    """The dense lane is the FIRST call — the only one carrying a nested low->full prefetch."""
    assert calls[0].get("prefetch"), "the dense lane must carry its low-dim inner prefetch"
    return calls[0]


def _inner_prefetch_limit(kwargs: dict) -> int:
    """The 64d lane's own depth — the leaf inside the dense lane's ``prefetch``."""
    return kwargs["prefetch"][0].limit


def test_default_prefetch_limit_is_the_shipped_1000():
    """The default must stay the value production ran with until the A/B says otherwise."""
    from src.core.config import Settings

    assert Settings().dense_prefetch_limit == 1000


def test_inner_prefetch_limit_is_read_from_config(settings, monkeypatch):
    """The shipped default path: the 64d prefetch depth is the configured value."""
    cfg, calls = _run_funnel(settings, monkeypatch)
    assert _inner_prefetch_limit(_dense_lane(calls)) == cfg.dense_prefetch_limit == 1000


def test_raising_the_setting_raises_the_prefetch_limit(settings, monkeypatch):
    """§I61's treatment arm: 1000 -> 2000 must reach Qdrant. Fails if the value is hardcoded."""
    cfg, calls = _run_funnel(settings, monkeypatch, dense_prefetch_limit=2000)
    assert cfg.dense_prefetch_limit == 2000
    assert _inner_prefetch_limit(_dense_lane(calls)) == 2000


def test_the_rest_of_the_funnel_is_pinned(settings, monkeypatch):
    """Single-variable: only the inner depth moves; the outer re-score cut and lanes stay fixed."""
    _cfg, base = _run_funnel(settings, monkeypatch)
    _cfg, raised = _run_funnel(settings, monkeypatch, dense_prefetch_limit=2000)

    for calls in (base, raised):
        dense = _dense_lane(calls)
        assert dense["limit"] == 500, "the full-dim re-score cut must not scale with the prefetch"
        assert dense["prefetch"][0].using == "dense_64", "the inner stage must stay the 64d lane"
        assert dense["using"] == "dense_1024", "the dense lane's outer vector is the full dim"

    # …and nothing but that one number differs between the two arms.
    assert _inner_prefetch_limit(_dense_lane(base)) == 1000
    assert _inner_prefetch_limit(_dense_lane(raised)) == 2000


@pytest.mark.parametrize("limit", [1000, 1500, 2000, 3489])
def test_every_arm_of_the_sweep_is_reachable(settings, monkeypatch, limit):
    """The A/B sweeps {1000, 1500, 2000, every in-window chunk} — all must be settable."""
    _cfg, calls = _run_funnel(settings, monkeypatch, dense_prefetch_limit=limit)
    assert _inner_prefetch_limit(_dense_lane(calls)) == limit


def test_the_funnel_queries_each_lane_separately(settings, monkeypatch):
    """§I68 — the lanes are queried individually and fused client-side, NOT by Qdrant's FusionQuery.

    Splade is on and ColBERT is skipped (local Qdrant), so the funnel issues exactly TWO lane
    queries: the dense lane (a nested low->full prefetch) and the sparse lane (a leaf). A regression
    that puts the fusion back on the server would collapse these into a single call.
    """
    _cfg, calls = _run_funnel(settings, monkeypatch)
    assert len(calls) == 2, "dense + sparse are two separate lane queries"
    assert calls[0].get("prefetch"), "the dense lane carries the nested low->full prefetch"
    assert calls[1].get("prefetch") is None, "the sparse lane is a leaf — no inner prefetch"
    assert calls[1]["using"] == "sparse"
