"""The level-1 lane weights (§I99's fusion-order arm O4) — and the invariant that makes it safe.

`_qdrant_search` fuses the vector lanes (dense / sparse / colbert) with `_rrf_merge`. The fusion-order
arm needs to down-weight a lane WITHOUT removing its candidates, so `_qdrant_search` (and `search`,
`search_with_das`) gained an optional `lane_weights: dict[str, float] | None`.

⚠️ **The load-bearing test is `test_default_path_is_inert`.** The change is on the PRODUCT path, so the
default must be bit-identical to the unweighted call it replaces. `_rrf_merge(weights=None)` expands to
`[1.0] * n`, which is exactly the old call — and this test asserts the two produce identical ids,
identical `rrf_score`s and identical order, so "inert by default" is a measurement and not a claim.

The discriminating test is `test_weights_change_the_order`, which fails if `lane_weights` is accepted
and then ignored (the classic silent no-op).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np


def _cfg_vectors(**sizes):
    return {name: SimpleNamespace(size=size) for name, size in sizes.items()}


class _LaneQdrant:
    """Returns a FIXED per-lane ranking, so the fused order is a pure function of the weights.

    dense   -> [A, B, C]
    sparse  -> [C, A, B]
    colbert -> []      (an empty lane: it contributes nothing, which must not crash the fusion)
    """

    LANES = {"dense_full": ["A", "B", "C"], "sparse": ["C", "A", "B"], "colbert": []}

    def __init__(self, vectors_cfg):
        self._vectors_cfg = vectors_cfg
        self.calls: list[dict] = []

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(
            params=SimpleNamespace(vectors=self._vectors_cfg)))

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        names = self.LANES.get(kwargs.get("using"), [])
        pts = [SimpleNamespace(id=i + 1, score=1.0 - 0.01 * i, payload={"chunk_id": c})
               for i, c in enumerate(names)]
        return SimpleNamespace(points=pts)

    def close(self):
        pass


def _run(settings, monkeypatch, **kw):
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update={
        "qdrant_host": "fake",          # else the ColBERT lane is skipped as "local file Qdrant"
        "splade_enabled": True,
        "colbert_enabled": True,
        "dense_dim": 768,
        "dense_dim_low": 64,
    })
    store = DocumentStore(cfg)
    fake = _LaneQdrant(_cfg_vectors(dense_64=64, dense_full=768))
    monkeypatch.setattr(store, "_qdrant", fake)
    resp = store._qdrant_search(
        np.ones(cfg.dense_dim, dtype=np.float32),
        filter_=None,
        limit=100,
        query_text="what is kinetic energy",
        **kw,
    )
    order = [p.payload["chunk_id"] for p in resp.points]
    scores = {p.payload["chunk_id"]: p.score for p in resp.points}
    return fake, order, scores


def test_all_three_lanes_were_queried(settings, monkeypatch):
    """A guard on the FIXTURE: if the lanes are not all live, the other tests prove nothing."""
    fake, order, _ = _run(settings, monkeypatch)
    used = [c.get("using") for c in fake.calls]
    assert used == ["dense_full", "sparse", "colbert"], f"lanes queried: {used}"
    assert set(order) == {"A", "B", "C"}


def test_default_path_is_inert(settings, monkeypatch):
    """⚠️ THE LOAD-BEARING ONE. `lane_weights=None` must equal not passing it at all."""
    _, order_absent, scores_absent = _run(settings, monkeypatch)
    _, order_none, scores_none = _run(settings, monkeypatch, lane_weights=None)

    assert order_absent == order_none, "the default changed the fused ORDER"
    assert scores_absent == scores_none, "the default changed the fused SCORES"
    # and the default is the unweighted RRF order, computed independently:
    #   A = 1/2 + 1/3, B = 1/3 + 1/4, C = 1/4 + 1/2
    assert order_absent == ["A", "C", "B"], order_absent


def test_weights_change_the_order(settings, monkeypatch):
    """Down-weighting sparse (without removing it) must promote B over C. Fails if ignored."""
    _, order_equal, _ = _run(settings, monkeypatch)
    _, order_weighted, _ = _run(
        settings, monkeypatch, lane_weights={"dense": 1.0, "sparse": 0.1, "colbert": 0.1})

    assert order_equal == ["A", "C", "B"]
    assert order_weighted == ["A", "B", "C"], (
        "lane_weights was accepted but had no effect — a silent no-op")
    # the candidate SET is unchanged: weighting reorders, it does not remove
    assert set(order_weighted) == set(order_equal) == {"A", "B", "C"}


def test_an_unknown_lane_name_defaults_to_one(settings, monkeypatch):
    """A dict that names only one lane must not raise and must leave the others at 1.0."""
    _, order_partial, _ = _run(settings, monkeypatch, lane_weights={"dense": 1.0})
    _, order_none, _ = _run(settings, monkeypatch, lane_weights=None)
    assert order_partial == order_none


def test_rrf_merge_none_equals_omitted(settings):
    """The primitive the whole thing rests on: `weights=None` is `[1.0] * n`."""
    from src.pdf_ingestion.store import DocumentStore

    a = [{"chunk_id": "x"}, {"chunk_id": "y"}]
    b = [{"chunk_id": "y"}, {"chunk_id": "z"}]
    without = DocumentStore._rrf_merge(a, b, rrf_k=1)
    with_none = DocumentStore._rrf_merge(a, b, rrf_k=1, weights=None)
    assert without == with_none
