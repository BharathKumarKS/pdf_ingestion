"""Mutation proof for overview_metric_diag_verifier.py.

Every check must be reddenable, and every mutation must redden its INTENDED check. Mutations are
generated over every aggregate cell so no check is left unexercised.

Usage:  python logs/p1/step10/overview_metric_diag_mutation.py
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
ART = HERE / "overview_metric_diag.json"
SRC = HERE / "t4_endpoint.json"
VER = HERE / "overview_metric_diag_verifier.py"
TYPES = ("factual", "overview", "multihop")


def run(art_obj, src_obj, tmp: Path, *, fix_digests=True):
    ap, sp = tmp / "art.json", tmp / "src.json"
    sp.write_text(json.dumps(src_obj))
    art_obj = copy.deepcopy(art_obj)
    if fix_digests:
        art_obj["meta"]["inputs"]["t4_endpoint.json"] = hashlib.sha256(sp.read_bytes()).hexdigest()
    ap.write_text(json.dumps(art_obj))
    p = subprocess.run(
        [sys.executable, str(VER), "--check", "--artifact", str(ap), "--source", str(sp)],
        capture_output=True, text=True,
    )
    return set(re.findall(r"FAIL\s+(\S+)", p.stdout)), p.stdout


def build_mutations():
    m = []

    def add(name, intended, fn):
        m.append((name, intended, fn))

    def bump(path_getter, key, delta=0.01):
        def fn(a, s):
            path_getter(a)[key] = path_getter(a)[key] + delta
        return fn

    def setv(path_getter, key, val):
        def fn(a, s):
            path_getter(a)[key] = val
        return fn

    def agg(a, t):
        return a["diagnosis"]["by_type"][t]["aggregate"]

    def ov(a):
        return a["diagnosis"]["overall"]

    # V3 -- realised x type + overall
    for metric in ("realised_R", "realised_P", "realised_nDCG"):
        for t in TYPES:
            add(f"MV_V3_{metric}_{t}", f"V3_{metric}_{t}", bump(lambda a, t=t: agg(a, t), metric))
        add(f"MV_V3_{metric}_overall", f"V3_{metric}_overall", bump(ov, metric))

    # V4 -- label ceiling x type + overall
    for t in TYPES:
        add(f"MV_V4_{t}", f"V4_Rceil_label_{t}", bump(lambda a, t=t: agg(a, t), "R_ceil_label"))
    add("MV_V4_overall", "V4_Rceil_label_overall", bump(ov, "R_ceil_label"))

    # V5 -- pool-aware ceilings x type
    for metric in ("R_ceil_pool", "P_ceil_pool", "nDCG_ceil_pool"):
        for t in TYPES:
            add(f"MV_V5_{metric}_{t}", f"V5_{metric}_{t}", bump(lambda a, t=t: agg(a, t), metric))

    # V6 -- capture x family x type + overall
    for fam in ("R", "P", "nDCG"):
        for t in TYPES:
            add(f"MV_V6_{fam}_{t}", f"V6_capture_{fam}_{t}", bump(lambda a, t=t: agg(a, t), f"capture_{fam}"))
        add(f"MV_V6_{fam}_overall", f"V6_capture_{fam}_overall", bump(ov, f"capture_{fam}"))

    # V2 / V2b
    add("MV_V2_n", "V2_n_queries_133", setv(lambda a: a["diagnosis"], "n_queries", 132))
    for t in TYPES:
        add(f"MV_V2b_{t}", f"V2b_n_{t}", setv(lambda a, t=t: agg(a, t), "n", 1))

    # V1 / V1b / V1c
    add("MV_V1_t4", "V1_input_digest_t4",
        setv(lambda a: a["meta"]["inputs"], "t4_endpoint.json", "0" * 64))
    add("MV_V1b_t0", "V1b_input_digest_t0",
        setv(lambda a: a["meta"]["inputs"], "t0_baseline.json", "0" * 64))
    add("MV_V1c_fo", "V1c_input_digest_fo",
        setv(lambda a: a["meta"]["inputs"], "fusion_order.json", "0" * 64))

    # V7 -- a pool-aware ceiling above its label ceiling
    add("MV_V7_P", "V7_ceil_pool_le_label",
        setv(lambda a: agg(a, "overview"), "P_ceil_pool", 2.0))

    # V8 / V8b
    add("MV_V8_16", "V8_mmr_set_16", setv(lambda a: a["mmr_subset"], "n_fired", 15))
    add("MV_V8b_eq", "V8b_mmr_set_eq_pool_diff",
        setv(lambda a: a["mmr_subset"], "fired_set_equals_pool_diff", False))

    # V9 -- a source query whose pool holds more gold than it can reach
    def mut_v9(a, s):
        for r in s["per_query"]:
            if r["n_reachable"] >= 1:
                r["C_pool_cov"] = 5.0
                break
    add("MV_V9_pool_gt_reach", "V9_pool_gold_le_reach", mut_v9)

    # V10 -- a NaN in an aggregate
    add("MV_V10_nan", "V10_no_nan", setv(lambda a: agg(a, "factual"), "capture_R", float("nan")))

    # V11 -- a verdict that contradicts the threshold
    def mut_v11(a, s):
        a["diagnosis"]["by_type"]["overview"]["aggregate"]["verdict_R"] = "metric-limited"
    add("MV_V11_verdict", "V11_verdict_follows_threshold", mut_v11)

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

        rows = []
        all_red = set()
        for name, intended, fn in build_mutations():
            a, s = copy.deepcopy(art), copy.deepcopy(src)
            fn(a, s)
            red, _ = run(a, s, tmp, fix_digests=(name != "MV_V1_t4"))
            rows.append((name, intended, intended in red, sorted(red)))
            all_red |= red

    w = max(len(r[0]) for r in rows)
    print(f"{'mutation':{w}s}  {'intended check':30s}  reddens?  also reddens")
    print("-" * (w + 66))
    ok_all = True
    for name, intended, hit, red in rows:
        extra = [x for x in red if x != intended]
        print(f"{name:{w}s}  {intended:30s}  {'YES' if hit else 'NO '}       {', '.join(extra) if extra else '-'}")
        ok_all &= hit

    inert = sorted(all_checks - all_red)
    print()
    print(f"mutations            : {len(rows)}")
    print(f"checks total         : {len(all_checks)}")
    print(f"checks reddened      : {len(all_red)}")
    print(f"INERT checks         : {inert if inert else 'none'}")
    print(f"all mutations hit    : {ok_all}")
    return 0 if (ok_all and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
