"""C2 / lane-plan S4 — `search_fused`: ONE fusion over every lane, each lane competing on RANK.

Today's wiring inserts lanes at three depths (plan §0): the vector lanes are fused in
`_qdrant_search`; the DA lane is appended after that fusion; the graph lane is appended by the
CALLER after dedup/MMR with a fabricated `score`. An appended lane can never displace a fused hit.
`search_fused` collects each lane's RANKED list and fuses them all with `_rrf_merge` + weights.

These tests pin the four properties the plan's S4 verifier names, each of which CAN fail:

  (a) every candidate carries an `rrf_score` — it went through the fusion, not an append;
  (b) a candidate's fused rank DEPENDS ON its rank within its lane (reverse a lane -> order moves);
  (c) the fused set is a SUPERSET of every contributor's set (no lane's candidates vanish);
  (d) a lane weight of 0 REMOVES that lane's contribution (not merely scores it zero).
"""
from __future__ import annotations

import numpy as np


def _hits(prefix: str, n: int, start_page: int = 100):
    """Distinct pages so the page-dedup stage cannot collapse them."""
    return [{"chunk_id": f"{prefix}{i}", "page_number": start_page + i, "text": f"{prefix} {i}",
             "score": 1.0 / (i + 1)} for i in range(n)]


def _store_with_lanes(settings, monkeypatch, *, vec, da, graph, raptor=None):
    from src.pdf_ingestion.store import DocumentStore
    s = DocumentStore(settings.model_copy(update={"da_enabled": True}))
    monkeypatch.setattr(s, "search", lambda *a, **k: list(vec))
    monkeypatch.setattr(s, "search_da", lambda *a, **k: list(da))
    monkeypatch.setattr(s, "_resolve_da_parents", lambda hits: list(hits))
    if raptor is not None:
        monkeypatch.setattr(s, "search_raptor", lambda *a, **k: list(raptor))

    class _FakeGraph:
        def graph_search(self, **k):
            return list(graph)
    import src.pdf_ingestion.graph_builder as gb
    monkeypatch.setattr(gb, "get_graph_builder", lambda cfg: _FakeGraph())
    return s


def _ids(hits):
    return [h["chunk_id"] for h in hits]


# ── (a) every candidate carries an rrf_score ─────────────────────────────────

def test_every_candidate_carries_an_rrf_score(settings, monkeypatch):
    s = _store_with_lanes(settings, monkeypatch,
                          vec=_hits("v", 5), da=_hits("d", 5, 200), graph=_hits("g", 5, 300))
    out = s.search_fused(np.ones(768, dtype=np.float32), query_text="q", fetch_k=50)
    assert out, "the fusion returned nothing"
    assert all("rrf_score" in h for h in out), (
        "a candidate without an rrf_score did not go through the fusion — it was appended")
    assert all(h["rrf_score"] > 0 for h in out)


# ── (b) fused rank depends on the lane's own rank ────────────────────────────

def test_fused_rank_depends_on_the_lane_rank(settings, monkeypatch):
    da = _hits("d", 5, 200)
    s1 = _store_with_lanes(settings, monkeypatch,
                           vec=_hits("v", 5), da=da, graph=_hits("g", 5, 300))
    out1 = _ids(s1.search_fused(np.ones(768, dtype=np.float32), query_text="q", fetch_k=50))

    # Reverse ONLY the DA lane; the fused order must move (rank is what RRF reads).
    s2 = _store_with_lanes(settings, monkeypatch,
                           vec=_hits("v", 5), da=list(reversed(da)), graph=_hits("g", 5, 300))
    out2 = _ids(s2.search_fused(np.ones(768, dtype=np.float32), query_text="q", fetch_k=50))

    assert out1 != out2, "reversing a lane did not change the fused order — rank is not being read"


# ── (c) the fused set is a superset of every lane ────────────────────────────

