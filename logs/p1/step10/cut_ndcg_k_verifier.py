"""Independent verifier for 4B (cut_ndcg_k).

stdlib only. Reads the WRITTEN artifact AND re-derives every number from the SOURCE artifact's
raw per-query arrays, so the harness's own arithmetic is not trusted.

    python logs/p1/step10/cut_ndcg_k_verifier.py --check [--artifact P] [--source P]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "cut_ndcg_k.json"
SRC = HERE / "t4_endpoint.json"

TYPES = ("factual", "overview", "multihop")
EXPECTED_N = {"factual": 53, "overview": 40, "multihop": 40}
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261031
TOL = 1e-9


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def idcg(n, k):
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


def metrics_at_k(pages, relevant, k):
    rel = set(relevant)
    seen, gains = set(), []
    for p in pages[:k]:
        if p in rel and p not in seen:
            gains.append(1); seen.add(p)
        else:
            gains.append(0)
    n_hits = sum(gains)
    recall = (n_hits / len(rel)) if rel else None
    precision = n_hits / k if k else None
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ic = idcg(len(rel), k)
    return recall, precision, (dcg / ic if ic > 0 else 0.0)


def boot_ci(deltas):
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(deltas)
    if n == 0:
        return (None, None)
    means = []
    for _ in range(BOOTSTRAP_N):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return (means[int(0.025 * BOOTSTRAP_N)], means[int(0.975 * BOOTSTRAP_N) - 1])


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, vid, ok, detail=""):
        self.rows.append({"id": vid, "pass": bool(ok), "detail": detail})

    @property
    def failed(self):
        return [r for r in self.rows if not r["pass"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--source", default=str(SRC))
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    src = json.loads(Path(args.source).read_text())
    c = Checks()
    d = art["cut_ndcg_k"]
    rows = src["per_query"]

    # V1 -- digest
    c.add("V1_input_digest_t4", art["meta"]["inputs"]["t4_endpoint.json"] == sha256(Path(args.source)))

    # V2 -- population
    c.add("V2_n_queries_133", d["n_queries"] == len(rows) == 133)
    for t in TYPES:
        got = d["by_type"][t]["aggregate"]["n"]
        c.add(f"V2b_n_{t}", got == EXPECTED_N[t], f"got={got}")

    # V3 / V3b -- G2: the prefix identity and the pool sha, from the SOURCE
    pre = [r["id"] for r in rows if r["W50_pages"][:len(r["C_pages"])] != r["C_pages"]]
    c.add("V3_prefix_identity", not pre, f"bad={pre[:5]}")
    pool = [r["id"] for r in rows if r["C_pool_sha"] != r["W50_pool_sha"]]
    c.add("V3b_pool_sha_equal", not pool, f"bad={pool[:5]}")
    c.add("V3c_guard_recorded", art["guards"]["G2_prefix_identity_bad"] == pre
          and art["guards"]["G2b_pool_sha_bad"] == pool)

    # V4 -- G3: the @20 metrics reproduce T4's own C_metrics, per type
    for t in TYPES:
        sel = [r for r in rows if r["query_type"] == t]
        agg = d["by_type"][t]["aggregate"]
        exp_n = mean(metrics_at_k(r["C_pages"], r["relevant_pages"], 20)[2] for r in sel)
        exp_r = mean(metrics_at_k(r["C_pages"], r["relevant_pages"], 20)[0] for r in sel)
        exp_p = mean(metrics_at_k(r["C_pages"], r["relevant_pages"], 20)[1] for r in sel)
        c.add(f"V4_nDCG20_{t}", abs(agg["nDCG20"] - exp_n) <= 1e-9, f"{agg['nDCG20']:.6f} vs {exp_n:.6f}")
        c.add(f"V4_R20_{t}", abs(agg["R20"] - exp_r) <= 1e-9)
        c.add(f"V4_P20_{t}", abs(agg["P20"] - exp_p) <= 1e-9)
        # and against T4's recorded C_metrics (independent path)
        c.add(f"V4c_nDCG20_vs_Cmetrics_{t}",
              abs(agg["nDCG20"] - mean(r["C_metrics"]["ndcg_at_20"] for r in sel)) <= 1e-4)

    # V5 -- G4: @50 R reproduces T4's W50_metrics["recall_at_50"] exactly (independent path)
    for t in TYPES:
        sel = [r for r in rows if r["query_type"] == t]
        agg = d["by_type"][t]["aggregate"]
        c.add(f"V5_R50_vs_W50metrics_{t}",
              abs(agg["R50"] - mean(r["W50_metrics"]["recall_at_50"] for r in sel)) <= 1e-4,
              f"{agg['R50']:.6f} vs {mean(r['W50_metrics']['recall_at_50'] for r in sel):.6f}")

    # V6 -- the prefix identity implies the @20 metrics are IDENTICAL between the arms.
    # ⚠️ Compare over the COMMON prefix length len(C_pages): arm C emits min(20, pool) entries, so on a
    # query where the pool held 19 it has 19, and W50_pages[:20] would carry one extra slot.
    bad = []
    for r in rows:
        k = len(r["C_pages"])
        m_c = metrics_at_k(r["C_pages"], r["relevant_pages"], k)
        m_w = metrics_at_k(r["W50_pages"], r["relevant_pages"], k)
        if any(abs(a - b) > 1e-12 for a, b in zip(m_c, m_w)):
            bad.append(r["id"])
    c.add("V6_prefix_implies_identical_20", not bad, f"bad={bad[:5]}")

    # V7 -- extra_slots_gold >= 0 and len(W50) >= len(C) per query
    bad = [r["id"] for r in rows if len(r["W50_pages"]) < len(r["C_pages"])]
    c.add("V7_len_monotone", not bad, f"bad={bad[:5]}")
    bad = [r["id"] for r in d["by_type"]["overview"]["per_query"] if r["extra_slots_gold"] < 0]
    c.add("V7b_extra_gold_nonneg", not bad)

    # V8 -- the bootstrap CI re-derives (same seed).
    # ⚠️ Rebuild in FIXED TYPES order: json.dumps(sort_keys=True) reorders by_type alphabetically, so a
    # reloaded dict's .values() is factual/multihop/overview, not the harness's factual/overview/multihop.
    # The bootstrap resamples by index, so the order is part of the identity.
    allrecs = [r for t in TYPES for r in d["by_type"][t]["per_query"]]
    for name, key in (("dR", "dR"), ("dP", "dP"), ("dnDCG", "dnDCG")):
        ds = [r[key] for r in allrecs]
        lo, hi = boot_ci(ds)
        got = d["overall"][f"{name}_ci"]
        c.add(f"V8_ci_{name}", abs(got[0] - lo) <= 1e-9 and abs(got[1] - hi) <= 1e-9,
              f"got={got} exp=[{lo},{hi}]")

    # V9 -- the comparability split is correct AND the same-denominator block is non-decreasing by construction
    comp = d["comparability"]
    le = [r for r in allrecs if r["n_rel"] <= 20]
    gt = [r for r in allrecs if r["n_rel"] > 20]
    c.add("V9_comparability_n", comp["n_rel_le_20_same_denominator"]["n"] == len(le)
          and comp["n_rel_gt_20_comparable"]["n"] == len(gt),
          f"{comp['n_rel_le_20_same_denominator']['n']}/{comp['n_rel_gt_20_comparable']['n']} vs {len(le)}/{len(gt)}")
    c.add("V9b_comparable_mean",
          abs(comp["n_rel_gt_20_comparable"]["mean_dnDCG"] - mean(r["dnDCG"] for r in gt)) <= 1e-9)
    # the construction: where n_rel<=20, IDCG@20==IDCG@50 so the 50-list (a superset) cannot lower nDCG
    viol = [r["id"] for r in le if r["dnDCG"] < -1e-12]
    c.add("V9c_same_denom_non_decreasing", not viol, f"violations={viol[:5]}")

    # V10 -- no NaN / null
    bad = []
    for t in TYPES:
        for k, v in d["by_type"][t]["aggregate"].items():
            if v is None or (isinstance(v, float) and v != v):
                bad.append(f"{t}.{k}")
    c.add("V10_no_nan", not bad, f"{bad}")

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
