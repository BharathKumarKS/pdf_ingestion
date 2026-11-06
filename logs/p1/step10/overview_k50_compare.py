"""Compare the overview k=50 generator run against the k=20 baseline (v3_judged_full).

Reads both artifacts, joins per query id, and reports the paired deltas on the GENERATOR metrics
(faithfulness = primary) plus the retrieval metrics. Prints a verdict under the pre-registered rule.

Run:  .venv/bin/python logs/p1/step10/overview_k50_compare.py
"""
from __future__ import annotations

import glob
import json
import statistics
from pathlib import Path

RES = Path("data/eval_results")


def load(pattern: str) -> dict:
    files = sorted(glob.glob(str(RES / pattern)))
    if not files:
        raise SystemExit(f"no artifact matching {pattern}")
    p = files[-1]
    print(f"  reading {p}")
    return json.loads(Path(p).read_text())


def by_id(doc: dict) -> dict:
    return {r["id"]: r for r in doc["results"]}


base = load("v3_judged_full_*.json")          # k=20
k50 = load("overview_k50_*.json")             # k=50
B, K = by_id(base), by_id(k50)
common = sorted(set(B) & set(K))
print(f"\noverview queries paired: {len(common)} (baseline {len(B)}, k50 {len(K)})")


def _ci(diffs):
    n = len(diffs)
    m = statistics.mean(diffs)
    half = 1.96 * statistics.stdev(diffs) / (n ** 0.5)
    return m, [m - half, m + half]


def paired(metric: str):
    a, b = [], []
    for qid in common:
        va = (B[qid].get("generation") or {}).get(metric)
        vb = (K[qid].get("generation") or {}).get(metric)
        if va is None or vb is None:
            continue
        a.append(va); b.append(vb)
    diffs = [y - x for x, y in zip(a, b)]
    if len(diffs) < 2:
        return None
    m, ci = _ci(diffs)
    return {"n": len(diffs), "k20": statistics.mean(a), "k50": statistics.mean(b),
            "delta": m, "ci": ci, "resolved": ci[0] > 0 or ci[1] < 0,
            "wins": sum(1 for d in diffs if d > 0), "losses": sum(1 for d in diffs if d < 0)}


def paired_retrieval(metric: str):
    a, b = [], []
    for qid in common:
        va = (B[qid].get("metrics") or {}).get(metric)
        vb = (K[qid].get("metrics") or {}).get(metric)
        if va is None or vb is None:
            continue
        a.append(va); b.append(vb)
    diffs = [y - x for x, y in zip(a, b)]
    if len(diffs) < 2:
        return None
    m, ci = _ci(diffs)
    return {"n": len(diffs), "k20": statistics.mean(a), "k50": statistics.mean(b),
            "delta": m, "ci": ci, "resolved": ci[0] > 0 or ci[1] < 0}


print("\n=== GENERATOR metrics (paired, k50 − k20) ===")
for metric in ("faithfulness", "answer_relevance", "citation_accuracy"):
    r = paired(metric)
    if not r:
        print(f"  {metric}: insufficient overlap"); continue
    verdict = "RESOLVED" if r["resolved"] else "unresolved"
    print(f"  {metric:18s} k20={r['k20']:.4f} k50={r['k50']:.4f} "
          f"Δ={r['delta']:+.4f} CI[{r['ci'][0]:+.4f},{r['ci'][1]:+.4f}] {verdict} "
          f"({r['wins']}W/{r['losses']}L, n={r['n']})")

print("\n=== RETRIEVAL metrics (paired, k50 − k20) ===")
for metric in ("recall_at_20", "recall_at_50", "ndcg_at_20", "ndcg_at_50", "context_precision"):
    r = paired_retrieval(metric)
    if not r:
        print(f"  {metric}: n/a"); continue
    verdict = "RESOLVED" if r["resolved"] else "unresolved"
    print(f"  {metric:18s} k20={r['k20']:.4f} k50={r['k50']:.4f} "
          f"Δ={r['delta']:+.4f} CI[{r['ci'][0]:+.4f},{r['ci'][1]:+.4f}] {verdict}")

# guard: the k=50 arm must have a wider cut
sizes = {len(r.get("top_chunks") or []) for r in K.values()}
print(f"\n  (top_chunks sizes recorded: {sorted(sizes)})")