def test_fused_set_is_a_superset_of_every_lane(settings, monkeypatch):
    vec, da, graph, rap = _hits("v", 5), _hits("d", 5, 200), _hits("g", 5, 300), _hits("r", 5, 400)
    s = _store_with_lanes(settings, monkeypatch, vec=vec, da=da, graph=graph, raptor=rap)
    out = _ids(s.search_fused(np.ones(768, dtype=np.float32), query_text="q",
                              raptor_vector=np.ones(768, dtype=np.float32), fetch_k=50))
    for lane in (vec, da, graph, rap):
        missing = set(_ids(lane)) - set(out)
        assert not missing, f"a lane's candidates vanished from the fusion: {missing}"


# ── (d) a zero weight REMOVES the lane ───────────────────────────────────────

def test_zero_weight_removes_the_lane(settings, monkeypatch):
    vec, da, graph = _hits("v", 5), _hits("d", 5, 200), _hits("g", 5, 300)
    s = _store_with_lanes(settings, monkeypatch, vec=vec, da=da, graph=graph)
    out = _ids(s.search_fused(np.ones(768, dtype=np.float32), query_text="q",
                              weights={"graph": 0.0}, fetch_k=50))
    assert not (set(_ids(graph)) & set(out)), "a zero-weight lane still contributed candidates"
    assert set(_ids(vec)) <= set(out) and set(_ids(da)) <= set(out)


def test_rrf_score_decreases_with_rank_within_a_lane(settings, monkeypatch):
    """The RANK term must be present: a lane's rank-1 candidate must out-score its rank-5 one.

    ⚠️ The `fused order moves when a lane is reversed` test above does NOT discriminate this —
    with a constant score the insertion order still follows the lane order, so that test passes.
    This one reads the score itself, which is the quantity the rank term changes.
    """
    graph = _hits("g", 5, 300)
    s = _store_with_lanes(settings, monkeypatch,
                          vec=_hits("v", 5), da=_hits("d", 5, 200), graph=graph)
    out = s.search_fused(np.ones(768, dtype=np.float32), query_text="q", fetch_k=50)
    by = {h["chunk_id"]: h["rrf_score"] for h in out}
    scores = [by[g["chunk_id"]] for g in graph]
    assert scores == sorted(scores, reverse=True), f"rrf_score not monotone in rank: {scores}"
    assert scores[0] > scores[-1], f"rank-1 and rank-5 carry the same rrf_score: {scores}"


def test_a_large_weight_promotes_that_lanes_candidates(settings, monkeypatch):
    """The weights must actually SCALE the fusion — otherwise they are decorative."""
    vec, da, graph = _hits("v", 5), _hits("d", 5, 200), _hits("g", 5, 300)
    s = _store_with_lanes(settings, monkeypatch, vec=vec, da=da, graph=graph)
    out = _ids(s.search_fused(np.ones(768, dtype=np.float32), query_text="q",
                              weights={"graph": 1000.0}, fetch_k=50))
    assert out[0] == graph[0]["chunk_id"], (
        f"a 1000x weight on the graph lane did not promote its rank-1 chunk; top was {out[0]}")


def test_weights_length_mismatch_raises(settings):
    from src.pdf_ingestion.store import DocumentStore
    raised = False
    try:
        DocumentStore._rrf_merge(_hits("a", 2), _hits("b", 2), rrf_k=1, weights=[1.0])
    except ValueError:
        raised = True
    assert raised, "a weights/lanes length mismatch must RAISE, not silently mis-assign weights"


# ── the unweighted path is unchanged (regression guard on §I68's rrf_k=1 convention) ──

def test_default_weights_equal_the_unweighted_fusion(settings):
    from src.pdf_ingestion.store import DocumentStore
    a, b = _hits("a", 3), _hits("b", 3, 200)
    default = DocumentStore._rrf_merge(a, b, rrf_k=1)
    explicit = DocumentStore._rrf_merge(a, b, rrf_k=1, weights=[1.0, 1.0])
    assert [h["chunk_id"] for h in default] == [h["chunk_id"] for h in explicit]
    assert [h["rrf_score"] for h in default] == [h["rrf_score"] for h in explicit]
