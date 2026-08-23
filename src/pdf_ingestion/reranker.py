"""
Cross-encoder re-ranker — Phase 4.

Re-scores retrieved chunks by jointly encoding (query, passage) pairs,
catching relevance that embedding cosine similarity misses (e.g. vocabulary
mismatch between query "Newton's first law" and Feynman's "law of inertia").

Model: cross-encoder/ms-marco-MiniLM-L-6-v2  (~80 MB, CPU-friendly, <1s/query)
"""
from __future__ import annotations

from loguru import logger

from src.core.config import Settings, get_settings


class StubReranker:
    """Returns chunks in original order — no model needed for tests."""

    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        return chunks[:top_k]


class CrossEncoderReranker:
    """
    Loads cross-encoder/ms-marco-MiniLM-L-6-v2 once and re-scores
    (query, passage) pairs. Higher score = more relevant.
    """

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading cross-encoder model: {}", model_name)
        self._model = CrossEncoder(model_name)
        logger.info("Cross-encoder ready")

    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        if not chunks:
            return []
        pairs = [(query, c.get("text", "")) for c in chunks]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
        logger.debug(
            "Re-ranker: top score {:.3f}, bottom score {:.3f} (kept {}/{})",
            ranked[0][0], ranked[-1][0], min(top_k, len(ranked)), len(ranked),
        )
        return [c for _, c in ranked[:top_k]]


# ── Singleton ──────────────────────────────────────────────────────────────

_reranker_instance: StubReranker | CrossEncoderReranker | None = None


def get_reranker(settings: Settings | None = None) -> StubReranker | CrossEncoderReranker:
    global _reranker_instance
    if _reranker_instance is None:
        cfg = settings or get_settings()
        if not cfg.reranker_enabled or cfg.use_stub_reranker:
            _reranker_instance = StubReranker()
        else:
            _reranker_instance = CrossEncoderReranker(cfg.reranker_model)
    return _reranker_instance


def reset_reranker() -> None:
    global _reranker_instance
    _reranker_instance = None
