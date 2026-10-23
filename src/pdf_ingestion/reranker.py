"""
Cross-encoder re-ranker — Phase 4.

Re-scores retrieved chunks by jointly encoding (query, passage) pairs,
catching relevance that embedding cosine similarity misses (e.g. vocabulary
mismatch between query "Newton's first law" and Feynman's "law of inertia").

Model: BAAI/bge-reranker-v2-m3 (cfg.reranker_model). Runs locally or is served by
the cluster (SV_RERANK_URL); CPU-friendly, <1s/query.
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
    Loads the configured cross-encoder (default BAAI/bge-reranker-v2-m3) once and
    re-scores (query, passage) pairs. Higher score = more relevant.
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


# ── SV Cluster cross-encoder reranker ─────────────────────────────────────


class ClusterCrossEncoderReranker:
    """
    Calls the SV cluster reranker endpoint instead of loading locally.
    Fixes the HuggingFace lock-file issue permanently.

    RANK endpoint (sorted results):
        POST http://10.0.10.70:8000/rerank/v1/rank
        {"model": "BAAI/bge-reranker-v2-m3",
         "query": "...", "documents": ["doc1", ...], "top_k": 20}
    Response:
        {"results": [{"corpus_id": 0, "score": 0.95, "text": "..."}, ...]}

    NOTE: the truncation parameter is `top_k`, NOT `top_n` — verified against the live
    cluster 2026-10-06: with `top_n=2` over 6 documents the server returned all 6 (the key
    is ignored), while `top_k=2` returned 2. Harmless here only because `rerank()` below
    slices to `top_k` itself; sending `top_n` just moves every candidate over the wire.

    ⚠️ **This class SWALLOWS its own failures** (§I55): `rerank()` catches every exception and
    returns the pool **unranked**, so any metric that depends on the reranked ORDER (R@20, NDCG)
    is computed on the retrieval order with no trace. The fallback is now **counted**
    (`self.fallbacks`) and the last error kept (`self.last_fallback`), so a caller can see it and
    refuse to certify a reranked metric. The counter is per-instance and `get_reranker()` is a
    singleton, so a caller detects a fallback for ONE query by comparing the counter before and
    after its `rerank()` call (`scripts/evaluate_rag.py:run_retrieval`).
    """

    def __init__(self, url: str, model: str) -> None:
        self._url   = url
        self._model = model
        # §I55 — the swallow count. Never reset implicitly: a run's total is `fallbacks`, and a
        # per-query delta is what tells one query's call apart from the run's.
        self.fallbacks: int = 0
        self.last_fallback: str | None = None
        logger.info("ClusterCrossEncoderReranker: {} @ {}", model, url)

    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        if not chunks:
            return []
        import httpx
        documents = [c.get("text", "") for c in chunks]
        payload = {
            "model":     self._model,
            "query":     query,
            "documents": documents,
            "top_k":     min(top_k, len(chunks)),
        }
        try:
            resp = httpx.post(self._url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", data) if isinstance(data, dict) else data

            # Handle multiple response formats:
            # Format A: [{"index": 0, "relevance_score": 0.9}, ...]  — vLLM standard
            # Format B: [{"score": 0.9}, ...]                        — infinity-emb (no index, score-sorted)
            # Format C: [0.9, 0.23, ...]                             — raw score list in input order
            if results and isinstance(results[0], dict):
                score_key = "relevance_score" if "relevance_score" in results[0] else "score"
                # The mapping back to the input chunk depends on the server's response shape.
                # Prefer an explicit index field; ONLY fall back to positional mapping when the
                # server returns scores in input order (no index field at all).
                idx_key = next((k for k in ("corpus_id", "index", "id") if k in results[0]), None)
                if idx_key is not None:
                    # Server tells us which input document each score belongs to.
                    ranked = []
                    for r in results:
                        i = r.get(idx_key)
                        if isinstance(i, int) and 0 <= i < len(chunks):
                            ranked.append(chunks[i])
                        if len(ranked) >= top_k:
                            break
                    top_score = results[0].get(score_key, 0)
                else:
                    # No index field: the server returned a score per input document, in input
                    # order. Sorting by score is the only correct interpretation.
                    pairs = sorted(enumerate(results), key=lambda x: x[1].get(score_key, 0), reverse=True)
                    ranked = [chunks[i] for i, _ in pairs[:top_k]]
                    top_score = pairs[0][1].get(score_key, 0) if pairs else 0
            else:
                # Format C: list of floats in input order — sort chunks by score
                scores = [float(r) for r in results]
                pairs = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
                ranked = [chunks[i] for i, _ in pairs[:top_k]]
                top_score = pairs[0][1] if pairs else 0

            # §I55, SECOND PATH — a 200 that parses CLEANLY and yields an EMPTY ranking. Measured
            # 2026-10-22 (probe, session 10): `{"results": []}` and `{}` (no `results` key) both
            # return **0 chunks**, move no counter, and log nothing above DEBUG — so the query is
            # averaged in as a TOTAL MISS while the artifact still says
            # `reranked_metrics_valid: true`. Same class as the swallowed exception below and
            # strictly worse: it returns *nothing* rather than the unranked pool, so every metric
            # for that query is 0 by construction. Raised into the SAME handler — one counter, one
            # log line, one disposition. (A pool of 100 documents cannot legitimately rank 0.)
            if not ranked:
                raise ValueError(
                    f"reranker returned an EMPTY ranking for a {len(chunks)}-document pool"
                )

            logger.debug(
                "Cluster reranker: top score {:.3f} (kept {}/{})",
                top_score, len(ranked), len(chunks),
            )
            return ranked
        except Exception as exc:
            # LOUD on purpose: this returns UNRANKED results. Downstream metrics (Precision@k,
            # NDCG@k) are meaningless when this fires, and the artifact would otherwise still
            # record reranker.enabled=true. Do not downgrade this to debug/warning.
            # §I55 — COUNTED as well as logged: a log line nobody reads is not a control, and
            # `evaluate_rag.py` reads this counter to refuse to certify a reranked metric.
            self.fallbacks += 1
            self.last_fallback = f"{type(exc).__name__}: {exc}"
            logger.error(
                "RERANKER DISABLED — cluster rerank call to {} failed ({}: {}). "
                "Returning UNRANKED results in original retrieval order; "
                "Precision@k/NDCG@k will be measured on unranked output. [fallback #{}]",
                self._url, type(exc).__name__, exc, self.fallbacks,
            )
            return chunks[:top_k]


# ── Singleton ──────────────────────────────────────────────────────────────

_reranker_instance: StubReranker | CrossEncoderReranker | None = None


def get_reranker(
    settings: Settings | None = None,
) -> StubReranker | ClusterCrossEncoderReranker | CrossEncoderReranker:
    global _reranker_instance
    if _reranker_instance is None:
        cfg = settings or get_settings()
        if not cfg.reranker_enabled or cfg.use_stub_reranker:
            _reranker_instance = StubReranker()
        elif cfg.sv_rerank_url:
            _reranker_instance = ClusterCrossEncoderReranker(
                url=cfg.sv_rerank_url,
                model=cfg.reranker_model,
            )
        else:
            _reranker_instance = CrossEncoderReranker(cfg.reranker_model)
    return _reranker_instance


def reset_reranker() -> None:
    global _reranker_instance
    _reranker_instance = None
