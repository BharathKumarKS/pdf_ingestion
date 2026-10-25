"""Stage A — the dense lane NAMES and the low lane's WIDTH are resolved off the collection, and a
width mismatch raises instead of truncating silently.

**Why the width must be resolved and not configured.** ``knowledge_base_v2`` declares its low lane
at **64d** (``dense_64``) and ``knowledge_base_v3`` at **128d** (``dense_128``), and the gemma
adoption's product-endpoint A/B queries **both** — v2 is the baseline arm. Slicing the query vector
to ``cfg.dense_dim_low`` would send a 128d vector to v2's 64d lane, so the baseline arm would either
400 or search at a silently wrong width. ``cfg.dense_dim_low`` is the width a **NEW** collection is
created at, not a property of every collection.

The discriminating tests are the ones that fail against the old code:

  * ``test_v2_is_queried_at_its_own_64d_width`` fails on the old hardcoded ``"dense_64"`` +
    ``query_vector[:cfg.dense_dim_low]`` (it would slice 128);
  * ``test_v3_is_queried_by_its_own_names`` fails on the old hardcoded ``"dense_64"`` name;
  * ``test_write_guard_raises_on_a_width_mismatch`` fails with no guard at all (the only symptom
    would be a bare Qdrant 400 with no fix in it, §I47's lesson).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest


def _cfg_vectors(**sizes):
    """A collection's ``params.vectors`` mapping: lane name -> declared width."""
    return {name: SimpleNamespace(size=size) for name, size in sizes.items()}


class _CapturingQdrant:
    """A named-vector collection with real declared widths, recording every ``query_points``."""

    def __init__(self, vectors_cfg):
        self._vectors_cfg = vectors_cfg
        self.calls: list[dict] = []

    def get_collection(self, _name):
        return SimpleNamespace(config=SimpleNamespace(
            params=SimpleNamespace(vectors=self._vectors_cfg)))

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])

    def close(self):
        pass


def _run_funnel(settings, monkeypatch, vectors_cfg, **overrides):
    from src.pdf_ingestion.store import DocumentStore

    cfg = settings.model_copy(update=overrides) if overrides else settings
    store = DocumentStore(cfg)
    fake = _CapturingQdrant(vectors_cfg)
    monkeypatch.setattr(store, "_qdrant", fake)

    store._qdrant_search(
        np.ones(cfg.dense_dim, dtype=np.float32),
        filter_=None,
        limit=cfg.mmr_candidates,
        query_text="what is kinetic energy",
    )
    assert fake.calls, "the funnel issued no query_points call"
    return cfg, fake.calls


def _inner(kwargs: dict):
    """The funnel's first prefetch stage — the low-dimension lane."""
    return kwargs["prefetch"][0].prefetch[0]


# ── 1. The resolver ─────────────────────────────────────────────────────────

def test_resolves_v3_lane_names_and_width(settings):
    from src.pdf_ingestion.store import _resolve_low_lane

    name, size = _resolve_low_lane(
        _cfg_vectors(dense_128=128, dense_full=768), settings)
    assert (name, size) == ("dense_128", 128)


def test_resolves_v2_lane_name_at_its_own_64d_width(settings):
    """⚠️ The A/B's baseline arm: v2's lane is 64d while cfg.dense_dim_low is 128."""
    from src.pdf_ingestion.store import _resolve_low_lane

    cfg = settings.model_copy(update={"dense_dim_low": 128})
    name, size = _resolve_low_lane(_cfg_vectors(dense_64=64, dense_1024=1024), cfg)
    assert (name, size) == ("dense_64", 64), "the collection's width must win over the config's"


def test_unreadable_width_falls_back_to_the_config(settings):
    """A stub schema (``object()``) declares no size — the configured width is the honest answer."""
    from src.pdf_ingestion.store import _lane_size, _resolve_low_lane

    cfg = settings.model_copy(update={"dense_dim_low": 128})
    cfg_vectors = {"dense_64": object(), "dense_1024": object()}
    assert _lane_size(cfg_vectors, "dense_64") is None
    assert _resolve_low_lane(cfg_vectors, cfg) == ("dense_64", 128)


def test_unreadable_schema_uses_the_newest_lane_name(settings):
    from src.pdf_ingestion.store import _LOW_VECTOR_NAMES, _resolve_low_lane

    assert _resolve_low_lane(None, settings) == (_LOW_VECTOR_NAMES[0], settings.dense_dim_low)


def test_full_lane_prefers_the_width_free_name(settings):
    """``dense_full`` is newest, so a collection carrying it resolves to it — not ``dense_1024``."""
    from src.pdf_ingestion.store import _dense_name_from

    assert _dense_name_from(_cfg_vectors(
        dense_128=128, dense_full=768, dense_1024=1024)) == "dense_full"
    # v2 still resolves, so it stays queryable.
    assert _dense_name_from(_cfg_vectors(dense_64=64, dense_1024=1024)) == "dense_1024"


# ── 2. The funnel queries each collection at ITS width, by ITS names ────────

def test_v3_is_queried_by_its_own_names(settings, monkeypatch):
    cfg, calls = _run_funnel(
        settings, monkeypatch, _cfg_vectors(dense_128=128, dense_full=768), dense_dim=768)

    inner = _inner(calls[0])
    assert inner.using == "dense_128"
    assert len(inner.query) == 128, "the low lane must be sliced to the LANE's width"
    # The full-dimension lane is the OUTER prefetch's `using` (the funnel fuses the prefetches,
    # so the top-level call carries `prefetch=` + a FusionQuery, not `using=`).
    outer = calls[0]["prefetch"][0]
    assert outer.using == "dense_full"
    assert len(outer.query) == 768


def test_v2_is_queried_at_its_own_64d_width(settings, monkeypatch):
    """⚠️ The regression that would silently kill Stage F's baseline arm."""
    cfg, calls = _run_funnel(
        settings, monkeypatch, _cfg_vectors(dense_64=64, dense_1024=1024))

    inner = _inner(calls[0])
    assert inner.using == "dense_64"
    assert len(inner.query) == 64, (
        "v2's low lane is 64d — slicing to cfg.dense_dim_low (128) would send the wrong width"
    )
    outer = calls[0]["prefetch"][0]
    assert outer.using == "dense_1024"
    assert len(outer.query) == 1024


# ── 3. The write guard ──────────────────────────────────────────────────────

def test_write_guard_raises_on_a_width_mismatch(settings):
    from src.pdf_ingestion.store import _assert_lane_width

    with pytest.raises(RuntimeError) as excinfo:
        _assert_lane_width(np.ones(128, dtype=np.float32), "dense_64", 64, settings)

    msg = str(excinfo.value)
    assert "dense_64" in msg and "64d" in msg and "128d" in msg
    assert "Nothing was written" in msg
    assert "dense_dim_low" in msg, "it must name the remedy, not just the fault"


def test_write_guard_is_silent_on_a_match(settings):
    from src.pdf_ingestion.store import _assert_lane_width

    _assert_lane_width(np.ones(128, dtype=np.float32), "dense_128", 128, settings)
    _assert_lane_width(np.ones(64, dtype=np.float32), "dense_64", 64, settings)
