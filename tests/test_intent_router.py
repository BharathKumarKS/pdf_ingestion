"""Tests for the intent router (Phase 4)."""
from __future__ import annotations

import numpy as np
import pytest

from src.core.intent_router import Intent, IntentRouter, RouteConfig, get_intent_router


# ── Stub router (no embedder needed) ─────────────────────────────────────────

class _StubRouter(IntentRouter):
    """Router that classifies based on keyword heuristics for tests."""

    def classify(self, query_vector: np.ndarray) -> Intent:
        return Intent.MIXED  # stub always returns MIXED


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestRouteConfig:
    def test_factual_route(self):
        from src.core.intent_router import ROUTE_MAP
        r = ROUTE_MAP[Intent.FACTUAL]
        assert r.use_vector is True
        assert r.use_raptor is False
        assert r.use_graph  is False

    def test_overview_route(self):
        from src.core.intent_router import ROUTE_MAP
        r = ROUTE_MAP[Intent.OVERVIEW]
        assert r.use_vector is True
        assert r.use_raptor is True
        assert r.use_graph  is False

    def test_multihop_route(self):
        from src.core.intent_router import ROUTE_MAP
        r = ROUTE_MAP[Intent.MULTIHOP]
        assert r.use_vector is True
        assert r.use_raptor is False
        assert r.use_graph  is True

    def test_visual_route(self):
        from src.core.intent_router import ROUTE_MAP
        r = ROUTE_MAP[Intent.VISUAL]
        assert r.use_vector  is False
        assert r.use_raptor  is False
        assert r.use_graph   is False
        assert r.use_colpali is True

    def test_mixed_route(self):
        from src.core.intent_router import ROUTE_MAP
        r = ROUTE_MAP[Intent.MIXED]
        assert r.use_vector is True
        assert r.use_raptor is True
        assert r.use_graph  is True


class TestIntentRouterStub:
    def test_stub_returns_mixed(self):
        router = _StubRouter()
        vec = np.random.rand(1024).astype(np.float32)
        assert router.classify(vec) == Intent.MIXED

    def test_route_returns_routeconfig(self):
        router = _StubRouter()
        vec = np.random.rand(1024).astype(np.float32)
        result = router.route(vec)
        assert isinstance(result, RouteConfig)
        assert result.intent == Intent.MIXED

    def test_stub_embedder_returns_mixed(self, monkeypatch):
        """When use_stub_embedder=True, router always returns MIXED."""
        from src.core.config import Settings
        cfg = Settings(use_stub_embedder=True, qdrant_in_memory=True)
        router = IntentRouter(settings=cfg)
        vec = np.random.rand(1024).astype(np.float32)
        assert router.classify(vec) == Intent.MIXED


class TestIntentRouterSingleton:
    def test_singleton_same_instance(self):
        r1 = get_intent_router()
        r2 = get_intent_router()
        assert r1 is r2

    def test_reset_clears_singleton(self):
        from src.core.intent_router import reset_intent_router
        r1 = get_intent_router()
        reset_intent_router()
        r2 = get_intent_router()
        assert r1 is not r2


class TestIntentRouterWithEmbedder:
    """Integration tests — uses real Jina embedder, marked slow."""

    @pytest.mark.slow
    def test_factual_query_classified(self):
        from src.core.config import Settings
        from src.pdf_ingestion.embedder import get_embedder
        cfg = Settings(qdrant_in_memory=True)
        embedder = get_embedder(cfg)
        router = IntentRouter(settings=cfg)

        q_vec = embedder.embed_query("What is Newton's second law of motion?")
        intent = router.classify(q_vec)
        # Should be factual or mixed (never overview or multihop)
        assert intent in (Intent.FACTUAL, Intent.MIXED)

    @pytest.mark.slow
    def test_visual_query_classified(self):
        from src.core.config import Settings
        from src.pdf_ingestion.embedder import get_embedder
        cfg = Settings(qdrant_in_memory=True)
        embedder = get_embedder(cfg)
        router = IntentRouter(settings=cfg)

        q_vec = embedder.embed_query("Show me the diagram of the double-slit experiment")
        intent = router.classify(q_vec)
        assert intent in (Intent.VISUAL, Intent.MIXED)

    @pytest.mark.slow
    def test_overview_query_classified(self):
        from src.core.config import Settings
        from src.pdf_ingestion.embedder import get_embedder
        cfg = Settings(qdrant_in_memory=True)
        embedder = get_embedder(cfg)
        router = IntentRouter(settings=cfg)

        q_vec = embedder.embed_query("Give me an overview of classical mechanics")
        intent = router.classify(q_vec)
        assert intent in (Intent.OVERVIEW, Intent.MIXED)
