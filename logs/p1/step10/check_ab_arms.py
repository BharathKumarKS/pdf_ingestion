#!/usr/bin/env python3
"""Step 10 §2 arm verifier — the checks the plan requires BEFORE any score is read.

Implements `.hermes/plans/2026-10-18-p1-step10-preregistration.md` §3, §4 and §7:

  1. both arm JSONs exist and contain the SAME query count (133 text queries);
  2. §D10 stability: `B5b_retriever_top20` must be IDENTICAL per query across the two arms —
     RRF is not bit-reproducible at pool level, so B4/B5 may differ on a handful of queries,
     but if B5b moved the A/B is VOID and must be re-run, not interpreted;
  3. same collection / same HyDE cache / same query file recorded in both config blocks;
  4. every R@20 reported raw AND divided by the §D9 ceiling — note the ceiling is
     mean(min(20,|rel|)/|rel|) = 0.8016 for the text lane, NOT the funnel's printed
     "Precision@20 ceiling" (mean min(|rel|,20)/20 = 0.4861), which is a different quantity;
  5. the paired delta with its 95% CI (mean ± 1.96·SD/√n) — `required_n.py` does NOT print a
     CI, so it is computed here, pre-registered in §4;
  6. exploratory per-type subgroups (factual / multihop / overview), clearly not the endpoint.

Exit 0 = the A/B is valid and readable, 1 = void or malformed.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "logs/p1/step10"
RERANK = OUT / "v2_rerank.json"
NORERANK = OUT / "v2_norerank.json"
QUERIES = REPO / "data/eval_queries_v2.json"
TOP_K = 20


def load(path: Path) -> dict:
    if not path.exists():
        print(f"!! missing {path.relative_to(REPO)}")
        sys.exit(1)
    return json.loads(path.read_text())


def pages(value) -> set[int]:
    return set(value or [])


def main() -> int:
    A, B = load(RERANK), load(NORERANK)
    rel = {
        e["id"]: set(e.get("relevant_pages") or [])
        for e in json.loads(QUERIES.read_text())
        if e.get("id") and not e["id"].startswith("_")
    }
    qtype = {
        e["id"]: e.get("query_type", "factual")
        for e in json.loads(QUERIES.read_text())
        if e.get("id") and not e["id"].startswith("_")
    }

    failures: list[str] = []
    print("=" * 88)
    print("STEP 10 §2 — ARM VERIFIER")
    print("=" * 88)

    # ── 1. same query count ───────────────────────────────────────────────
    n_a = A["config"]["n_queries"]
    n_b = B["config"]["n_queries"]
    print(f"\n[1] query count        : rerank={n_a}  no-rerank={n_b}")
    if n_a != n_b:
        failures.append(f"arms have different query counts: {n_a} vs {n_b}")
    if n_a != 133:
        failures.append(f"expected 133 text queries (the plan's operative n), got {n_a}")

    # ── 3. same collection / cache / query file ───────────────────────────
    print(f"\n[3] arm config")
    for label, arm in (("rerank", A), ("no-rerank", B)):
        c = arm["config"]
        print(f"      {label:10} collection={c.get('collection')}  hyde_cache={c.get('hyde_cache')}"
              f"  dense={c.get('dense_vector_name')}  n={c.get('n_queries')}")
        if c.get("collection") != "knowledge_base_v2":
            failures.append(f"{label} arm ran against collection {c.get('collection')!r}, not knowledge_base_v2")
    if A["config"].get("hyde_cache") != B["config"].get("hyde_cache"):
        failures.append("the two arms used DIFFERENT HyDE caches — the A/B is not paired")
    if A["config"].get("dense_vector_name") != B["config"].get("dense_vector_name"):
        failures.append("the two arms used different dense vector slots")

    # ── 2. §D10 stability ─────────────────────────────────────────────────
    pa = {r["id"]: r for r in A["per_query"]}
    pb = {r["id"]: r for r in B["per_query"]}
    shared = sorted(set(pa) & set(pb))
    b5b_moved, b4_moved, b5_moved = [], [], []
    for q in shared:
        if pages(pa[q]["pages"].get("B5b_retriever_top20")) != pages(pb[q]["pages"].get("B5b_retriever_top20")):
            b5b_moved.append(q)
        if pages(pa[q]["pages"].get("B4_rrf_union_100")) != pages(pb[q]["pages"].get("B4_rrf_union_100")):
            b4_moved.append(q)
        if pages(pa[q]["pages"].get("B5_colbert_100")) != pages(pb[q]["pages"].get("B5_colbert_100")):
            b5_moved.append(q)
    print(f"\n[2] §D10 stability (n={len(shared)} shared queries)")
    print(f"      B5b_retriever_top20 moved on {len(b5b_moved)} queries  {b5b_moved[:5]}")
    print(f"      B4_rrf_union_100   moved on {len(b4_moved)} queries (tolerated — §D10)")
    print(f"      B5_colbert_100     moved on {len(b5_moved)} queries (tolerated — §D10)")
    if b5b_moved:
        failures.append(
            f"B5b_retriever_top20 differs between arms on {len(b5b_moved)} queries — the A/B is VOID"
        )

    # ── 4/5. per-query R@20, delta, CI, ceiling ───────────────────────────
    def r20(row: dict) -> float:
        r = rel.get(row["id"]) or set()
        if not r:
            return 0.0
        return len(pages(row["top20_pages"]) & r) / len(r)

    def ceiling(ids) -> float:
        vals = [min(TOP_K, len(rel[i])) / len(rel[i]) for i in ids if rel.get(i)]
        return statistics.mean(vals) if vals else 0.0

    ids = [q for q in shared if rel.get(q)]
    diffs = [r20(pa[q]) - r20(pb[q]) for q in ids]
    n = len(diffs)
    mean_d = statistics.mean(diffs)
    sd_d = statistics.stdev(diffs) if n > 1 else 0.0
    se = sd_d / math.sqrt(n) if n else 0.0
    lo, hi = mean_d - 1.96 * se, mean_d + 1.96 * se
    m_a = statistics.mean(r20(pa[q]) for q in ids)
    m_b = statistics.mean(r20(pb[q]) for q in ids)
    ceil_all = ceiling(ids)

    print(f"\n[4] R@20 (n={n})")
    print(f"      rerank      raw={m_a:.4f}   ÷ceiling({ceil_all:.4f}) = {m_a / ceil_all:.4f}")
    print(f"      no-rerank   raw={m_b:.4f}   ÷ceiling({ceil_all:.4f}) = {m_b / ceil_all:.4f}")

    print(f"\n[5] paired difference (the pre-registered endpoint)")
    print(f"      mean Δ = {mean_d:+.4f}    SD_d = {sd_d:.4f}    SE = {se:.4f}")
    print(f"      95% CI = [{lo:+.4f}, {hi:+.4f}]")
    worse = sum(1 for d in diffs if d < 0)
    better = sum(1 for d in diffs if d > 0)
    print(f"      {worse} worse / {better} better / {n - worse - better} identical")
    if lo > 0:
        verdict = "MET — the reranker wins (CI excludes 0, positive)"
    elif hi < 0:
        verdict = "MET — the reranker LOSES (CI excludes 0, negative) → the arm comes out"
    else:
        verdict = "UNRESOLVED — the CI straddles 0 → keep the reranker enabled, do not extend (§D13)"
    print(f"      VERDICT: {verdict}")

    print(f"\n[6] exploratory per-type (NOT the pre-registered endpoint; no multiplicity control)")
    for t in ("factual", "multihop", "overview"):
        sub = [q for q in ids if qtype.get(q) == t]
        if len(sub) < 2:
            continue
        d = [r20(pa[q]) - r20(pb[q]) for q in sub]
        md = statistics.mean(d)
        sd = statistics.stdev(d)
        s = sd / math.sqrt(len(d))
        c = ceiling(sub)
        ra = statistics.mean(r20(pa[q]) for q in sub)
        rb = statistics.mean(r20(pb[q]) for q in sub)
        mark = "RESOLVED" if (md - 1.96 * s > 0 or md + 1.96 * s < 0) else "unresolved"
        print(f"      {t:9} n={len(sub):3}  Δ={md:+.4f}  CI=[{md - 1.96 * s:+.4f}, {md + 1.96 * s:+.4f}]"
              f"  {mark:10}  R@20 {ra:.4f}→{rb:.4f}  ÷ceiling({c:.4f}) {ra / c:.4f}→{rb / c:.4f}")

    (OUT / "ab_verdict.json").write_text(json.dumps({
        "n": n, "mean_delta": mean_d, "sd_d": sd_d, "se": se, "ci95": [lo, hi],
        "r20_rerank": m_a, "r20_norerank": m_b, "ceiling": ceil_all,
        "b5b_moved": b5b_moved, "b4_moved": b4_moved, "b5_moved": b5_moved,
        "verdict": verdict, "failures": failures,
    }, indent=2))
    print(f"\n      wrote {(OUT / 'ab_verdict.json').relative_to(REPO)}")

    print()
    print("=" * 88)
    if failures:
        print("VERIFIER: VOID / MALFORMED — do not interpret")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 88)
        return 1
    print("VERIFIER: PASS — the A/B is valid; the delta above is the pre-registered endpoint")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
