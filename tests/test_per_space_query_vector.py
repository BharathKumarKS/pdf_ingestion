"""§A — the per-space query-vector fix: one query vector per collection space.

Guards A1–A5 (pre-registration §4, committed ALONE as `6462145`). Each test drives the REAL
resolver (`store.resolve_space_query_vector`); the discriminating one is **A3** — when the arm's
space already matches the collection's, the fix must be a **bit-exact no-op**.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.core.config import get_settings
from src.pdf_ingestion import cluster_embedder
from src.pdf_ingestion.store import DocumentStore, resolve_space_query_vector


def _fake_qdrant(width: int):
    """A Qdrant stand-in whose collection declares a dense vector of `width`."""
    vec = SimpleNamespace(size=width)
    info = SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vec)))
    return SimpleNamespace(get_collection=lambda collection_name=None: info)


def _cfg(**over):
    return get_settings().model_copy(update={"use_stub_embedder": True, **over})


@pytest.fixture(autouse=True)
def _reset_derived():
    cluster_embedder.reset_derived_embedder()
    yield
    cluster_embedder.reset_derived_embedder()


# ── A3 — the discriminating control ─────────────────────────────────────────────────────────────
def test_A3_same_width_is_a_bit_exact_no_op():
    """The arm's vector IS the lane's space -> it is passed through UNCHANGED (same object)."""
    cfg = _cfg(derived_dense_dim=768)
    arm = np.arange(768, dtype=np.float32)
    got = resolve_space_query_vector(cfg, _fake_qdrant(768), arm, "text", "coll", "da")
    assert got is arm


# ── A1 — a mismatched arm gets a query in the collection's space ────────────────────────────────
def test_A1_differing_width_re_embeds_in_the_collection_space():
    cfg = _cfg(derived_dense_dim=768)
    arm = np.zeros(1024, dtype=np.float32)
    got = resolve_space_query_vector(cfg, _fake_qdrant(768), arm, "text", "coll", "da")
    assert got is not arm and got.shape == (768,)


# ── A2 — the lane's vector is NOT the arm's dense vector ────────────────────────────────────────
def test_A2_the_lane_vector_is_not_the_arm_vector():
    cfg = _cfg(derived_dense_dim=768)
    arm = np.zeros(1024, dtype=np.float32)
    got = resolve_space_query_vector(cfg, _fake_qdrant(768), arm, "text", "coll", "da")
    assert got.shape != arm.shape


# ── A4 — a mismatch is never a silent [] ────────────────────────────────────────────────────────
def test_A4_mismatch_without_text_raises():
    cfg = _cfg(derived_dense_dim=768)
    with pytest.raises(RuntimeError, match="§A"):
        resolve_space_query_vector(cfg, _fake_qdrant(768), np.zeros(1024, dtype=np.float32),
                                   None, "coll", "da")


def test_A4b_derived_embedder_of_the_wrong_width_raises():
    cfg = _cfg(derived_dense_dim=512)          # derived embedder 512d, collection 768d
    with pytest.raises(RuntimeError, match="cannot produce a query in that space"):
        resolve_space_query_vector(cfg, _fake_qdrant(768), np.zeros(1024, dtype=np.float32),
                                   "text", "coll", "da")


# ── A5 — the width is read OFF THE COLLECTION, never from config ────────────────────────────────
def test_A5_width_comes_off_the_collection_not_config():
    cfg = _cfg(derived_dense_dim=512, dense_dim=1024)
    got = resolve_space_query_vector(cfg, _fake_qdrant(512), np.zeros(1024, dtype=np.float32),
                                     "text", "coll", "da")
    assert got.shape == (512,)                 # the COLLECTION's width, not cfg.dense_dim


def test_unreadable_schema_keeps_the_arm_vector():
    """An absent/unreadable collection falls back to today's behaviour rather than guessing."""
    cfg = _cfg(derived_dense_dim=768)
    arm = np.zeros(1024, dtype=np.float32)
    broken = SimpleNamespace(get_collection=lambda collection_name=None: (_ for _ in ()).throw(
        RuntimeError("no such collection")))
    assert resolve_space_query_vector(cfg, broken, arm, "t", "coll", "da") is arm


# ── the DA lane actually SENDS the resolved vector ──────────────────────────────────────────────
def test_search_da_sends_the_collection_space_vector(monkeypatch):
    cfg = _cfg(derived_dense_dim=768, da_enabled=True)
    store = DocumentStore(cfg)
    seen: dict = {}

    def fake_query_points(collection_name=None, query=None, **kw):
        seen["query"] = np.asarray(query)
        return SimpleNamespace(points=[])

    fake = _fake_qdrant(768)
    fake.query_points = fake_query_points
    monkeypatch.setattr(store, "_qdrant", fake)

    store.search_da(np.zeros(1024, dtype=np.float32), tenant_id="global", limit=5,
                    query_text="hello")
    assert seen["query"].shape == (768,)       # re-embedded, not the 1024 arm vector


def test_search_da_raises_on_a_mismatch_without_text(monkeypatch):
    """A4 through the real lane: a mismatched arm with no text RAISES, never a silent []."""
    cfg = _cfg(derived_dense_dim=768, da_enabled=True)
    store = DocumentStore(cfg)
    fake = _fake_qdrant(768)
    fake.query_points = lambda **kw: SimpleNamespace(points=[])
    monkeypatch.setattr(store, "_qdrant", fake)

    with pytest.raises(RuntimeError, match="§A"):
        store.search_da(np.zeros(1024, dtype=np.float32), tenant_id="global", limit=5)
