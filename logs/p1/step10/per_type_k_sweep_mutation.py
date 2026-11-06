"""Mutation proof for per_type_k_sweep_verifier.py.

Each mutation perturbs a COPY of the artifact (or of a source) and requires the verifier's INTENDED check
to go red. It also requires every check to be reddened by at least one mutation (NO INERT CHECK).

Usage:  python logs/p1/step10/per_type_k_sweep_mutation.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import per_type_k_sweep_verifier as V  # noqa: E402


def _load():
    return (json.loads(V.ART.read_text()), json.loads(V.T4.read_text()), json.loads(V.T0.read_text()))


def run_verify(art, t4, t0):
    V.RESULTS.clear()
    V.verify(art, t4, t0)
    return {r["id"]: r["passed"] for r in V.RESULTS}


def mutations():
    """Yield (name, target_check, mutate_fn) where mutate_fn(art, t4, t0) mutates copies in place."""
    def art_mut(path, val):
        def f(art, t4, t0):
            d = art
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = val
        return f

    def art_inc(path, delta):
        def f(art, t4, t0):
            d = art
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = d[path[-1]] + delta
        return f

    yield ("M_V1_population", "V1_population", art_mut(["guards", "G1_population"], 999))
    yield ("M_V1_ids_align", "V1_ids_align", art_mut(["guards", "G1_ids_align"], False))
    yield ("M_V1_types", "V1_types", art_mut(["guards", "G1_types", "factual"], 99))
    yield ("M_V2_prefix", "V2_prefix_identity", art_mut(["guards", "G2_prefix_identity_bad"], ["x"]))
    yield ("M_V2_pool_sha", "V2_pool_sha", art_mut(["guards", "G2b_pool_sha_bad"], ["x"]))
    yield ("M_V2_anchor", "V2_cross_artifact_anchor", art_mut(["guards", "G3_cross_artifact_anchor_bad"], ["x"]))
    yield ("M_V3_CE", "V3_per_query_CE", art_inc(["results", "CE", "per_query", 0, "R@30"], 0.1))
    yield ("M_V3_POOL", "V3_per_query_POOL", art_inc(["results", "POOL", "per_query", 0, "nDCG@40"], 0.1))

    def m_v7(art, t4, t0):
        # drop gold page 34 from arm C's own list on gold-003 -> R@10 (from W50) > R@20 (from C) -> non-monotone
        for q in t4["per_query"]:
            if q["id"] == "gold-003":
                q["C_pages"] = [p for p in q["C_pages"] if p != 34]
    yield ("M_V7_monotone", "V7_monotone_R", m_v7)

    yield ("M_V4_CE", "V4_aggregates_CE", art_inc(["results", "CE", "by_type", "overview", "per_k", "30", "nDCG"], 0.1))
    yield ("M_V4_POOL", "V4_aggregates_POOL", art_inc(["results", "POOL", "by_type", "factual", "per_k", "50", "R"], 0.1))
    yield ("M_V5_CE", "V5_deltas_ci_CE", art_inc(["results", "CE", "by_type", "multihop", "per_k", "47", "dR", "mean"], 0.1))
    yield ("M_V5_POOL", "V5_deltas_ci_POOL", art_inc(["results", "POOL", "by_type", "overview", "per_k", "50", "dnDCG", "mean"], 0.1))
    yield ("M_V8_comparability", "V8_comparability",
           art_inc(["results", "CE", "by_type", "overview", "comparability", "n_rel_gt_20_comparable", "per_k", "47", "mean"], 0.1))
    yield ("M_V9_anchor", "V9_anchor_to_C_metrics", art_mut(["guards", "G5_anchor_bad"], ["x"]))
    yield ("M_V10_t4", "V10_input_sha_t4", art_mut(["meta", "inputs", "t4_endpoint.json"], "deadbeef"))
    yield ("M_V10_t0", "V10_input_sha_t0", art_mut(["meta", "inputs", "t0_baseline.json"], "deadbeef"))


def main() -> int:
    art0, t40, t00 = _load()
    base = run_verify(copy.deepcopy(art0), copy.deepcopy(t40), copy.deepcopy(t00))
    all_checks = set(base)
    if not all(base.values()):
        print("BASELINE IS RED — fix the verifier first:", [k for k, v in base.items() if not v])
        return 2

    reddened_by = {c: [] for c in all_checks}
    rows = []
    ok = True
    for name, target, fn in mutations():
        art, t4, t0 = copy.deepcopy(art0), copy.deepcopy(t40), copy.deepcopy(t00)
        fn(art, t4, t0)
        res = run_verify(art, t4, t0)
        failed = {c for c, p in res.items() if not p}
        for c in failed:
            reddened_by[c].append(name)
        hit = target in failed
        ok = ok and hit
        rows.append((name, target, sorted(failed), hit))

    print(f"{'mutation':22s} {'target':28s} {'hit':>4s}  failed")
    print("-" * 100)
    for name, target, failed, hit in rows:
        print(f"{name:22s} {target:28s} {'YES' if hit else 'NO ':>4s}  {','.join(failed)}")

    inert = [c for c in sorted(all_checks) if not reddened_by[c]]
    print()
    print(f"{len(rows)} mutations; {sum(1 for r in rows if r[3])}/{len(rows)} reddened their intended check")
    print(f"inert checks (never reddened): {inert if inert else 'NONE'}")
    return 0 if (ok and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
