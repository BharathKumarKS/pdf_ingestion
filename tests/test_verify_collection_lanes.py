"""The lane gate (`scripts/verify_collection_lanes.py`) — its guards must be able to FAIL.

The first draft of that script used `getattr(point, "vectors", {})` where a real Qdrant record
exposes `point.vector` (singular). Every point therefore looked vector-less, every point was
skipped, and the script printed an all-clear with zero coverage — the exact silent-pass class it
exists to prevent. Its two tests passed anyway, because the stub declared the same wrong
attribute: a test written to fit the implementation. These tests pin the behaviours that catch
that, against a stub that models a REAL record.

The stub models `SimpleNamespace(id=..., vector={...}, payload={...})` and a `scroll` returning
`(points, next_page_offset)` — a cursor, not a numeric offset.
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.verify_collection_lanes import (
    EXIT_GAP,
    EXIT_OK,
    EXIT_UNINSPECTABLE,
    point_lanes,
    required_lanes,
    verify,
)


_DEFAULT = object()          # sentinel: `None` must mean "no lanes", not "use the default"


class _StubClient:
    """A collection with declared lanes and a cursor-paged scroll."""

    def __init__(self, points, *, vectors=_DEFAULT, sparse=_DEFAULT, error=None):
        self._points = points
        self._error = error
        self._vectors = _ALL if vectors is _DEFAULT else vectors
        self._sparse = _SPARSE if sparse is _DEFAULT else sparse
        self.scroll_calls: list[dict] = []

    def get_collection(self, _name):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(
            vectors=self._vectors, sparse_vectors=self._sparse)))

    def scroll(self, collection_name, limit=1000, offset=None, with_vectors=True,
               with_payload=True):
        self.scroll_calls.append({"offset": offset, "with_vectors": with_vectors})
        start = 0 if offset is None else int(offset)
        page = self._points[start:start + limit]
        nxt = str(start + limit) if start + limit < len(self._points) else None
        return page, nxt


def _chunk(pid, lanes=("dense_128", "dense_full", "colbert", "sparse")):
    return SimpleNamespace(id=pid, vector={lane: [0.0] for lane in lanes}, payload={})


def _raptor(pid, lanes=("dense_128", "dense_full")):
    return SimpleNamespace(id=pid, vector={lane: [0.0] for lane in lanes},
                           payload={"raptor_level": 1})


_ALL = {"dense_128": object(), "dense_full": object(), "colbert": object()}
_SPARSE = {"sparse": object()}


# ── The happy path, and the scoping that makes it a happy path ──────────────

def test_passes_when_chunks_carry_every_lane_and_raptor_nodes_only_the_dense_ones():
    """The live v2 shape: summary nodes legitimately lack colbert/sparse."""
    client = _StubClient([_chunk(1), _chunk(2), _raptor(3)], vectors=_ALL, sparse=_SPARSE)
    rc, report = verify(client, "kb")
    assert rc == EXIT_OK
    assert report["points_inspected"] == 3
    assert report["points_by_kind"] == {"chunk": 2, "raptor": 1}
    assert report["coverage"]["sparse"] == 2


def test_raptor_nodes_are_still_required_to_carry_the_dense_lanes():
    """Scoping must not degenerate into 'raptor nodes are exempt'."""
    client = _StubClient([_raptor(1, lanes=("dense_full",))], vectors=_ALL, sparse=_SPARSE)
    rc, report = verify(client, "kb")
    assert rc == EXIT_GAP
    assert report["gaps"] == [("1", ["dense_128"])]


# ── The guards ──────────────────────────────────────────────────────────────

def test_a_gap_on_a_chunk_point_fails():
    client = _StubClient([_chunk(1), _chunk(2, lanes=("dense_full",))],
                         vectors=_ALL, sparse=_SPARSE)
    rc, report = verify(client, "kb")
    assert rc == EXIT_GAP
    assert report["gaps"] == [("2", ["colbert", "dense_128", "sparse"])]


def test_a_dead_sparse_lane_is_caught_though_the_point_count_is_healthy():
    """§I33: the lane is declared, every point exists, and the lane is empty on all of them."""
    client = _StubClient([_chunk(1, lanes=("dense_128", "dense_full", "colbert"))],
                         vectors=_ALL, sparse=_SPARSE)
    rc, report = verify(client, "kb")
    assert rc == EXIT_GAP
    assert report["coverage"]["sparse"] == 0


def test_the_sparse_lane_is_read_from_sparse_vectors_not_vectors():
    """§I76: a check reading only `params.vectors` never learns the sparse lane exists."""
    client = _StubClient([_chunk(1, lanes=("dense_128", "dense_full", "colbert"))],
                         vectors=_ALL, sparse=_SPARSE)
    _, report = verify(client, "kb")
    assert "sparse" in report["all_lanes"]


def test_an_empty_scroll_is_a_failure_not_a_pass():
    """The silent all-clear: 'inspected nothing, found nothing wrong'."""
    rc, report = verify(_StubClient([], vectors=_ALL, sparse=_SPARSE), "kb")
    assert rc == EXIT_UNINSPECTABLE
    assert "0 points" in report["error"]


def test_an_absent_collection_is_loud():
    client = _StubClient([], error=RuntimeError("Collection `kb` doesn't exist!"))
    rc, report = verify(client, "kb")
    assert rc == EXIT_UNINSPECTABLE
    assert "kb" in report["error"]


def test_a_collection_with_no_named_lanes_is_refused():
    client = _StubClient([_chunk(1)], vectors=SimpleNamespace(size=768), sparse={})
    rc, report = verify(client, "kb")
    assert rc == EXIT_UNINSPECTABLE
    assert "legacy single-vector" in report["error"]


# ── The two low-level helpers, pinned so the silent-pass defect cannot return ─

def test_point_lanes_reads_the_singular_vector_attribute():
    """`vectors` (plural) is not a Qdrant record attribute — reading it yields a silent all-clear."""
    assert point_lanes(SimpleNamespace(id="1", vector={"dense_full": [0.0]})) == {"dense_full"}
    assert point_lanes(SimpleNamespace(id="1", vectors={"dense_full": [0.0]})) == set()


def test_required_lanes_splits_chunk_from_raptor():
    dense, all_lanes = ["dense_128", "dense_full"], ["dense_128", "dense_full", "sparse"]
    assert required_lanes(_chunk(1), dense, all_lanes) == all_lanes
    assert required_lanes(_raptor(1), dense, all_lanes) == dense


def test_scroll_uses_the_cursor_and_asks_for_vectors():
    """Paging by a numeric offset is not Qdrant's scroll API; the cursor is."""
    client = _StubClient([_chunk(i) for i in range(5)], vectors=_ALL, sparse=_SPARSE)
    rc, report = verify(client, "kb", page_size=2)
    assert rc == EXIT_OK
    assert report["points_inspected"] == 5
    assert [c["offset"] for c in client.scroll_calls] == [None, "2", "4"]
    assert all(c["with_vectors"] for c in client.scroll_calls)
