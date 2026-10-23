#!/usr/bin/env python
"""§I58 — is the gold set still VALID for the new index, or does it need rebuilding?

The question: the labels were authored while `knowledge_base` (the deployed index, doc `6d55c52b`)
was live. `knowledge_base_v2` (doc `7ba61432`) is a re-ingest of the SAME PDF, with a different
chunker run, a different chunk count (3,796 vs 5,051) and the §I21/§E5 content filter applied.

If a labelled page has no retrievable chunk in an index, **no retriever can ever reach it** and the
query's achievable maximum falls below 1 — the metric is capped by the index, not by the system.
This probe measures that cap per query, per index, instead of arguing about it.

⚠️ It measures the *ceiling*, not the score. A query at achievable-max 1.0 is measurable; a query at
0.5 cannot exceed 0.5 however good the system gets.

It reads SQLite only. No Qdrant, no cluster, no LLM.

Run:
    unset PYTHONPATH && uv run python logs/p1/step10/eval_set_index_validity.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/eval_set_index_validity.json"

OLD_DOC = "6d55c52b"      # the deployed index's document  (knowledge_base)
NEW_DOC = "7ba61432"      # the rebuilt index's document    (knowledge_base_v2)
TYPES = ("factual", "multihop", "overview")


def reachable_pages(document_prefix: str, lo: int, hi: int) -> tuple[set[int], Counter]:
    """Pages a retriever can actually return for one document, under the live retrieval filter.

    The filter is `store.py:389-402`: `page_number >= min_content_page`, `<= max_content_page`, and
    `is_content is not False`. Reproduced here rather than assumed.
    """
    from sqlmodel import Session, select

    from src.core.config import get_settings
    from src.core.database import Chunk, get_engine

    cfg = get_settings()
    with Session(get_engine(cfg)) as session:
        rows = session.exec(
            select(Chunk).where(Chunk.document_id.like(f"{document_prefix}%"))  # type: ignore[attr-defined]
        ).all()
    pages: set[int] = set()
    per_page: Counter = Counter()
    for c in rows:
        pg = c.page_number
        if pg is None or c.is_content is False:
            continue
        if lo > 0 and pg < lo:
            continue
        if hi > 0 and pg > hi:
            continue
        pages.add(int(pg))
        per_page[int(pg)] += 1
    return pages, per_page


def achievable(labels: list[int], pages: set[int], window: int = 0) -> int:
    """How many labels a retriever can reach. `window` tolerates the §D4 ±1 chunk-boundary fuzz."""
    hit = 0
    for lab in labels:
        if any((lab + d) in pages for d in range(-window, window + 1)):
            hit += 1
    return hit


def main() -> int:
    from src.core.config import get_settings

    cfg = get_settings()
    lo, hi = cfg.min_content_page, cfg.max_content_page
    print(f"retrieval window: [{lo}, {hi}]  (0 = unbounded)")

    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])

    old_pages, old_per = reachable_pages(OLD_DOC, lo, hi)
    new_pages, new_per = reachable_pages(NEW_DOC, lo, hi)
    print(f"OLD ({OLD_DOC}): {len(old_pages)} reachable pages, {sum(old_per.values())} chunks")
    print(f"NEW ({NEW_DOC}): {len(new_pages)} reachable pages, {sum(new_per.values())} chunks")

    rows = []
    for q in queries:
        labels = [int(p) for p in q["relevant_pages"]]
        o0, n0 = achievable(labels, old_pages), achievable(labels, new_pages)
        o1, n1 = achievable(labels, old_pages, 1), achievable(labels, new_pages, 1)
        rows.append({
            "id": q["id"], "query_type": q.get("query_type"), "n_labels": len(labels),
            "old_reachable": o0, "new_reachable": n0,
            "old_achievable_max": round(o0 / len(labels), 6),
            "new_achievable_max": round(n0 / len(labels), 6),
            "old_achievable_max_pm1": round(o1 / len(labels), 6),
            "new_achievable_max_pm1": round(n1 / len(labels), 6),
            "unreachable_new_exact": sorted(
                {lab for lab in labels if lab not in new_pages})[:12],
            "unreachable_new_pm1": sorted(
                {lab for lab in labels
                 if not any((lab + d) in new_pages for d in (-1, 0, 1))})[:12],
        })

    def block(subset: list[dict]) -> dict:
        if not subset:
            return {}
        nm = [r["new_achievable_max"] for r in subset]
        om = [r["old_achievable_max"] for r in subset]
        return {
            "queries": len(subset),
            "old_achievable_max": {"min": min(om), "median": round(statistics.median(om), 4),
                                   "max": max(om), "mean": round(statistics.mean(om), 4)},
            "new_achievable_max": {"min": min(nm), "median": round(statistics.median(nm), 4),
                                   "max": max(nm), "mean": round(statistics.mean(nm), 4)},
            "new_achievable_max_pm1_mean": round(
                statistics.mean(r["new_achievable_max_pm1"] for r in subset), 4),
            "queries_capped_new": sum(1 for r in subset if r["new_achievable_max"] < 1.0),
            "queries_capped_new_pm1": sum(1 for r in subset if r["new_achievable_max_pm1"] < 1.0),
            "queries_capped_old": sum(1 for r in subset if r["old_achievable_max"] < 1.0),
            "labels_total": sum(r["n_labels"] for r in subset),
            "labels_unreachable_new": sum(r["n_labels"] - r["new_reachable"] for r in subset),
            "labels_unreachable_new_pm1": sum(
                r["n_labels"] - round(r["new_achievable_max_pm1"] * r["n_labels"]) for r in subset),
        }

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/eval_set_index_validity.py",
            "what": ("§I58 — the gold set's achievable maximum per query, per index. Measures the "
                     "CEILING the index imposes, not the score."),
            "old_document": OLD_DOC, "new_document": NEW_DOC,
            "retrieval_window": [lo, hi],
            "filter_reproduced": ("store.py:389-402 — page_number in [min_content_page, "
                                  "max_content_page] and is_content is not False"),
            "no_llm_calls": True, "no_cluster": True,
            "pm1": "±1 page, tolerating the §D4 chunk-boundary fuzz",
        },
        "summary": {"all": block(rows),
                    "by_type": {t: block([r for r in rows if r["query_type"] == t])
                                for t in TYPES}},
        "queries": rows,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    a = out["summary"]["all"]
    print(f"\n=== achievable maximum, {a['queries']} queries / {a['labels_total']} labels ===")
    print(f"  OLD index: mean {a['old_achievable_max']['mean']:.4f}  "
          f"min {a['old_achievable_max']['min']:.4f}  capped {a['queries_capped_old']}")
    print(f"  NEW index: mean {a['new_achievable_max']['mean']:.4f}  "
          f"min {a['new_achievable_max']['min']:.4f}  capped {a['queries_capped_new']}")
    print(f"  NEW ±1:    mean {a['new_achievable_max_pm1_mean']:.4f}  "
          f"capped {a['queries_capped_new_pm1']}")
    print(f"  labels unreachable in NEW: {a['labels_unreachable_new']} exact / "
          f"{a['labels_unreachable_new_pm1']} with ±1")
    for t, b in out["summary"]["by_type"].items():
        if b:
            print(f"    {t:9s} n={b['queries']:<4} new mean {b['new_achievable_max']['mean']:.4f} "
                  f"capped {b['queries_capped_new']}  (±1 capped {b['queries_capped_new_pm1']})")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
