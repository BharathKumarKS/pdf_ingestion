"""§G5/§I2 — genuine multi-hop: `graph_search` traverses `RELATES_TO` when `graph_max_hops > 1`.

The shipped lane is a single-hop concept lookup and hard-codes `hop_distance = 0` (§I2). This adds
hop-bounded expansion behind `cfg.graph_max_hops`, DEFAULT 1 = the shipped behaviour, so nothing
changes until the expansion's ablation runs. The two paths are branched, and these tests pin:
  * default OFF (a fresh Settings carries 1), and the legacy path emits NO traversal;
  * the expansion emits `RELATES_TO*0..N` and reports the real `hop_distance`;
  * `hop_distance` is NOT constant once the traversal runs;
  * the hop bound is CLAMPED (a wild value cannot widen the query).

The discriminating test is `test_expansion_traverses_and_reports_real_hops`: set the branch back to
the legacy query and it fails (no `RELATES_TO`, hop stays 0).
"""
from __future__ import annotations

import numpy as np


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows, rec):
        self._rows, self._rec = rows, rec

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run(self, cypher, **params):
        self._rec["cypher"] = cypher
        self._rec["params"] = params
        return _FakeResult(self._rows)


class _FakeDriver:
    def __init__(self, rows, rec):
        self._rows, self._rec = rows, rec

    def session(self):
        return _FakeSession(self._rows, self._rec)

    def close(self):
        pass


def _run(settings, monkeypatch, *, max_hops, rows):
    """Drive the REAL `graph_search` with a fake driver; return (results, recorded cypher)."""
    from src.pdf_ingestion.graph_builder import GraphBuilder

    cfg = settings.model_copy(update={"graph_max_hops": max_hops})
    g = GraphBuilder(cfg)
    rec: dict = {}
    monkeypatch.setattr(g, "_get_driver", lambda: _FakeDriver(rows, rec))
    monkeypatch.setattr(
        g, "_find_concepts_scored",
        lambda qv, top_k=8, query_text=None: [("orbit", 0.9), ("inertia", 0.8)])
    out = g.graph_search("why do orbits persist", tenant_id="global",
                         query_vector=np.ones(cfg.dense_dim, dtype=np.float32), limit=5)
    return out, rec.get("cypher", "")


_LEGACY_ROWS = [{"chunk_id": "c1", "concept_path": ["orbit"], "matched_concepts": 1,
                 "concept_score": 0.9, "hop_distance": 0, "text_preview": "t1"}]
_EXPANSION_ROWS = [
    {"chunk_id": "c1", "concept_path": ["orbit"], "matched_concepts": 1,
     "concept_score": 0.9, "hop_distance": 0, "text_preview": "t1"},
    {"chunk_id": "c2", "concept_path": ["gravity", "orbit"], "matched_concepts": 2,
     "concept_score": 0.7, "hop_distance": 2, "text_preview": "t2"},
]


def test_default_setting_is_one(settings):
    """The shipped default must be the non-traversing path — nothing changes by accident."""
    assert settings.graph_max_hops == 1


def test_default_path_emits_no_traversal(settings, monkeypatch):
    out, cypher = _run(settings, monkeypatch, max_hops=1, rows=_LEGACY_ROWS)
    assert "RELATES_TO" not in cypher, "the shipped path must NOT traverse RELATES_TO"
    assert "0 AS hop_distance" in cypher
    assert out[0]["hop_distance"] == 0


def test_expansion_traverses_and_reports_real_hops(settings, monkeypatch):
    """THE discriminating test — the traversal must run and report real hops."""
    out, cypher = _run(settings, monkeypatch, max_hops=2, rows=_EXPANSION_ROWS)
    assert "RELATES_TO*0..2" in cypher, "the expansion must emit the hop-bounded traversal"
    assert "min(size(relationships(p)))" in cypher, "hop_distance must be the real path length"
    assert [r["hop_distance"] for r in out] == [0, 2]


def test_hop_distance_is_not_constant(settings, monkeypatch):
    """§I2's defect was a CONSTANT hop_distance; after the traversal it must vary."""
    out, _ = _run(settings, monkeypatch, max_hops=2, rows=_EXPANSION_ROWS)
    assert len({r["hop_distance"] for r in out}) > 1, "hop_distance is still constant"


def test_hop_bound_is_clamped(settings, monkeypatch):
    """A wild setting cannot widen the query — the literal is clamped to <= 2 (3 hops = 66 s live)."""
    _, cypher = _run(settings, monkeypatch, max_hops=99, rows=_EXPANSION_ROWS)
    assert "RELATES_TO*0..2" in cypher, "the hop bound must be clamped"
    assert "*0..99" not in cypher


def test_seed_only_when_max_hops_is_zero(settings, monkeypatch):
    """0 (and any value < 1) falls back to the shipped seed-only path, never 'no seeds'."""
    _, cypher = _run(settings, monkeypatch, max_hops=0, rows=_LEGACY_ROWS)
    assert "RELATES_TO" not in cypher
