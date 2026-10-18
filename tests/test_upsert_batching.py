"""Tests for the Qdrant upsert batching rule (``store._iter_upsert_batches``).

Why this exists. The Feynman re-ingest reached the final write and died with:

    400 Bad Request: JSON payload (34769658 bytes) is larger than allowed (limit: 33554432)

The upsert was already batched — at a fixed **128 points**. That was fine until ColBERT was
enabled, because each point then carries a per-token multi-vector (~100 tokens x 128 dims x ~20
bytes of JSON ≈ 270 KB), and 128 of those is ~34.7 MB. So the batch is now bounded by **bytes**,
which is the unit Qdrant's limit is actually expressed in.

Three things have to hold, and each is tested separately because they fail differently:
1. the byte ESTIMATE must never under-estimate (an under-estimate produces the 400 again);
2. the batching rule must respect the budget, including the point cap;
3. a realistic point set must produce batches that genuinely fit under Qdrant's cap.
"""
from __future__ import annotations

import json

import numpy as np
from qdrant_client.models import PointStruct
from qdrant_client.models import SparseVector as QSparseVector

from src.pdf_ingestion.store import (
    _UPSERT_MAX_BYTES,
    _UPSERT_MAX_POINTS,
    _estimate_point_bytes,
    _iter_upsert_batches,
)

QDRANT_PAYLOAD_LIMIT = 33_554_432   # 32 MiB — the server's own constant, from its error message
DENSE_DIM = 1024
DIM_LOW = 64
COLBERT_DIM = 128


def _point(n_tokens: int = 100, text_len: int = 1_200) -> PointStruct:
    """A point shaped like the real thing: two dense vectors, a ColBERT multi-vector, sparse."""
    rng = np.random.default_rng(0)
    return PointStruct(
        id="00000000-0000-0000-0000-000000000001",
        vector={
            "dense_64": rng.random(DIM_LOW).astype(np.float32).tolist(),
            "dense_1024": rng.random(DENSE_DIM).astype(np.float32).tolist(),
            "colbert": rng.random((n_tokens, COLBERT_DIM)).astype(np.float32).tolist(),
            "sparse": QSparseVector(indices=list(range(60)), values=[0.5] * 60),
        },
        payload={"text": "x" * text_len, "parent_text": "y" * 400, "is_content": True,
                 "page_number": 12, "document_id": "d"},
    )


def _serialised_size(points: list) -> int:
    """The number Qdrant measures: the JSON body it receives."""
    return len(json.dumps(
        {"points": [p.model_dump(mode="json") for p in points]}, default=str
    ).encode())


# ── 1. The estimate must not under-estimate ────────────────────────────────

def test_estimate_is_never_an_under_estimate():
    """Under-estimating is the failure mode that reproduces the 400, so it must not happen."""
    for n_tokens, text_len in [(50, 300), (100, 1_200), (400, 4_000)]:
        point = _point(n_tokens, text_len)
        estimated = _estimate_point_bytes(point)
        actual = _serialised_size([point])
        assert estimated >= actual, (
            f"under-estimated: {estimated} < actual {actual} "
            f"(n_tokens={n_tokens}, text_len={text_len})"
        )


def test_estimate_scales_with_the_colbert_multi_vector():
    """ColBERT is what dominates the payload, so the estimate must track its token count."""
    small = _estimate_point_bytes(_point(n_tokens=50))
    large = _estimate_point_bytes(_point(n_tokens=400))
    assert large > small
    # 350 extra tokens x 128 dims x 24 bytes/float ≈ 1.07 MB
    assert large - small > 1_000_000


def test_estimate_handles_a_point_with_no_vectors():
    """Defensive: a malformed point must not crash the batch loop."""
    assert _estimate_point_bytes(PointStruct(id=1, vector={}, payload={})) > 0


# ── 2. The batching rule ───────────────────────────────────────────────────

