"""Mutation proof for order_waste_decomp_verifier.py.

Every check must be reddenable, and every mutation must redden its INTENDED check. The mutations
are generated programmatically over every aggregate cell so no check is left unexercised.

Usage:  python logs/p1/step10/order_waste_decomp_mutation.py
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
ART = HERE / "order_waste_decomp.json"
SRC = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"
VER = HERE / "order_waste_decomp_verifier.py"
TYPES = ("factual", "overview", "multihop")


def run(art_obj, src_obj, tmp: Path, *, fix_digests=True):
    """Run the verifier on temp copies. fix_digests re-points the recorded t4 digest at the temp
    source so only the intended mutation can redden V1."""
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
        return a["decomposition"]["by_type"][t]["aggregate"]

    def ov(a):
        return a["decomposition"]["overall"]

    # V3 -- every metric x every type, and every metric overall
    for metric in ("R_ceil_20", "pool_oracle_20", "realised_N", "realised_C"):
        for t in TYPES:
            add(f"MV_V3_{metric}_{t}", f"V3_{metric}_{t}", bump(lambda a, t=t: agg(a, t), metric))
        add(f"MV_V3_{metric}_overall", f"V3_{metric}_overall", bump(ov, metric))

    # V5 -- every waste identity x every type
    for metric in ("waste_pool", "waste_order", "waste_ce", "recoverable_total"):
        for t in TYPES:
            cid = f"V5_{metric}_{t}" if metric != "recoverable_total" else f"V5_recoverable_{t}"
            add(f"MV_{cid}", cid, bump(lambda a, t=t: agg(a, t), metric))

    # V6 -- every share
    for t in TYPES:
        add(f"MV_V6_{t}", f"V6_shares_sum_1_{t}", bump(lambda a, t=t: agg(a, t), "share_waste_order"))

    # V2 / V2b
    add("MV_V2_n", "V2_n_queries_133", setv(lambda a: a["decomposition"], "n_queries", 132))
    for t in TYPES:
        add(f"MV_V2b_{t}", f"V2b_n_{t}", setv(lambda a, t=t: agg(a, t), "n", 1))

    # V1 / V1b
    add("MV_V1_t4", "V1_input_digest_t4",
        setv(lambda a: a["meta"]["inputs"], "t4_endpoint.json", "0" * 64))
    add("MV_V1b_t0", "V1b_input_digest_t0",
        setv(lambda a: a["meta"]["inputs"], "t0_baseline.json", "0" * 64))

    # V4 -- a per-query pool_gold no longer equals C_pool_cov * n_reachable
    def mut_v4(a, s):
        a["decomposition"]["by_type"]["overview"]["per_query"][0]["pool_gold"] = 999.0
    add("MV_V4_pool_gold", "V4_pool_gold_identity", mut_v4)

    # V7 -- oracle above the label ceiling: needs a query with n_rel < 20 so min(20,pool_gold)
    #       can exceed min(20,n_rel)
    def mut_v7(a, s):
        for r in s["per_query"]:
            if r["n_relevant"] < 20:
                r["C_pool_cov"] = 100.0
                break
    add("MV_V7_oracle_gt_ceiling", "V7_oracle_le_ceiling", mut_v7)

    # V8 -- the product returns gold the pool does not hold
    def mut_v8(a, s):
        for r in s["per_query"]:
            if r["query_type"] == "factual":
                r["C_pool_cov"] = 0.0
                r["C_pages"] = list(r["relevant_pages"])
                break
    add("MV_V8_C_gt_oracle", "V8_realised_C_le_oracle", mut_v8)

    # V9 -- a funnel cell disagrees with T0
    def mut_v9(a, s):
        a["funnel_coverage"]["overview"]["fusion"]["coverage"] = 0.99
    add("MV_V9_funnel", "V9_funnel_matches_T0", mut_v9)

    # V10 -- a NaN in an aggregate
    add("MV_V10_nan", "V10_no_nan", setv(lambda a: agg(a, "factual"), "waste_ce", float("nan")))

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
    print(f"{'mutation':{w}s}  {'intended check':28s}  reddens?  also reddens")
    print("-" * (w + 62))
    ok_all = True
    for name, intended, hit, red in rows:
        extra = [x for x in red if x != intended]
        print(f"{name:{w}s}  {intended:28s}  {'YES' if hit else 'NO '}       {', '.join(extra) if extra else '-'}")
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
