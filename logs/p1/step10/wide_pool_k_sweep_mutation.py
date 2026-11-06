"""Mutation proof for wide_pool_k_sweep_verifier.py.

Each mutation perturbs a COPY of the artifact and requires the verifier's INTENDED check to go red.
Requires every check to be reddened by at least one mutation (NO INERT CHECK).

Usage:  python logs/p1/step10/wide_pool_k_sweep_mutation.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wide_pool_k_sweep_verifier as V  # noqa: E402


def _load():
    return (json.loads(V.ART.read_text()), json.loads(V.FA.read_text()),
            json.loads(V.T0.read_text()), json.loads(V.REF.read_text()))


def run_verify(art, fa, t0, ref):
    V.RESULTS.clear()
    V.verify(art, fa, t0, ref)
    return {r["id"]: r["passed"] for r in V.RESULTS}


def mutations():
    def art_set(path, val):
        def f(art):
            d = art
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = val
        return f

    def art_inc(path, delta):
        def f(art):
            d = art
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = d[path[-1]] + delta
        return f

    yield ("M_V1_population", "V1_population", art_set(["guards", "G1_population"], 999))
    yield ("M_V1_types", "V1_types", art_set(["guards", "G1_types", "factual"], 99))
    yield ("M_V2_anchor", "V2_cross_artifact_anchor", art_set(["guards", "G2_cross_artifact_anchor_bad"], ["x"]))
    yield ("M_V2_superset", "V2_set_superset", art_set(["guards", "G3_set_superset_bad"], ["x"]))
    yield ("M_V3_POOL100", "V3_per_query_POOL100", art_inc(["results", "POOL100", "per_query", 0, "R@30"], 0.1))
    yield ("M_V3_POOL500", "V3_per_query_POOL500", art_inc(["results", "POOL500", "per_query", 0, "nDCG@100"], 0.1))
    yield ("M_V4_POOL100", "V4_aggregates_POOL100", art_inc(["results", "POOL100", "by_type", "overview", "per_k", "50", "nDCG"], 0.1))
    yield ("M_V4_POOL500", "V4_aggregates_POOL500", art_inc(["results", "POOL500", "by_type", "factual", "per_k", "250", "R"], 0.1))
    yield ("M_V9_ssi105", "V9_ssi105_reproduction", art_set(["guards", "G6_ssi105_reproduction_bad"], ["x"]))
    yield ("M_V10_fa", "V10_input_sha_fa", art_set(["meta", "inputs", "fusion_attribution.json"], "deadbeef"))
    yield ("M_V10_t0", "V10_input_sha_t0", art_set(["meta", "inputs", "t0_baseline.json"], "deadbeef"))


def main() -> int:
    art0, fa0, t00, ref0 = _load()
    base = run_verify(copy.deepcopy(art0), fa0, t00, ref0)
    all_checks = set(base)
    if not all(base.values()):
        print("BASELINE RED:", [k for k, v in base.items() if not v])
        return 2

    reddened = {c: [] for c in all_checks}
    rows, ok = [], True
    for name, target, fn in mutations():
        art = copy.deepcopy(art0)
        fn(art)
        res = run_verify(art, fa0, t00, ref0)
        failed = {c for c, p in res.items() if not p}
        for c in failed:
            reddened[c].append(name)
        hit = target in failed
        ok = ok and hit
        rows.append((name, target, sorted(failed), hit))

    print(f"{'mutation':18s} {'target':28s} {'hit':>4s}  failed")
    print("-" * 96)
    for name, target, failed, hit in rows:
        print(f"{name:18s} {target:28s} {'YES' if hit else 'NO ':>4s}  {','.join(failed)}")
    inert = [c for c in sorted(all_checks) if not reddened[c]]
    print()
    print(f"{len(rows)} mutations; {sum(1 for r in rows if r[3])}/{len(rows)} reddened their intended check")
    print(f"inert checks: {inert if inert else 'NONE'}")
    return 0 if (ok and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
