"""Tests for the cross-encoder re-ranker (Phase 4)."""
from __future__ import annotations

import pytest

from src.pdf_ingestion.reranker import StubReranker, get_reranker, reset_reranker


def _make_chunks(texts: list[str]) -> list[dict]:
    return [{"text": t, "score": 0.9 - i * 0.1} for i, t in enumerate(texts)]


class TestStubReranker:
    def test_returns_top_k(self):
        r = StubReranker()
        chunks = _make_chunks(["a", "b", "c", "d", "e"])
        result = r.rerank("query", chunks, top_k=3)
        assert len(result) == 3

    def test_preserves_original_order(self):
        r = StubReranker()
        chunks = _make_chunks(["first", "second", "third"])
        result = r.rerank("query", chunks, top_k=2)
        assert result[0]["text"] == "first"
        assert result[1]["text"] == "second"

    def test_top_k_larger_than_chunks(self):
        r = StubReranker()
        chunks = _make_chunks(["a", "b"])
        result = r.rerank("query", chunks, top_k=10)
        assert len(result) == 2

    def test_empty_chunks(self):
        r = StubReranker()
        assert r.rerank("query", [], top_k=5) == []


class TestRerankerFactory:
    def test_stub_factory(self):
        from src.core.config import Settings
        cfg = Settings(use_stub_reranker=True, qdrant_in_memory=True)
        r = get_reranker(cfg)
        assert isinstance(r, StubReranker)

    def test_singleton(self):
        from src.core.config import Settings
        cfg = Settings(use_stub_reranker=True, qdrant_in_memory=True)
        r1 = get_reranker(cfg)
        r2 = get_reranker(cfg)
        assert r1 is r2

    def test_reset_clears_singleton(self):
        from src.core.config import Settings
        cfg = Settings(use_stub_reranker=True, qdrant_in_memory=True)
        r1 = get_reranker(cfg)
        reset_reranker()
        r2 = get_reranker(cfg)
        assert r1 is not r2


class TestRerankerIntegration:
    def test_reranker_reorders_chunks(self):
        """Stub reranker preserves order; real reranker would reorder."""
        from src.core.config import Settings
        cfg = Settings(use_stub_reranker=True, qdrant_in_memory=True)
        reranker = get_reranker(cfg)
        chunks = _make_chunks([
            "Newton's first law states that an object at rest stays at rest.",
            "Thermodynamics deals with heat and temperature.",
            "The photoelectric effect shows light behaves as particles.",
        ])
        result = reranker.rerank("Newton's first law", chunks, top_k=2)
        assert len(result) == 2
        assert all("text" in c for c in result)

    @pytest.mark.slow
    def test_real_reranker_reorders(self):
        """Real cross-encoder should rank Newton chunk highest."""
        from src.core.config import Settings
        cfg = Settings(use_stub_reranker=False, qdrant_in_memory=True)
        from src.pdf_ingestion.reranker import CrossEncoderReranker
        reranker = CrossEncoderReranker(cfg.reranker_model)

        chunks = _make_chunks([
            "Thermodynamics is the study of heat transfer.",
            "Newton's first law: an object at rest stays at rest unless acted on by a force.",
            "Quantum mechanics describes behavior at atomic scales.",
        ])
        result = reranker.rerank("What is Newton's first law?", chunks, top_k=1)
        assert "Newton" in result[0]["text"]
