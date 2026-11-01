"""Mutation proof for cut_ndcg_k_verifier.py. Every check must be reddenable, every mutation must
redden its INTENDED check.

Usage:  python logs/p1/step10/cut_ndcg_k_mutation.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "cut_ndcg_k.json"
SRC = HERE / "t4_endpoint.json"
VER = HERE / "cut_ndcg_k_verifier.py"
TYPES = ("factual", "overview", "multihop")


def run(art_obj, src_obj, tmp: Path, *, fix_digests=True):
    ap, sp = tmp / "art.json", tmp / "src.json"
    sp.write_text(json.dumps(src_obj))
    art_obj = copy.deepcopy(art_obj)
    if fix_digests:
        art_obj["meta"]["inputs"]["t4_endpoint.json"] = hashlib.sha256(sp.read_bytes()).hexdigest()
    ap.write_text(json.dumps(art_obj))
    p = subprocess.run([sys.executable, str(VER), "--check", "--artifact", str(ap), "--source", str(sp)],
                       capture_output=True, text=True)
    return set(re.findall(r"FAIL\s+(\S+)", p.stdout)), p.stdout


def build_mutations():
    m = []

    def add(name, intended, fn):
        m.append((name, intended, fn))

    def bump(getter, key, delta=0.01):
        def fn(a, s):
            getter(a)[key] = getter(a)[key] + delta
        return fn

    def setv(getter, key, val):
        def fn(a, s):
            getter(a)[key] = val
        return fn

    def agg(a, t):
        return a["cut_ndcg_k"]["by_type"][t]["aggregate"]

    # V4 -- the @20 metrics x type
    for metric in ("nDCG20", "R20", "P20"):
        for t in TYPES:
            add(f"MV_V4_{metric}_{t}", f"V4_{metric}_{t}", bump(lambda a, t=t: agg(a, t), metric))

    # V5 -- R50 x type
    for t in TYPES:
        add(f"MV_V5_R50_{t}", f"V5_R50_vs_W50metrics_{t}", bump(lambda a, t=t: agg(a, t), "R50"))

    # V8 -- the CI x name
    for name in ("dR", "dP", "dnDCG"):
        def mut_ci(a, s, name=name):
            ci = a["cut_ndcg_k"]["overall"][f"{name}_ci"]
            a["cut_ndcg_k"]["overall"][f"{name}_ci"] = [ci[0] + 0.01, ci[1] + 0.01]
        add(f"MV_V8_ci_{name}", f"V8_ci_{name}", mut_ci)

    # V2 / V2b
    add("MV_V2_n", "V2_n_queries_133", setv(lambda a: a["cut_ndcg_k"], "n_queries", 132))
    for t in TYPES:
        add(f"MV_V2b_{t}", f"V2b_n_{t}", setv(lambda a, t=t: agg(a, t), "n", 1))

    # V1
    add("MV_V1_t4", "V1_input_digest_t4",
        setv(lambda a: a["meta"]["inputs"], "t4_endpoint.json", "0" * 64))

    # V3 -- prefix identity: SOURCE mutation
    def mut_v3(a, s):
        for r in s["per_query"]:
            if r["W50_pages"]:
                r["W50_pages"][0] = 999999
                break
    add("MV_V3_prefix", "V3_prefix_identity", mut_v3)

    # V3b -- pool sha: SOURCE mutation
    def mut_v3b(a, s):
        s["per_query"][0]["C_pool_sha"] = "deadbeefdeadbeef"
    add("MV_V3b_poolsha", "V3b_pool_sha_equal", mut_v3b)

    # V3c -- the recorded guard: artifact mutation
    def mut_v3c(a, s):
        a["guards"]["G2_prefix_identity_bad"] = ["x"]
    add("MV_V3c_guard", "V3c_guard_recorded", mut_v3c)

    # V4c -- the @20 vs C_metrics cross-check: artifact mutation
    add("MV_V4c", "V4c_nDCG20_vs_Cmetrics_overview", bump(lambda a: agg(a, "overview"), "nDCG20"))

    # V6 -- prefix implies identical @20: SOURCE mutation (change a C page)
    def mut_v6(a, s):
        for r in s["per_query"]:
            if r["query_type"] == "overview":
                r["C_pages"] = list(r["C_pages"])
                r["C_pages"][0] = 999999
                break
    add("MV_V6_prefix20", "V6_prefix_implies_identical_20", mut_v6)

    # V7 -- len monotone: SOURCE mutation
    def mut_v7(a, s):
        for r in s["per_query"]:
            r["W50_pages"] = r["W50_pages"][:5]
            break
    add("MV_V7_len", "V7_len_monotone", mut_v7)

    # V7b -- extra gold nonneg: artifact mutation
    def mut_v7b(a, s):
        a["cut_ndcg_k"]["by_type"]["overview"]["per_query"][0]["extra_slots_gold"] = -1
    add("MV_V7b_gold", "V7b_extra_gold_nonneg", mut_v7b)

    # V9 -- comparability n: artifact mutation
    def mut_v9(a, s):
        a["cut_ndcg_k"]["comparability"]["n_rel_gt_20_comparable"]["n"] = 1
    add("MV_V9_comp_n", "V9_comparability_n", mut_v9)

    # V9b -- comparable mean: artifact mutation
    def mut_v9b(a, s):
        a["cut_ndcg_k"]["comparability"]["n_rel_gt_20_comparable"]["mean_dnDCG"] += 0.01
    add("MV_V9b_comp_mean", "V9b_comparable_mean", mut_v9b)

    # V9c -- same-denominator non-decreasing: artifact mutation (make one n_rel<=20 query negative)
    def mut_v9c(a, s):
        for t in TYPES:
            for r in a["cut_ndcg_k"]["by_type"][t]["per_query"]:
                if r["n_rel"] <= 20:
                    r["dnDCG"] = -0.5
                    return
    add("MV_V9c_nondec", "V9c_same_denom_non_decreasing", mut_v9c)

    # V10 -- NaN
    add("MV_V10_nan", "V10_no_nan", setv(lambda a: agg(a, "factual"), "nDCG20", float("nan")))

    return m


def main() -> int:
    art = json.loads(ART.read_text())
    src = json.loads(SRC.read_text())
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base_red, base_out = run(art, src, tmp)
        all_checks = set(re.findall(r"(?:PASS|FAIL)\s+(\S+)", base_out))
        if base_red:
            print(f"BASELINE NOT CLEAN: {sorted(base_red)}")
            return 2
        rows, all_red = [], set()
        for name, intended, fn in build_mutations():
            a, s = copy.deepcopy(art), copy.deepcopy(src)
            fn(a, s)
            red, _ = run(a, s, tmp, fix_digests=(name != "MV_V1_t4"))
            rows.append((name, intended, intended in red, sorted(red)))
            all_red |= red

    w = max(len(r[0]) for r in rows)
    print(f"{'mutation':{w}s}  {'intended check':34s}  reddens?  also reddens")
    print("-" * (w + 70))
    ok_all = True
    for name, intended, hit, red in rows:
        extra = [x for x in red if x != intended]
        print(f"{name:{w}s}  {intended:34s}  {'YES' if hit else 'NO '}       {', '.join(extra) if extra else '-'}")
        ok_all &= hit
    inert = sorted(all_checks - all_red)
    print()
    print(f"mutations       : {len(rows)}")
    print(f"checks total    : {len(all_checks)}")
    print(f"checks reddened : {len(all_red)}")
    print(f"INERT checks    : {inert if inert else 'none'}")
    print(f"all mutations hit: {ok_all}")
    return 0 if (ok_all and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
