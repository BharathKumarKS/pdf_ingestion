"""§I55 — the cross-encoder reranker swallows its own failures, and the eval must not certify it.

`ClusterCrossEncoderReranker.rerank` catches EVERY exception, logs `RERANKER DISABLED`, and returns
the pool **unranked** — while the eval artifact recorded `reranker.enabled=true` and said nothing.
Measured 2026-10-22: 1/133 v2 queries (`gold-004`, HTTP 500) were rejected, deterministically per
query, so it does not average out within a query.

The fix has three parts, all pinned here:
  1. the fallback is COUNTED (`reranker.fallbacks`, `reranker.last_fallback`);
  2. `run_retrieval` detects it per query (`reranker_fallback`) and `evaluate_query` carries it up;
  3. `evaluate_rag` collects the affected query ids so the artifact can refuse to certify a
     reranked metric (`reranker.reranked_metrics_valid=false`, non-zero exit).

Every guard below is written to be able to FAIL: delete the counter increment and test 1 fails;
make `run_retrieval` report `False` unconditionally and test 3 fails.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from src.core.config import Settings

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_rag.py"


@pytest.fixture(scope="module")
def ev():
    """Load evaluate_rag.py as a module so its functions can be tested directly."""
    spec = importlib.util.spec_from_file_location("evaluate_rag_i55_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cfg():
    return Settings(
        hyde_enabled=False, reranker_enabled=True, reranker_fetch_k=100, reranker_top_k=20,
        qdrant_in_memory=True,
    )


# ── 1. the reranker counts the swallow ────────────────────────────────────────────────────────

def test_cluster_reranker_counts_fallback_and_returns_unranked(monkeypatch):
    import httpx

    from src.pdf_ingestion.reranker import ClusterCrossEncoderReranker

    def boom(*_a, **_k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", boom)
    r = ClusterCrossEncoderReranker(url="http://10.0.0.1:8000/rerank/v1/rank", model="m")
    chunks = [{"text": f"doc{i}"} for i in range(5)]

    out = r.rerank("q", chunks, top_k=3)

    assert r.fallbacks == 1, "the swallow must be COUNTED, not only logged"
    assert "ConnectError" in (r.last_fallback or "")
    # Unranked means the ORIGINAL retrieval order, truncated — not a reordering.
    assert out == chunks[:3]


def test_cluster_reranker_no_fallback_on_success(monkeypatch):
    import httpx

    from src.pdf_ingestion.reranker import ClusterCrossEncoderReranker

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"corpus_id": 1, "score": 0.9}, {"corpus_id": 0, "score": 0.1}]}

    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: FakeResp())
    r = ClusterCrossEncoderReranker(url="http://x", model="m")
    chunks = [{"text": "a"}, {"text": "b"}]

    out = r.rerank("q", chunks, top_k=2)

    assert r.fallbacks == 0
    assert r.last_fallback is None
    assert out[0]["text"] == "b", "a successful rerank must actually reorder"


@pytest.mark.parametrize("payload", [{"results": []}, {}], ids=["empty-results", "no-results-key"])
def test_cluster_reranker_counts_an_empty_200_response(monkeypatch, payload):
    """§I55, SECOND PATH — a 200 that parses CLEANLY but ranks NOTHING is a failure, not a result.

    Measured 2026-10-22: `{"results": []}` and `{}` both returned 0 chunks, moved no counter, and
    logged nothing above DEBUG — so `evaluate_rag` averaged the query in as a TOTAL MISS while the
    artifact still said `reranked_metrics_valid: true`. The disposition must be the same as the
    swallowed exception: count it, log it, and fall back to the UNRANKED pool (never to nothing).
    """
    import httpx

    from src.pdf_ingestion.reranker import ClusterCrossEncoderReranker

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: FakeResp())
    r = ClusterCrossEncoderReranker(url="http://x", model="m")
    chunks = [{"text": f"doc{i}"} for i in range(5)]

    out = r.rerank("q", chunks, top_k=3)

    assert r.fallbacks == 1, "an empty ranking must be COUNTED as a fallback"
    assert "EMPTY ranking" in (r.last_fallback or "")
    assert out == chunks[:3], "must fall back to the UNRANKED pool, not return nothing"


# ── 2. run_retrieval detects it per query; evaluate_query carries it up ───────────────────────

class _Store:
    def __init__(self, hits):
        self._hits = hits

    def search_with_das(self, *_a, **_k):
        return [dict(h) for h in self._hits]


class _Emb:
    def embed_query(self, _text):
        return [0.0] * 1024


class _Reranker:
    """A stand-in whose swallow is switchable — the counter contract of the real class."""

    def __init__(self, fall_back: bool):
        self.fallbacks = 0
        self.last_fallback = None
        self._fall_back = fall_back

    def rerank(self, _q, chunks, top_k):
        if self._fall_back:
            self.fallbacks += 1
            self.last_fallback = "HTTPStatusError: 500"
            return chunks[:top_k]
        return list(reversed(chunks))[:top_k]


def _hits(n: int = 5) -> list[dict]:
    return [{"text": f"d{i}", "score": 0.5, "page_number": i + 1} for i in range(n)]


def test_run_retrieval_flags_reranker_fallback(ev, cfg):
    out = ev.run_retrieval("q", _Store(_hits()), _Emb(), _Reranker(fall_back=True), cfg, "global", 0.0)
    assert out["reranker_fallback"] is True


def test_run_retrieval_no_flag_when_rerank_succeeds(ev, cfg):
    out = ev.run_retrieval("q", _Store(_hits()), _Emb(), _Reranker(fall_back=False), cfg, "global", 0.0)
    assert out["reranker_fallback"] is False


def test_evaluate_query_propagates_the_flag(ev, cfg):
    args = argparse.Namespace(
        skip_visual=True, retrieval_only=True, judged_context_precision=False,
        tenant="global", score_threshold=0.0,
    )
    query = {"id": "gold-004", "query": "q", "query_type": "factual", "relevant_pages": [1, 2]}

    res = ev.evaluate_query(query, _Store(_hits()), _Emb(), _Reranker(fall_back=True), cfg, None, args)

    assert res["reranker_fallback"] is True
    assert ev.collect_reranker_fallbacks([res]) == ["gold-004"]


# ── 3. the run-level collection the artifact is built from ────────────────────────────────────

def test_collect_reranker_fallbacks_is_empty_when_nothing_fell_back(ev):
    results = [{"id": "a"}, {"id": "b", "reranker_fallback": False}]
    assert ev.collect_reranker_fallbacks(results) == []


def test_collect_reranker_fallbacks_names_only_the_affected_queries(ev):
    results = [
        {"id": "gold-001", "reranker_fallback": False},
        {"id": "gold-004", "reranker_fallback": True},
        {"id": "gold-005", "reranker_fallback": True},
    ]
    assert ev.collect_reranker_fallbacks(results) == ["gold-004", "gold-005"]