def test_batches_respect_the_byte_budget():
    """With a 1 MB budget and 400 KB points, two fit and the third starts a new batch."""
    points = [object() for _ in range(5)]
    sizes = {id(p): 400_000 for p in points}
    import src.pdf_ingestion.store as store_mod

    original = store_mod._estimate_point_bytes
    store_mod._estimate_point_bytes = lambda p: sizes[id(p)]
    try:
        batches = list(_iter_upsert_batches(points, max_bytes=1_000_000, max_points=999))
    finally:
        store_mod._estimate_point_bytes = original

    assert [len(b) for b in batches] == [2, 2, 1], "400k+400k fits; a third would exceed 1MB"


def test_a_single_oversized_point_is_still_sent_alone():
    """One point larger than the whole budget must not be dropped or loop forever."""
    points = [object(), object()]
    import src.pdf_ingestion.store as store_mod

    original = store_mod._estimate_point_bytes
    store_mod._estimate_point_bytes = lambda p: 50_000_000
    try:
        batches = list(_iter_upsert_batches(points, max_bytes=1_000_000, max_points=999))
    finally:
        store_mod._estimate_point_bytes = original

    assert [len(b) for b in batches] == [1, 1], "each oversized point goes in its own request"


def test_the_point_cap_applies_to_tiny_points():
    """A byte budget alone would put thousands of tiny points in one request."""
    points = [object() for _ in range(10)]
    import src.pdf_ingestion.store as store_mod

    original = store_mod._estimate_point_bytes
    store_mod._estimate_point_bytes = lambda p: 1
    try:
        batches = list(_iter_upsert_batches(points, max_bytes=10 ** 9, max_points=4))
    finally:
        store_mod._estimate_point_bytes = original

    assert [len(b) for b in batches] == [4, 4, 2]


def test_no_points_yields_no_batches():
    assert list(_iter_upsert_batches([])) == []


# ── 3. The real guarantee, on realistic points ─────────────────────────────

def test_realistic_batches_fit_under_qdrants_limit():
    """THE REGRESSION TEST. 128 realistic points serialise to ~34.7 MB — over the cap.

    This asserts the actual invariant Qdrant enforces, on points shaped like the real ones, using
    the production constants. A fixed-count batch of 128 fails this; the byte budget passes it.
    """
    points = [_point(n_tokens=100) for _ in range(400)]

    batches = list(_iter_upsert_batches(points))
    assert len(batches) > 1, "400 ColBERT points cannot fit in one request"

    for i, batch in enumerate(batches):
        size = _serialised_size(batch)
        assert size < QDRANT_PAYLOAD_LIMIT, (
            f"batch {i} is {size} bytes — over Qdrant's {QDRANT_PAYLOAD_LIMIT} limit"
        )

    assert sum(len(b) for b in batches) == len(points), "no point may be dropped"


def test_the_production_budget_is_comfortably_under_qdrants_limit():
    """The constants themselves are part of the guarantee: a budget near the cap has no headroom.

    The estimate is deliberately generous but not exact, so the budget must leave real slack: if
    someone raised _UPSERT_MAX_BYTES toward 32 MiB, an under-estimated batch could be rejected.
    """
    assert _UPSERT_MAX_BYTES < QDRANT_PAYLOAD_LIMIT
    assert _UPSERT_MAX_BYTES * 2 < QDRANT_PAYLOAD_LIMIT, "want ~4x headroom, not a near-miss"
    assert _UPSERT_MAX_POINTS > 0


def test_a_fixed_128_point_batch_would_have_failed():
    """Proves the regression test is load-bearing: the OLD rule violates the limit.

    If this ever passes, the realistic point size has changed and the byte budget needs revisiting
    — so it is an assertion about the problem, not about the fix.
    """
    points = [_point(n_tokens=100) for _ in range(128)]
    old_style = _serialised_size(points)
    assert old_style > QDRANT_PAYLOAD_LIMIT, (
        "the old 128-point batch now fits, so the byte budget is no longer needed — "
        "revisit _UPSERT_MAX_BYTES rather than deleting this test"
    )
