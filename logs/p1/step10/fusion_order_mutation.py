"""Mutation proof for fusion_order_verifier.py.

Every check must be reddenable, and every mutation must redden its INTENDED check. The mutations are
generated programmatically over every recorded cell so no check is left unexercised.

Usage:  python logs/p1/step10/fusion_order_mutation.py
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
ART = HERE / "fusion_order.json"
VER = HERE / "fusion_order_verifier.py"
ARMS = ("O0", "O0w", "O1", "O2", "O3", "O4")
TREATMENTS = ("O1", "O2", "O3", "O4")
TYPES = ("factual", "multihop", "overview")
ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20",
                 "precision_at_20", "f1_at_20")


def run(art_obj, tmp: Path, *, list_checks: bool = False):
    ap = tmp / "art.json"
    ap.write_text(json.dumps(art_obj))
    # ⚠️ The CLEAN baseline must be read with `--list-checks`: the normal run prints FAILURES only, so
    # a clean run yields no check ids and the "every check was reddened" test becomes vacuous.
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

    # V2 -- every arm x scope x cell
    for arm in ARMS:
        for scope in ("overall",) + TYPES:
            for k in ENDPOINT_KEYS + ("precision_ceiling_at_20", "pool_mean"):
                add(f"MV_V2_{arm}_{scope}_{k}", f"V2_{arm}_{scope}_{k}",
                    (lambda a, arm=arm, scope=scope, k=k: rec(a, arm, scope).__setitem__(
                        k, (rec(a, arm, scope).get(k) or 0.0) + 0.01)))

    # V1
    add("MV_V1_n", "V1_n_queries_133",
        lambda a: a["meta"].__setitem__("n_queries", 132))
    add("MV_V1c_arms", "V1c_arms_present",
        lambda a: a["aggregate"].__setitem__("O9_bogus", copy.deepcopy(a["aggregate"]["O0"])))

    # V3 -- a pool sha no longer matches its page list
    def mv3(a):
        a["per_query"][0]["O0_pool_sha"] = "0" * 16
    add("MV_V3_pool_sha", "V3_pool_sha_recomputes", mv3)

    # V2b -- the metric FUNCTION: break a recorded per-query metric on a query with no page-less
    # candidate (the rows where the re-derivation must be exact)
    def _pick_exact(a):
        for r in a["per_query"]:
            if "error" in r:
                continue
            if not any(r.get(f"{x}_endp_pageless") for x in ARMS):
                return r
        return None

    def mv2b(a):
        r = _pick_exact(a)
        if r is not None:
            r["O0_metrics"]["ndcg_at_20"] = r["O0_metrics"]["ndcg_at_20"] + 0.05
    add("MV_V2b_metric_fn", "V2b_O0_overall_metric_fn_exact", mv2b)

    # V2b -- one per ARM x TYPE, so every `V2b_{arm}_{scope}_metric_fn_exact` check is exercised
    # (breaking a query of type t reddens that arm's scope-t check AND its overall check)
    for arm in ARMS:
        for t in TYPES:
            def _mv2b_scope(a, arm=arm, t=t):
                for r in a["per_query"]:
                    if "error" in r or r["query_type"] != t:
                        continue
                    if any(r.get(f"{x}_endp_pageless") for x in ARMS):
                        continue
                    r[f"{arm}_metrics"]["ndcg_at_20"] = r[f"{arm}_metrics"]["ndcg_at_20"] + 0.05
                    return
            add(f"MV_V2b_{arm}_{t}", f"V2b_{arm}_{t}_metric_fn_exact", _mv2b_scope)

    # V1b -- a per-type POPULATION count changes (the checks read `per_query`, not the aggregate)
    def _mv_v1b(a):
        for r in a["per_query"]:
            if r["query_type"] == "overview":
                r["query_type"] = "factual"
                return
    add("MV_V1b_overview", "V1b_n_overview", _mv_v1b)


    # V4 -- a page-less endpoint candidate on a NON-multihop query (the mechanism breaks)
    def mv4(a):
        for r in a["per_query"]:
            if r["query_type"] == "multihop" and r.get("O0_endp_pageless"):
                r["query_type"] = "factual"
                break
    add("MV_V4_pageless_mechanism", "V4_pageless_endpoint_candidates_are_all_multihop", mv4)

    def mv4b(a):
        a["per_query"][0]["O0_slots_n"] = a["per_query"][0]["O0_slots_n"] + 1
    add("MV_V4b_slots_n", "V4b_slots_n_equals_pages_plus_pageless", mv4b)

    # V5 -- every treatment x key, overall mean/n/ci, and the by-type means
    for arm in TREATMENTS:
        for k in ENDPOINT_KEYS:
            add(f"MV_V5_{arm}_{k}_mean", f"V5_{arm}_minus_O0_{k}_mean",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_O0"][k].__setitem__(
                    "mean", (a["deltas"][f"{arm}_minus_O0"][k].get("mean") or 0.0) + 0.01)))
            add(f"MV_V5_{arm}_{k}_n", f"V5_{arm}_minus_O0_{k}_n",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_O0"][k].__setitem__(
                    "n", (a["deltas"][f"{arm}_minus_O0"][k].get("n") or 133) - 1)))
            add(f"MV_V5_{arm}_{k}_ci", f"V5_{arm}_minus_O0_{k}_ci",
                (lambda a, arm=arm, k=k: a["deltas"][f"{arm}_minus_O0"][k]["ci95"].__setitem__(
                    0, a["deltas"][f"{arm}_minus_O0"][k]["ci95"][0] + 0.05)))
        for t in TYPES:
            for k in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20"):
                add(f"MV_V5_{arm}_{t}_{k}", f"V5_{arm}_{t}_{k}_mean",
                    (lambda a, arm=arm, t=t, k=k: a["deltas"][
                        f"{arm}_minus_O0_by_type"][t][k].__setitem__(
                        "mean", (a["deltas"][f"{arm}_minus_O0_by_type"][t][k].get("mean") or 0.0)
                        + 0.01)))

    # V6 -- every guard flag
    GUARD_TO_CHECK = {
        "G1_no_lane_dropout_survived": "V6_G1_no_lane_dropout",
        "G4_no_reranker_fallback": "V6_G4_no_reranker_fallback",
        "G5_each_mechanism_engaged": "V6_G5_mechanism_engaged",
        "G6_133_queries_0_errors": "V6_G6_133_0_errors",
        "G7_lane_weights_default_is_inert_in_run": "V6_G7_inert_in_run",
    }
    for gname, cid in GUARD_TO_CHECK.items():
        add(f"MV_V6_{gname}", cid,
            (lambda a, gname=gname: a["guards"].__setitem__(gname, not a["guards"][gname])))

    add("MV_V6_G3_rederived", "V6_G3_O1_set_equality_REDERIVED",
        lambda a: a["per_query"][0].__setitem__("O1_pool_pages",
                                                a["per_query"][0]["O1_pool_pages"] + [99999]))
    add("MV_V6_G3c", "V6_G3c_O1_differs_exactly_where_O0_MMR_fired",
        lambda a: a["per_query"][0].__setitem__("O1_pool_pages",
                                                a["per_query"][0]["O1_pool_pages"] + [99998]))
    add("MV_V6_G3d", "V6_G3d_recorded_flag_was_misspecified",
        lambda a: a["guards"].__setitem__(
            "G3_O1_membership_identical_where_mmr_did_not_fire", True))

    # V7 -- perturb O0's aggregate (the anchor)
    for k in ENDPOINT_KEYS + ("coverage_reachable", "pool_cov"):
        add(f"MV_V7_{k}", f"V7_G2_anchor_overall",
            (lambda a, k=k: a["aggregate"]["O0"]["overall"].__setitem__(
                k, (a["aggregate"]["O0"]["overall"].get(k) or 0.0) + 0.01)))

    # V8 -- a NaN in an aggregate
    add("MV_V8_nan", "V8_no_nan",
        lambda a: a["aggregate"]["O1"]["overall"].__setitem__("ndcg_at_20", float("nan")))

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
        # ⚠️ Each mutation is an independent subprocess on a COPY of the artifact, so they parallelise
        # cleanly; the serial form took ~43 min for ~370 mutations.
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
    print(f"{'mutation':{w}s}  {'intended check':38s}  reddens?")
    print("-" * (w + 50))
    ok_all = True
    for name, intended, hit, red in rows:
        extra = [x for x in red if x != intended]
        print(f"{name:{w}s}  {intended:38s}  {'YES' if hit else 'NO '}"
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
