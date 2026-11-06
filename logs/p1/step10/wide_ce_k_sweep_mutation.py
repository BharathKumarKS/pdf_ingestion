"""Mutation proof for wide_ce_k_sweep_verifier.py. Each mutation must redden its intended check;
every check must be reddened by at least one mutation (NO INERT CHECK).

Usage:  python logs/p1/step10/wide_ce_k_sweep_mutation.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wide_ce_k_sweep_verifier as V  # noqa: E402


def _load():
    return json.loads(V.ART.read_text()), json.loads(V.RUN.read_text())


def run_verify(art, run):
    V.RESULTS.clear()
    V.verify(art, run)
    return {r["id"]: r["passed"] for r in V.RESULTS}


def mutations():
    def s(path, val):
        def f(art):
            d = art
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = val
        return f

    def inc(path, delta):
        def f(art):
            d = art
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = d[path[-1]] + delta
        return f

    yield ("M_V1_population", "V1_population", s(["guards", "G1_population"], 999))
    yield ("M_V1_types", "V1_types", s(["guards", "G1_types", "factual"], 99))
    yield ("M_V2_reachable", "V2_reachable_888", s(["guards", "G2_reachable_pages"], 999))
    yield ("M_V2_no_errors", "V2_no_errors", s(["guards", "G3_errors"], ["x"]))
    yield ("M_V2_no_fallbacks", "V2_no_fallbacks", s(["guards", "G4_reranker_fallbacks"], 1))
    yield ("M_V2_cap_widened", "V2_cap_widened", s(["guards", "G5_ce_len_min_gt_20"], 20))
    yield ("M_V2_pool_widened", "V2_pool_widened", s(["guards", "G6_pool_mean_gt_86"], 86.0))
    yield ("M_V3_per_query", "V3_per_query_CE", inc(["results", "CE", "per_query", 0, "R@100"], 0.1))
    yield ("M_V4_aggregates", "V4_aggregates_CE", inc(["results", "CE", "by_type", "overview", "per_k", "250", "nDCG"], 0.1))
    yield ("M_V8_comparability", "V8_comparability",
           inc(["results", "CE", "by_type", "overview", "comparable_k_lt_nrel", "100", "dnDCG", "mean"], 0.1))
    yield ("M_V10_sha", "V10_input_sha", s(["meta", "inputs", "wide_ce_endpoint.json"], "deadbeef"))


def main() -> int:
    art0, run0 = _load()
    base = run_verify(copy.deepcopy(art0), run0)
    all_checks = set(base)
    if not all(base.values()):
        print("BASELINE RED:", [k for k, v in base.items() if not v])
        return 2

    reddened = {c: [] for c in all_checks}
    rows, ok = [], True
    for name, target, fn in mutations():
        art = copy.deepcopy(art0)
        fn(art)
        res = run_verify(art, run0)
        failed = {c for c, p in res.items() if not p}
        for c in failed:
            reddened[c].append(name)
        hit = target in failed
        ok = ok and hit
        rows.append((name, target, sorted(failed), hit))

    print(f"{'mutation':18s} {'target':26s} {'hit':>4s}  failed")
    print("-" * 92)
    for name, target, failed, hit in rows:
        print(f"{name:18s} {target:26s} {'YES' if hit else 'NO ':>4s}  {','.join(failed)}")
    inert = [c for c in sorted(all_checks) if not reddened[c]]
    print()
    print(f"{len(rows)} mutations; {sum(1 for r in rows if r[3])}/{len(rows)} reddened their intended check")
    print(f"inert checks: {inert if inert else 'NONE'}")
    return 0 if (ok and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
