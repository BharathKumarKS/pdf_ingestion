"""Regression tests for the retrieval metrics (P0-7).

``Precision@top_k`` divided by a fixed ``top_k``, which caps it at
``min(|relevant|, top_k)/top_k`` — about 0.10 for a gold set whose median query
has 2 labelled pages. It therefore read as failure while sitting at its own
ceiling. It is replaced by:

  * ``Recall@top_k`` — denominator is ``|relevant|``, well-conditioned at any
    ground-truth size; and
  * ``Hit@top_k``    — did any labelled page reach the final top-k.

``Recall@fetch_k`` (the candidate pool) is kept, so the gap between the two
quantifies exactly what ranking discards.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.core.config import Settings

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_rag.py"


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("evaluate_rag_metrics_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cfg():
    return Settings(reranker_fetch_k=100, reranker_top_k=20)


def _retrieval(pages: list[int]) -> dict:
    hits = [{"page_number": p} for p in pages]
    return {"hits": hits, "hits_above": hits, "reranked": hits}


def test_recall_at_top_k_uses_ground_truth_denominator(ev, cfg):
    """Both labelled pages in the top-20 -> 1.0, NOT 2/20 = 0.10."""
    m = ev.compute_retrieval_metrics(_retrieval([5, 9, 1]), [5, 9], cfg)
    assert m["recall_at_20"] == 1.0
    assert m["hit_at_20"] == 1.0


def test_recall_at_top_k_partial(ev, cfg):
    """4 labelled, 2 present -> 0.5 (the old metric would have said 2/20 = 0.10)."""
    m = ev.compute_retrieval_metrics(_retrieval([5, 9, 1, 2]), [5, 9, 30, 40], cfg)
    assert m["recall_at_20"] == 0.5


def test_hit_at_top_k_zero_when_nothing_relevant(ev, cfg):
    m = ev.compute_retrieval_metrics(_retrieval([1, 2, 3]), [50, 60], cfg)
    assert m["hit_at_20"] == 0.0
    assert m["recall_at_20"] == 0.0


def test_precision_is_no_longer_emitted(ev, cfg):
    m = ev.compute_retrieval_metrics(_retrieval([5]), [5], cfg)
    assert "precision_at_20" not in m
    assert {"recall_at_100", "recall_at_20", "hit_at_20", "mrr", "ndcg_at_20"} <= set(m)


def test_pool_vs_final_recall_gap_is_visible(ev, cfg):
    """A page in the pool but dropped by ranking shows up as the recall gap."""
    pages = [1, 2, 3, 4, 5]
    retrieval = {
        "hits": [{"page_number": p} for p in pages],          # pool has all 5
        "hits_above": [{"page_number": p} for p in pages],
        "reranked": [{"page_number": p} for p in pages[:2]],  # final top-2 only
    }
    m = ev.compute_retrieval_metrics(retrieval, [1, 5], cfg)
    assert m["recall_at_100"] == 1.0  # p5 is in the candidate pool
    assert m["recall_at_20"] == 0.5   # ...but ranking discarded it


# ── Context precision: CHUNK units, so not pinned at the page-count ceiling ───

def test_context_precision_counts_chunks_not_pages(ev, cfg):
    """Denominator is the retrieved chunks; the unit is the chunk.

    This does NOT lift the metric far on a real corpus: measured 0.05-0.10, because
    top_k=20 pulls chunks from many pages while the gold set labels 1-3 of them. It
    is a diagnostic of how much of the context window is not gold, not a score with
    headroom. The judged (RAGAS-style) variant is the one that can move.
    """
    m = ev.compute_retrieval_metrics(_retrieval([5, 5, 9, 9]), [5, 9], cfg)
    assert m["context_precision"] == 1.0          # every chunk from a labelled page
    assert m["recall_at_20"] == 1.0

    m2 = ev.compute_retrieval_metrics(_retrieval([5, 9, 1, 2]), [5, 9], cfg)
    assert m2["context_precision"] == 0.5         # 2 of 4 chunks


def test_context_precision_zero_when_nothing_relevant(ev, cfg):
    m = ev.compute_retrieval_metrics(_retrieval([1, 2, 3, 4]), [50], cfg)
    assert m["context_precision"] == 0.0


def test_context_precision_none_without_chunks(ev, cfg):
    m = ev.compute_retrieval_metrics(_retrieval([]), [50], cfg)
    assert m["context_precision"] is None


# ── Judged (RAGAS-style) context precision ───────────────────────────────────

def test_judged_context_precision_all_and_none(ev):
    chunks = [{"text": f"c{i}"} for i in range(4)]
    assert ev.compute_context_precision_judged("q", chunks, lambda p: "YES") == 1.0
    assert ev.compute_context_precision_judged("q", chunks, lambda p: "NO") == 0.0


def test_judged_context_precision_is_rank_weighted(ev):
    """Only the 4th chunk useful -> precision@4 = 1/4, and that is the only term."""
    chunks = [{"text": f"c{i}"} for i in range(4)]
    judge = lambda p: "YES" if p.rstrip().endswith("c3") else "NO"  # noqa: E731
    assert ev.compute_context_precision_judged("q", chunks, judge) == 0.25


def test_judged_context_precision_none_without_chunks(ev):
    assert ev.compute_context_precision_judged("q", [], lambda p: "YES") is None
