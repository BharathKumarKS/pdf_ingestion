"""Unit tests for DocumentStore._score_merge (the 4A score-fusion alternative).

Pins (a) the method's arithmetic on hand-checkable fixtures, (b) the keying fallback that must match
_rrf_merge (a candidate with no chunk_id is never dropped), and (c) that the PRODUCT path
(_rrf_merge) is untouched -- _score_merge is additive and inert unless called.
"""
from __future__ import annotations

import pytest

from src.pdf_ingestion.store import DocumentStore


def _lane(ids_scores):
    return [{"chunk_id": cid, "score": s, "qdrant_point_id": f"p{cid}"} for cid, s in ids_scores]


def test_minmax_is_a_normalised_sum():
    # lane A scores [0, 10]; lane B scores [5, 5] (degenerate range -> contributes 0)
    a = _lane([("a", 0.0), ("b", 10.0)])
    b = _lane([("b", 5.0), ("c", 5.0)])
    merged = DocumentStore._score_merge(a, b, mode="minmax")
    by = {e["chunk_id"]: e["rrf_score"] for e in merged}
    # a: lane A norm 0 -> 0 ; lane B absent
    # b: lane A norm 1 -> 1 ; lane B norm 0 (degenerate) -> 1
    # c: lane B norm 0 -> 0
    assert by["a"] == pytest.approx(0.0)
    assert by["b"] == pytest.approx(1.0)
    assert by["c"] == pytest.approx(0.0)
    # descending by fused score
    assert [e["chunk_id"] for e in merged][0] == "b"


def test_zscore_is_standardised_sum():
    a = _lane([("a", 1.0), ("b", 2.0), ("c", 3.0)])  # mean 2, sd sqrt(2/3)
    merged = DocumentStore._score_merge(a, mode="zscore")
    by = {e["chunk_id"]: e["rrf_score"] for e in merged}
    sd = (2.0 / 3.0) ** 0.5
    assert by["a"] == pytest.approx(-1.0 / sd, abs=1e-6)
    assert by["b"] == pytest.approx(0.0, abs=1e-6)
    assert by["c"] == pytest.approx(1.0 / sd, abs=1e-6)


def test_degenerate_lane_contributes_zero():
    a = _lane([("a", 7.0), ("b", 7.0)])  # max == min
    merged = DocumentStore._score_merge(a, mode="minmax")
    assert all(e["rrf_score"] == 0.0 for e in merged)


def test_missing_chunk_id_falls_back_to_point_id():
    lane = [{"score": 1.0, "qdrant_point_id": "pt-1"}, {"score": 0.0, "qdrant_point_id": "pt-2"}]
    merged = DocumentStore._score_merge(lane, mode="minmax")
    assert {e["qdrant_point_id"] for e in merged} == {"pt-1", "pt-2"}


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        DocumentStore._score_merge(_lane([("a", 1.0)]), mode="nonsense")


def test_weight_length_mismatch_raises():
    with pytest.raises(ValueError):
        DocumentStore._score_merge(_lane([("a", 1.0)]), _lane([("b", 1.0)]), weights=[1.0])


def test_rrf_default_path_is_unchanged_and_distinct_from_score_merge():
    """The product path uses _rrf_merge(rrf_k=1); _score_merge must not be the same behaviour.
    Fixture: RRF ties a and b (each is rank 1 in one lane, rank 2 in the other); the score sum
    separates them, because a is near the top in BOTH lanes while b is not."""
    a = _lane([("a", 0.9), ("b", 0.1), ("c", 0.05)])
    b = _lane([("b", 0.9), ("a", 0.8), ("c", 0.05)])
    rrf = DocumentStore._rrf_merge(a, b, rrf_k=1)
    sm = DocumentStore._score_merge(a, b, mode="minmax")
    rrf_scores = {e["chunk_id"]: e["rrf_score"] for e in rrf}
    sm_scores = {e["chunk_id"]: e["rrf_score"] for e in sm}
    # RRF(rrf_k=1): a and b are both rank 1 once and rank 2 once -> equal
    assert rrf_scores["a"] == pytest.approx(rrf_scores["b"])
    # score fusion: a is top in A and near-top in B; b is the mirror -> a wins
    assert sm_scores["a"] > sm_scores["b"]
