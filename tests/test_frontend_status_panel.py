"""Tests for the Admin Status "store vs SQLite" table (I3).

The panel itself lives behind ``is_admin`` in the app file, so a test cannot click
through to it. ``_store_vs_sqlite_rows`` was extracted to module level for exactly that
reason — this exercises the comparison logic, including the disagreement cases the panel
exists to surface.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "src" / "frontend" / "streamlit_app.py"


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("streamlit_app_status_under_test", _APP)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeStore:
    """Returns a canned count per collection; raises for an unknown one."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts
        self.asked: list[str] = []

    def count_collection(self, collection_name: str) -> int:
        self.asked.append(collection_name)
        return self._counts[collection_name]


def test_matching_counts_are_ticked(app):
    store = _FakeStore({"knowledge_base": 5135})
    rows = app._store_vs_sqlite_rows(store, [("knowledge_base", 5135)])
    assert rows == [{
        "Collection":   "knowledge_base",
        "Store points": 5135,
        "SQLite rows":  5135,
        "Match":        "✅",
    }]


def test_mismatch_reports_the_signed_delta(app):
    store = _FakeStore({"derivative_artifacts": 81837})
    (row,) = app._store_vs_sqlite_rows(store, [("derivative_artifacts", 82164)])
    assert row["Match"] == "⚠️ Δ -327"
    assert row["Store points"] == 81837
    assert row["SQLite rows"] == 82164


def test_positive_delta_is_signed(app):
    store = _FakeStore({"visual_knowledge_base": 2835})
    (row,) = app._store_vs_sqlite_rows(store, [("visual_knowledge_base", 945)])
    assert row["Match"] == "⚠️ Δ +1,890"


def test_empty_store_is_called_out(app):
    """A store that answers but holds nothing is a distinct, louder signal than a delta."""
    store = _FakeStore({"knowledge_base": 0})
    (row,) = app._store_vs_sqlite_rows(store, [("knowledge_base", 5048)])
    assert row["Match"] == "⚠️ store empty"


def test_collection_with_no_sqlite_counterpart(app):
    """concept_embeddings has no SQLite table — a populated one must not read as a mismatch."""
    store = _FakeStore({"concept_embeddings": 1200})
    (row,) = app._store_vs_sqlite_rows(store, [("concept_embeddings", None)])
    assert row["Match"] == "—"
    assert row["SQLite rows"] == "—"


def test_empty_store_is_flagged_even_without_a_sqlite_counterpart(app):
    """An empty collection is a problem on its own, not a 'no counterpart' dash."""
    store = _FakeStore({"concept_embeddings": 0})
    (row,) = app._store_vs_sqlite_rows(store, [("concept_embeddings", None)])
    assert row["Match"] == "⚠️ store empty"


def test_all_four_collections_are_reported_in_order(app):
    store = _FakeStore({
        "knowledge_base": 5135, "visual_knowledge_base": 2835,
        "derivative_artifacts": 81837, "concept_embeddings": 0,
    })
    rows = app._store_vs_sqlite_rows(store, [
        ("knowledge_base", 5135),
        ("visual_knowledge_base", 945),
        ("derivative_artifacts", 82164),
        ("concept_embeddings", None),
    ])
    assert [r["Collection"] for r in rows] == [
        "knowledge_base", "visual_knowledge_base", "derivative_artifacts", "concept_embeddings",
    ]
    assert [r["Match"] for r in rows] == ["✅", "⚠️ Δ +1,890", "⚠️ Δ -327", "⚠️ store empty"]
    assert store.asked == [
        "knowledge_base", "visual_knowledge_base", "derivative_artifacts", "concept_embeddings",
    ]
