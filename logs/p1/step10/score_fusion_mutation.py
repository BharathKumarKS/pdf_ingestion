"""Mutation proof for score_fusion_verifier.py.

Every check must be reddenable, and every mutation must redden its INTENDED check. Mutations are
generated programmatically over every recorded cell so no check is left unexercised.

Usage:  python logs/p1/step10/score_fusion_mutation.py
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "score_fusion.json"
VER = HERE / "score_fusion_verifier.py"
ARMS = ("S0", "S1", "S2")
TREATMENTS = ("S1", "S2")
TYPES = ("factual", "multihop", "overview")
ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "recall_at_100",
                 "hit_at_20", "precision_at_20", "precision_ceiling_at_20", "f1_at_20")


def run(art_obj, tmp: Path, *, list_checks: bool = False):
    ap = tmp / "art.json"
    ap.write_text(json.dumps(art_obj))
    cmd = [sys.executable, str(VER), "--list-checks" if list_checks else "--check",
           "--artifact", str(ap)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return set(re.findall(r"FAIL\s+(\S+)", p.stdout)), p.stdout


def build_mutations():
    m = []

    def add(name, intended, fn):
        m.append((name, intended, fn))

    def rec(a, arm, scope):
        return (a["aggregate"][arm]["overall"] if scope == "overall"
                else a["aggregate"][arm]["by_type"][scope])

    # V2 -- every arm x scope x cell (incl. the coverage cells, read from the per-query arrays)
    for arm in ARMS:
        for scope in ("overall",) + TYPES:
            for k in ENDPOINT_KEYS + ("precision_ceiling_at_20", "coverage_reachable", "pool_cov"):
                add(f"MV_V2_{arm}_{scope}_{k}", f"V2_{arm}_{scope}_{k}",
                    (lambda a, arm=arm, scope=scope, k=k: rec(a, arm, scope).__setitem__(
                        k, (rec(a, arm, scope).get(k) or 0.0) + 0.01)))
            add(f"MV_V2_{arm}_{scope}_pool_mean", f"V2_{arm}_{scope}_pool_mean",
                (lambda a, arm=arm, scope=scope: rec(a, arm, scope).__setitem__(
                    "pool_mean", (rec(a, arm, scope).get("pool_mean") or 0.0) + 0.01)))

    # V1
    add("MV_V1_n", "V1_n_queries_133", lambda a: a["meta"].__setitem__("n_queries", 132))
    add("MV_V1c_arms", "V1c_arms_present",
        lambda a: a["aggregate"].__setitem__("S9_bogus", copy.deepcopy(a["aggregate"]["S0"])))
    for t in TYPES:
        def _mv1b(a, t=t):
            for r in a["per_query"]:
                if r["query_type"] == t:
                    r["query_type"] = "factual" if t != "factual" else "overview"
                    return
        add(f"MV_V1b_{t}", f"V1b_n_{t}", _mv1b)

    # V3 -- a pool sha no longer matches its page list
    add("MV_V3_pool_sha", "V3_pool_sha_recomputes",
        lambda a: a["per_query"][0].__setitem__("S0_pool_sha", "0" * 16))

    # V2b -- the metric FUNCTION on the rows where the re-derivation must be exact
    def _pick_exact(a, t=None):
        for r in a["per_query"]:
            if "error" in r:
                continue
            if t and r["query_type"] != t:
                continue
            if all(r[f"{x}_slots_n"] == len(r[f"{x}_pages"]) for x in ARMS):
                return r
        return None

    for arm in ARMS:
        for scope in ("overall",) + TYPES:
            def _mv2b(a, arm=arm, scope=scope):
                r = _pick_exact(a, None if scope == "overall" else scope)
                if r is not None:
                    r[f"{arm}_metrics"]["ndcg_at_20"] = r[f"{arm}_metrics"]["ndcg_at_20"] + 0.05
            add(f"MV_V2b_{arm}_{scope}", f"V2b_{arm}_{scope}_metric_fn_exact", _mv2b)

    # V4 -- a recorded coverage value no longer matches its page list (on a NON-multihop row, so the
    # mechanism assertion cannot absorb it)
    def mv4(a):
        for r in a["per_query"]:
            if r["query_type"] == "factual" and r.get("S0_cov") is not None:
                r["S0_cov"] = r["S0_cov"] + 0.01
                return
    add("MV_V4_coverage", "V4_coverage_rederives_exact", mv4)

    # V5 -- a page-less endpoint candidate on a NON-multihop query (the mechanism breaks)
    def mv5(a):
        for r in a["per_query"]:
            if r["query_type"] == "factual":
                r["S0_slots_n"] = r["S0_slots_n"] + 1
                return
    add("MV_V5_pageless_mechanism", "V5_pageless_endpoint_candidates_are_all_multihop", mv5)

    # V6 -- every treatment x key: overall mean/n/ci/resolved, by-type means, and poolcov
    for arm in TREATMENTS:
        for k in ENDPOINT_KEYS:
            add(f"MV_V6_{arm}_{k}_mean", f"V6_{arm}_minus_S0_{k}_mean",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_S0"][k].__setitem__(
                    "mean", (a["deltas"][f"{arm}_minus_S0"][k].get("mean") or 0.0) + 0.01)))
            add(f"MV_V6_{arm}_{k}_n", f"V6_{arm}_minus_S0_{k}_n",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_S0"][k].__setitem__(
                    "n", (a["deltas"][f"{arm}_minus_S0"][k].get("n") or 133) - 1)))
            add(f"MV_V6_{arm}_{k}_ci", f"V6_{arm}_minus_S0_{k}_ci",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_S0"][k]["ci95"].__setitem__(
                    0, a["deltas"][f"{arm}_minus_S0"][k]["ci95"][0] + 0.05)))
            add(f"MV_V6_{arm}_{k}_resolved", f"V6_{arm}_minus_S0_{k}_resolved",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_S0"][k].__setitem__(
                    "resolved", not a["deltas"][f"{arm}_minus_S0"][k]["resolved"])))
        for t in TYPES:
            for k in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20"):
                add(f"MV_V6_{arm}_{t}_{k}", f"V6_{arm}_{t}_{k}_mean",
                    (lambda a, arm=arm, t=t, k=k: a["deltas"][
                        f"{arm}_minus_S0_by_type"][t][k].__setitem__(
                        "mean", (a["deltas"][f"{arm}_minus_S0_by_type"][t][k].get("mean") or 0.0)
                        + 0.01)))
        add(f"MV_V6_poolcov_{arm}", f"V6_poolcov_{arm}_minus_S0_mean",
            (lambda a, arm=arm: a["deltas"][f"poolcov_{arm}_minus_S0"].__setitem__(
                "mean", (a["deltas"][f"poolcov_{arm}_minus_S0"].get("mean") or 0.0) + 0.01)))

    # V7 -- every guard flag, plus the two mechanism-specific re-derivations
    GUARD_TO_CHECK = {
        "G1_population_133_0_errors_all_arms": "V7_G1_population",
        "G3_three_arms_share_the_same_lane_set": "V7_G3_lane_set",
        "G3b_digest_flip_is_pool_inert": "V7_G3b_inert",
        "G4_normalisers_exercised_each_lane": "V7_G4_normalisers_exercised",
        "G5_no_lane_dropout_survived": "V7_G5_no_lane_dropout",
        "G6_no_nan_null_and_page_dedup": "V7_G6_no_nan_null_dedup",
    }
    for gname, cid in GUARD_TO_CHECK.items():
        add(f"MV_V7_{gname}", cid,
            (lambda a, gname=gname: a["guards"].__setitem__(gname, not a["guards"][gname])))
    add("MV_V7_G4b_lane_stats", "V7_G4b_lane_stats_reported",
        lambda a: a["guard_detail"]["G4"]["max_gt_min_fraction"].__setitem__("dense", 0.5))
    add("MV_V7_G3_lane_set_detail", "V7_G3_lane_set",
        lambda a: a["per_query"][0].__setitem__("S1_lane_stats",
                                                [{"n": 1, "min": 0.0, "max": 0.0, "max_gt_min": False}]))
    add("MV_V7_G3_digest_list", "V7_G3_digest_list_reported",
        lambda a: a["guard_detail"]["G3"].__setitem__(
            "n_digest_mismatch", a["guard_detail"]["G3"]["n_digest_mismatch"] + 1))
    add("MV_V7_G3b_covers", "V7_G3b_covers_every_flip",
        lambda a: a["guard_detail"]["G3b"].__setitem__(
            "bogus-qid", {"pool_sha_stable": True, "pages_stable": True, "digest_reproduced": True}))
    add("MV_V7_G3b_inert_detail", "V7_G3b_inert",
        lambda a: next(iter(a["guard_detail"]["G3b"].values())).__setitem__("pool_sha_stable", False))

    # V8 -- perturb S0's aggregate (the §9 anchor), overall AND per type, plus the reported
    # missing-keys list. ⚠️ Only the keys V8 actually COMPARES: the anchor carries no
    # `recall_at_100`, and `coverage_reachable` is not in V8's key set — mutating those reddens the
    # V2 aggregate check instead, so they are exercised there, not here.
    for k in [x for x in ENDPOINT_KEYS if x != "recall_at_100"] + ["pool_cov"]:
        add(f"MV_V8_{k}", "V8_G2_anchor_overall",
            (lambda a, k=k: a["aggregate"]["S0"]["overall"].__setitem__(
                k, (a["aggregate"]["S0"]["overall"].get(k) or 0.0) + 0.01)))
    for t in TYPES:
        for k in ("ndcg_at_20", "map", "pool_cov"):
            add(f"MV_V8_{t}_{k}", f"V8_G2_anchor_{t}",
                (lambda a, t=t, k=k: a["aggregate"]["S0"]["by_type"][t].__setitem__(
                    k, (a["aggregate"]["S0"]["by_type"][t].get(k) or 0.0) + 0.01)))
    add("MV_V8_missing_keys", "V8_G2_anchor_reports_missing_keys",
        lambda a: a["guard_detail"].__setitem__("G2_anchor_missing_keys", ["bogus_key"]))

    # V9 -- the composition counts
    for arm in TREATMENTS:
        add(f"MV_V9_{arm}", f"V9_composition_{arm}",
            (lambda a, arm=arm: a["composition"][arm].__setitem__(
                "n_differs", a["composition"][arm]["n_differs"] + 1)))

    # V10 -- a NaN in an aggregate
    add("MV_V10_nan", "V10_no_nan",
        lambda a: a["aggregate"]["S1"]["overall"].__setitem__("ndcg_at_20", float("nan")))

    return m


def main() -> int:
    art = json.loads(ART.read_text())
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base_red, base_out = run(art, tmp, list_checks=True)
        all_checks = set(re.findall(r"(?:PASS|FAIL)\s+(\S+)", base_out))
        if base_red:
            print(f"BASELINE NOT CLEAN ({len(base_red)}): {sorted(base_red)[:10]}")
            return 2

        rows, all_red = [], set()
        import concurrent.futures as _cf

        def _one(item):
            name, intended, fn = item
            with tempfile.TemporaryDirectory() as sub_td:
                a = copy.deepcopy(art)
                fn(a)
                red, _ = run(a, Path(sub_td))
            return (name, intended, intended in red, sorted(red))

        with _cf.ThreadPoolExecutor(max_workers=8) as ex:
            for res in ex.map(_one, build_mutations()):
                rows.append(res)
                all_red |= set(res[3])

    w = max(len(r[0]) for r in rows)
    print(f"{'mutation':{w}s}  {'intended check':46s}  reddens?")
    print("-" * (w + 60))
    ok_all = True
    for name, intended, hit, red in rows:
        extra = [x for x in red if x != intended]
        print(f"{name:{w}s}  {intended:46s}  {'YES' if hit else 'NO '}"
              + (f"   (+{len(extra)} other)" if extra else ""))
        ok_all &= hit

    inert = sorted(all_checks - all_red)
    print()
    print(f"mutations        : {len(rows)}")
    print(f"checks total     : {len(all_checks)}")
    print(f"checks reddened  : {len(all_red)}")
    print(f"INERT checks     : {inert if inert else 'none'}")
    print(f"all mutations hit: {ok_all}")
    return 0 if (ok_all and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
