"""Independent verifier for 5A's overview-metric diagnosis.

stdlib only. Reads the WRITTEN artifact AND re-derives every number from the SOURCE artifacts'
raw per-query arrays, so the harness's own arithmetic is not trusted.

    python logs/p1/step10/overview_metric_diag_verifier.py --check [--artifact P] [--source P]

Every check must be able to FAIL. The mutation proof (overview_metric_diag_mutation.py) reddens each
check in turn; a check no mutation can redden is inert and is reported as such.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "overview_metric_diag.json"
SRC = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"
FO = HERE / "fusion_order.json"

TYPES = ("factual", "overview", "multihop")
EXPECTED_N = {"factual": 53, "overview": 40, "multihop": 40}
LABEL_CEIL = {"factual": 0.9557, "overview": 0.3992, "multihop": 1.0000}  # §I99
LABEL_CEIL_OVERALL = 0.8016  # §I99
CAPTURE_THRESHOLD = 0.90
TOL = 1e-9


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def idcg(n: int, k: int) -> float:
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, vid, ok, detail=""):
        self.rows.append({"id": vid, "pass": bool(ok), "detail": detail})

    @property
    def failed(self):
        return [r for r in self.rows if not r["pass"]]


def rederive(src: dict):
    """Re-derive every quantity straight from the source per-query arrays."""
    per = {}
    for t in TYPES:
        recs = []
        for r in src["per_query"]:
            if r["query_type"] != t:
                continue
            n_rel, n_reach = r["n_relevant"], r["n_reachable"]
            pool_gold = int(round(r["C_pool_cov"] * n_reach))
            pool_gold = min(pool_gold, n_reach)
            idcg_r = idcg(n_rel, 20)
            m = r["C_metrics"]
            recs.append(dict(
                n_rel=n_rel, n_reach=n_reach, pool_gold=pool_gold,
                R_ceil_label=min(20, n_rel) / n_rel,
                R_ceil_pool=min(20, pool_gold) / n_rel,
                P_ceil_label=min(n_rel, 20) / 20,
                P_ceil_pool=min(pool_gold, 20) / 20,
                nDCG_ceil_pool=(idcg(pool_gold, 20) / idcg_r) if idcg_r > 0 else 0.0,
                realised_R=m["recall_at_20"], realised_P=m["precision_at_20"],
                realised_nDCG=m["ndcg_at_20"],
            ))
        per[t] = recs
    return per


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--source", default=str(SRC))
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    src = json.loads(Path(args.source).read_text())
    fo = json.loads(FO.read_text())
    c = Checks()
    d = art["diagnosis"]
    per = rederive(src)
    allr = [r for t in TYPES for r in per[t]]

    # V1 -- recorded input digests match the files on disk
    mi = art["meta"]["inputs"]
    c.add("V1_input_digest_t4", mi.get("t4_endpoint.json") == sha256(Path(args.source)),
          f"meta={mi.get('t4_endpoint.json','?')[:16]} disk={sha256(Path(args.source))[:16]}")
    c.add("V1b_input_digest_t0", mi.get("t0_baseline.json") == sha256(T0),
          f"meta={mi.get('t0_baseline.json','?')[:16]} disk={sha256(T0)[:16]}")
    c.add("V1c_input_digest_fo", mi.get("fusion_order.json") == sha256(FO),
          f"meta={mi.get('fusion_order.json','?')[:16]} disk={sha256(FO)[:16]}")

    # V2 -- population
    c.add("V2_n_queries_133", d["n_queries"] == len(src["per_query"]) == 133,
          f"artifact={d['n_queries']} source={len(src['per_query'])}")
    for t in TYPES:
        got = d["by_type"][t]["aggregate"]["n"]
        c.add(f"V2b_n_{t}", got == EXPECTED_N[t], f"got={got} expected={EXPECTED_N[t]}")

    # V3 -- realised values re-derived from C_metrics (G2)
    for name, key in (("realised_R", "realised_R"), ("realised_P", "realised_P"),
                      ("realised_nDCG", "realised_nDCG")):
        for t in TYPES:
            got = d["by_type"][t]["aggregate"][name]
            exp = mean(r[key] for r in per[t])
            c.add(f"V3_{name}_{t}", abs(got - exp) <= 1e-9, f"got={got:.10f} exp={exp:.10f}")
        got = d["overall"][name]
        exp = mean(r[key] for r in allr)
        c.add(f"V3_{name}_overall", abs(got - exp) <= 1e-9, f"got={got:.10f} exp={exp:.10f}")

    # V4 -- label ceilings reproduce §I99 (G3)
    for t in TYPES:
        got = d["by_type"][t]["aggregate"]["R_ceil_label"]
        c.add(f"V4_Rceil_label_{t}", abs(got - LABEL_CEIL[t]) <= 1e-4,
              f"got={got:.6f} expected={LABEL_CEIL[t]}")
    got = d["overall"]["R_ceil_label"]
    c.add("V4_Rceil_label_overall", abs(got - LABEL_CEIL_OVERALL) <= 1e-4,
          f"got={got:.6f} expected={LABEL_CEIL_OVERALL}")

    # V5 -- pool-aware ceilings re-derived per type (G4)
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        for name, key in (("R_ceil_pool", "R_ceil_pool"), ("P_ceil_pool", "P_ceil_pool"),
                          ("nDCG_ceil_pool", "nDCG_ceil_pool")):
            exp = mean(r[key] for r in per[t])
            c.add(f"V5_{name}_{t}", abs(a[name] - exp) <= 1e-9, f"got={a[name]:.10f} exp={exp:.10f}")

    # V6 -- capture identity: capture_X == mean over queries of (realised_i / ceil_i)
    #       (per-query ratio then averaged, the project's convention -- NOT ratio-of-means)
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        for fam, rk, ck in (("R", "realised_R", "R_ceil_pool"),
                            ("P", "realised_P", "P_ceil_pool"),
                            ("nDCG", "realised_nDCG", "nDCG_ceil_pool")):
            vals = [r[rk] / r[ck] for r in per[t] if r[ck] > 0]
            exp = mean(vals) if vals else None
            got = a[f"capture_{fam}"]
            ok = (exp is None and got is None) or (exp is not None and abs(got - exp) <= 1e-9)
            c.add(f"V6_capture_{fam}_{t}", ok, f"got={got} exp={exp}")
    for fam, rk, ck in (("R", "realised_R", "R_ceil_pool"),
                        ("P", "realised_P", "P_ceil_pool"),
                        ("nDCG", "realised_nDCG", "nDCG_ceil_pool")):
        vals = [r[rk] / r[ck] for r in allr if r[ck] > 0]
        exp = mean(vals) if vals else None
        got = d["overall"][f"capture_{fam}"]
        ok = (exp is None and got is None) or (exp is not None and abs(got - exp) <= 1e-9)
        c.add(f"V6_capture_{fam}_overall", ok, f"got={got} exp={exp}")

    # V7 -- the pool-aware ceiling never exceeds the label ceiling (P and R), and nDCG <= 1
    bad = []
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        if a["P_ceil_pool"] > a["P_ceil_label"] + 1e-9:
            bad.append(f"{t}:P")
        if a["R_ceil_pool"] > a["R_ceil_label"] + 1e-9:
            bad.append(f"{t}:R")
        if a["nDCG_ceil_pool"] > 1.0 + 1e-9:
            bad.append(f"{t}:nDCG")
    c.add("V7_ceil_pool_le_label", not bad, f"violations={bad}")

    # V8 -- the MMR set is the 16 §I100 recorded, and equals the O0/O1 pool-diff set (G5)
    ms = art["mmr_subset"]
    fired = sorted(r["id"] for r in fo["per_query"] if r.get("O0_mmr_fired"))
    pool_diff = sorted(r["id"] for r in fo["per_query"] if r.get("O1_pool_sha") != r.get("O0_pool_sha"))
    c.add("V8_mmr_set_16", len(fired) == 16 and ms["n_fired"] == 16, f"disk={len(fired)} art={ms['n_fired']}")
    c.add("V8b_mmr_set_eq_pool_diff", fired == pool_diff and ms["fired_set_equals_pool_diff"],
          f"eq={fired == pool_diff} art={ms['fired_set_equals_pool_diff']}")

    # V9 -- per query, pool_gold <= n_reach and <= n_rel
    bad = 0
    for r in src["per_query"]:
        pg = r["C_pool_cov"] * r["n_reachable"]
        if pg > r["n_reachable"] + 1e-9 or pg > r["n_relevant"] + 1e-9:
            bad += 1
    c.add("V9_pool_gold_le_reach", bad == 0, f"{bad} violations")

    # V10 -- no NaN / null in the aggregates
    bad = []
    for t in TYPES:
        for k, v in d["by_type"][t]["aggregate"].items():
            if v is None or (isinstance(v, float) and v != v):
                bad.append(f"{t}.{k}")
    c.add("V10_no_nan", not bad, f"{bad}")

    # V11 -- the verdict follows the fixed threshold (re-derived, not trusted)
    bad = []
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        for fam, ck in (("R", "capture_R"), ("P", "capture_P"), ("nDCG", "capture_nDCG")):
            want = "metric-limited" if a[ck] >= CAPTURE_THRESHOLD else "ranker-limited"
            if a[f"verdict_{fam}"] != want:
                bad.append(f"{t}:{fam}")
    c.add("V11_verdict_follows_threshold", not bad, f"violations={bad}")

    print(f"artifact : {args.artifact}")
    print(f"source   : {args.source}")
    print()
    for r in c.rows:
        print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['id']}" + (f"   {r['detail']}" if not r["pass"] else ""))
    print()
    print(f"{len(c.rows)} checks, {len(c.failed)} failed")
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main())
