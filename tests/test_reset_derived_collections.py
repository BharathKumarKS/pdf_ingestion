"""`scripts/reset_derived_collections.py` — the drop that makes the derived collections 1024d (§I12).

The script is destructive, so the tests pin the two properties that matter:

  * **the allowlist** — only `derivative_artifacts` / `concept_embeddings` can be dropped;
    anything else (`knowledge_base`, `visual_knowledge_base`) is refused with exit 2 and
    nothing is deleted; and
  * **dry-run safety** — without `--yes`, nothing is deleted at all.

They run against a fake Qdrant client, following the repo's `importlib` script-loading
convention (`tests/test_graph_clear.py`, `tests/test_backmatter_gate.py`). The real client is
exercised by the live dry-run, not here — a fake cannot validate a Qdrant call, only the logic
that decides which collection to ask for.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = _ROOT / "scripts" / "reset_derived_collections.py"
    spec = importlib.util.spec_from_file_location("reset_derived_collections_under_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


rdc = _load_script()


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Vectors:
    def __init__(self, size):
        self.size = size


class _Params:
    def __init__(self, size):
        self.vectors = _Vectors(size)


class _Config:
    def __init__(self, size):
        self.params = _Params(size)


class _Info:
    def __init__(self, points, size):
        self.points_count = points
        self.config = _Config(size)


class _FakeCfg:
    da_collection = "derivative_artifacts"
    concept_collection = "concept_embeddings"
    qdrant_collection = "knowledge_base_v2"
    colpali_collection = "visual_knowledge_base"
    dense_dim = 1024
    embedding_dim = 768
    qdrant_host = "10.0.10.65"
    qdrant_local_path = "./data/qdrant"


class _FakeClient:
    """collections: {name: (points, dim)}. Records every delete."""

    def __init__(self, collections):
        self.collections = dict(collections)
        self.deleted: list[str] = []

    def get_collection(self, name):
        if name not in self.collections:
            raise ValueError(f"collection {name} not found")
        points, dim = self.collections[name]
        return _Info(points, dim)

    def delete_collection(self, name):
        if name not in self.collections:
            raise ValueError(f"collection {name} not found")
        self.deleted.append(name)
        del self.collections[name]


def _client():
    return _FakeClient({
        "derivative_artifacts": (81837, 768),
        "concept_embeddings":   (19719, 768),
        "knowledge_base_v2":    (3869, None),
        "visual_knowledge_base": (1033, None),
    })


# ── The allowlist is the guard ────────────────────────────────────────────────

def test_knowledge_base_is_refused_and_nothing_is_deleted():
    c = _client()
    rc = rdc.main(["--collections", "knowledge_base_v2", "--yes"], client=c, cfg=_FakeCfg())
    assert rc == 2
    assert c.deleted == []
    assert "knowledge_base_v2" in c.collections          # untouched


def test_visual_collection_is_refused():
    c = _client()
    rc = rdc.main(["--collections", "visual_knowledge_base", "--yes"], client=c, cfg=_FakeCfg())
    assert rc == 2
    assert c.deleted == []


def test_a_mixed_request_is_refused_whole():
    """One bad name refuses the whole request — never a partial delete."""
    c = _client()
    rc = rdc.main(["--collections", "concept_embeddings", "knowledge_base_v2", "--yes"],
                  client=c, cfg=_FakeCfg())
    assert rc == 2
    assert c.deleted == []                                # the allowed one was NOT deleted either
    assert "concept_embeddings" in c.collections


# ── Dry-run safety ────────────────────────────────────────────────────────────

def test_dry_run_deletes_nothing():
    c = _client()
    rc = rdc.main(["--collections", "concept_embeddings"], client=c, cfg=_FakeCfg())
    assert rc == 0
    assert c.deleted == []
    assert "concept_embeddings" in c.collections


# ── The apply path ────────────────────────────────────────────────────────────

def test_yes_deletes_the_allowed_collection():
    c = _client()
    rc = rdc.main(["--collections", "concept_embeddings", "--yes"], client=c, cfg=_FakeCfg())
    assert rc == 0
    assert c.deleted == ["concept_embeddings"]
    assert "concept_embeddings" not in c.collections
    assert "derivative_artifacts" in c.collections        # the other one is untouched


def test_both_derived_collections_can_be_dropped():
    c = _client()
    rc = rdc.main(["--collections", "derivative_artifacts", "concept_embeddings", "--yes"],
                  client=c, cfg=_FakeCfg())
    assert rc == 0
    assert sorted(c.deleted) == ["concept_embeddings", "derivative_artifacts"]
    assert "knowledge_base_v2" in c.collections


def test_absent_collection_is_skipped_not_an_error():
    c = _FakeClient({"knowledge_base_v2": (3869, None)})
    rc = rdc.main(["--collections", "concept_embeddings", "--yes"], client=c, cfg=_FakeCfg())
    assert rc == 0
    assert c.deleted == []


# ── The plan reports the stale dimension (what the operator reads) ────────────

def test_plan_reports_the_stale_dimension():
    c = _client()
    plan = rdc.plan_reset(c, rdc._droppable(_FakeCfg()), ["concept_embeddings"])
    assert plan["refused"] == []
    st = plan["states"]["concept_embeddings"]
    assert st["exists"] is True
    assert st["dim"] == 768                                # the stale state this script removes
    assert st["points"] == 19719


def test_allowlist_is_exactly_the_two_derived_collections():
    assert set(rdc._droppable(_FakeCfg())) == {"derivative_artifacts", "concept_embeddings"}


def test_repopulate_sources_are_documented_for_every_droppable():
    for name in rdc._droppable(_FakeCfg()):
        assert name in rdc._REPOPULATE and rdc._REPOPULATE[name]
