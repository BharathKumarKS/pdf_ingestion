#!/usr/bin/env python3
"""How many eval queries do we need? Computed from real per-query results.

A paired comparison needs N ≈ (z_a + z_b)^2 * sigma_d^2 / d^2, where sigma_d is the SD of
the PER-QUERY DIFFERENCE between two configurations -- not the SD of the scores. If two
configurations agree on most queries, sigma_d is small and N is small.

A "run" is a results JSON (data/eval_results/*.json) plus a boundary within it. The merge-A/B
files store, per query, the retrieved page set at each pipeline boundary (`pages`, keyed by
boundary name) and the final top-20 (`top20_pages`). A spec is therefore:

    results.json              -> the file's final top-20 (its headline R@20)
    results.json:BOUNDARY     -> recall@k at that boundary, e.g. B5b_retriever_top20

Per-query recall is reconstructed from the stored page sets against the ground-truth
`relevant_pages` in --queries (the result files carry no per-query metrics of their own).

Usage:
    # merge comparison: ColBERT-outer vs 3-way RRF, final R@20
    uv run python scripts/required_n.py \
        data/eval_results/merge-ab_colbert_2026-10-06.json \
        data/eval_results/merge-ab_rrf3_2026-10-06.json --delta 0.05

    # reranker comparison: the retriever's own top-20 vs after the cross-encoder, one run
    uv run python scripts/required_n.py \
        data/eval_results/merge-ab_rrf3_2026-10-06.json:B5b_retriever_top20 \
        data/eval_results/merge-ab_rrf3_2026-10-06.json:B6_rerank_20 --delta 0.083
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from pathlib import Path


def _pages(value) -> set[int]:
    """A stored page set is a list, or a str repr of a Python set ('{30, 35, ...}')."""
    if isinstance(value, str):
        return set(ast.literal_eval(value))
    return set(value)


def per_query_recall(spec: str, queries: Path, k: int = 20) -> dict[str, float]:
    """id -> recall@k for one run, reconstructed from the stored page sets.

    spec is 'results.json' (final top-20) or 'results.json:BOUNDARY'.
    """
    path, _, boundary = spec.partition(":")
    d = json.loads(Path(path).read_text())
    rel = {e["id"]: set(e.get("relevant_pages") or [])
           for e in json.loads(queries.read_text())}
    out: dict[str, float] = {}
    for r in d["per_query"]:
        relevant = rel.get(r["id"])
        if not relevant:
            continue
        got = _pages(r["pages"][boundary] if boundary else r["top20_pages"])
        out[r["id"]] = len(got & relevant) / len(relevant)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("a", help="run A: results.json[:BOUNDARY]")
    p.add_argument("b", help="run B: results.json[:BOUNDARY]")
    p.add_argument("--queries", default="data/eval_queries.json",
                   help="ground-truth query file (relevant_pages)")
    p.add_argument("--delta", type=float, default=0.05,
                   help="effect size you want to detect (default 0.05 recall@20)")
    p.add_argument("--k", type=int, default=20)
    args = p.parse_args()

    A = per_query_recall(args.a, Path(args.queries), args.k)
    B = per_query_recall(args.b, Path(args.queries), args.k)
    shared = sorted(set(A) & set(B))
    if len(shared) < 5:
        print(f"only {len(shared)} shared queries — cannot estimate; check the JSON shape")
        print(f"  keys in {args.a}: {list(A)[:5]}")
        return 1

    diffs = [A[q] - B[q] for q in shared]
    n = len(diffs)
    mean_d = sum(diffs) / n
    var_d = sum((x - mean_d) ** 2 for x in diffs) / (n - 1) if n > 1 else 0.0
    sd_d = math.sqrt(var_d)

    mean_a = sum(A[q] for q in shared) / n
    mean_b = sum(B[q] for q in shared) / n
    sd_a = math.sqrt(sum((A[q] - mean_a) ** 2 for q in shared) / (n - 1))
    sd_b = math.sqrt(sum((B[q] - mean_b) ** 2 for q in shared) / (n - 1))
    cov = sum((A[q] - mean_a) * (B[q] - mean_b) for q in shared) / (n - 1)
    corr = cov / (sd_a * sd_b) if sd_a and sd_b else float("nan")

    z_a, z_b = 1.959964, 0.8416212   # alpha=0.05 two-sided, power=0.80
    need = (z_a + z_b) ** 2 * var_d / (args.delta ** 2)

    print(f"shared queries          : {n}")
    print(f"mean difference         : {mean_d:+.4f}")
    print(f"SD of per-query scores  : {sd_a:.4f}")
    print(f"SD of per-query DIFF    : {sd_d:.4f}   <-- this is what matters")
    print(f"correlation of the two  : {corr:.3f}")
    print()
    print(f"to detect a difference of {args.delta:+.3f} at alpha=0.05, power=0.80:")
    print(f"    required N ≈ {math.ceil(need)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
