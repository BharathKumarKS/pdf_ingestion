"""5A — the OVERVIEW METRIC DIAGNOSIS: is overview's loss the measuring stick or the ranker?

READ-ONLY. Reads three existing artifacts and writes one JSON. No cluster, no LLM, no collection write.

    logs/p1/step10/t4_endpoint.json    -- arm C (the product): C_metrics, C_pool_cov, C_pages
    logs/p1/step10/t0_baseline.json    -- the funnel (only for the G2/G3 cross-check)
    logs/p1/step10/fusion_order.json   -- O0_mmr_fired, O0/O1 pool sha + metrics (the MMR subset check)

The question (pre-registration .hermes/plans/2026-10-31-p1-overview-metric-diagnosis-preregistration.md):

    Is overview's low score an ARTIFACT of the metric (a broad label set making recall's denominator
    enormous) or a REAL ranking loss (the ranker sitting far below its own ceiling)?

Method: per query, put the realised value beside BOTH ceilings -- the LABEL ceiling (what the register
already reports) and the POOL-AWARE ceiling (the best any ranker could do on the gold the product's pool
actually holds). The ratio realised/ceiling is the CAPTURE. capture >= 0.90 => metric-limited;
capture < 0.90 => ranker-limited. The threshold is fixed in the pre-registration and not moved here.

Usage:  python logs/p1/step10/overview_metric_diag.py [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
T4 = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"
FO = HERE / "fusion_order.json"
DEFAULT_OUT = HERE / "overview_metric_diag.json"

TYPES = ("factual", "overview", "multihop")
K = 20
CAPTURE_THRESHOLD = 0.90  # fixed by the pre-registration §5; do NOT move after the run


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _idcg(n: int, k: int) -> float:
    """Ideal DCG with binary gains, page-deduped -- identical to evaluate_rag.py:406-407."""
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


def _ceilings(n_rel: int, n_reach: int, pool_gold: float, k: int) -> dict:
    pool_gold = min(int(round(pool_gold)), n_reach)  # a page COUNT; cannot exceed the reachable gold
    idcg_realised = _idcg(n_rel, k)
    return {
        # label-side (what the register already reports)
        "R_ceil_label": min(k, n_rel) / n_rel,
        "P_ceil_label": min(n_rel, k) / k,
        # pool-aware (the honest achievable bound)
        "R_ceil_pool": min(k, pool_gold) / n_rel,
        "P_ceil_pool": min(pool_gold, k) / k,
        "nDCG_ceil_pool": (_idcg(pool_gold, k) / idcg_realised) if idcg_realised > 0 else 0.0,
    }


def diagnose(t4: dict) -> dict:
    rows = t4["per_query"]
    out = {"n_queries": len(rows), "k": K, "capture_threshold": CAPTURE_THRESHOLD,
           "by_type": {}, "overall": {}}

    for t in TYPES:
        sel = [r for r in rows if r["query_type"] == t]
        if not sel:
            continue
        recs = []
        for r in sel:
            n_rel = r["n_relevant"]
            n_reach = r["n_reachable"]
            pool_gold = r["C_pool_cov"] * n_reach
            rel = set(r["relevant_pages"])
            gold_in_C = len(set(r["C_pages"]) & rel)
            c = _ceilings(n_rel, n_reach, pool_gold, K)
            m = r["C_metrics"]
            rec = dict(
                id=r["id"], n_rel=n_rel, n_reach=n_reach, pool_gold=pool_gold,
                pool_size=r["C_pool_size"], gold_in_C=gold_in_C,
                realised_R=m["recall_at_20"], realised_P=m["precision_at_20"],
                realised_nDCG=m["ndcg_at_20"],
                **c,
            )
            # capture ratios (realised / ceiling), guarded against a zero ceiling
            rec["capture_R"] = rec["realised_R"] / c["R_ceil_pool"] if c["R_ceil_pool"] > 0 else None
            rec["capture_P"] = rec["realised_P"] / c["P_ceil_pool"] if c["P_ceil_pool"] > 0 else None
            rec["capture_nDCG"] = rec["realised_nDCG"] / c["nDCG_ceil_pool"] if c["nDCG_ceil_pool"] > 0 else None
            recs.append(rec)

        agg = {"n": len(recs)}
        for key in ("n_rel", "n_reach", "pool_gold", "pool_size",
                    "R_ceil_label", "R_ceil_pool", "P_ceil_label", "P_ceil_pool", "nDCG_ceil_pool",
                    "realised_R", "realised_P", "realised_nDCG",
                    "capture_R", "capture_P", "capture_nDCG"):
            agg[key] = _mean(r[key] for r in recs if r[key] is not None)
        # pool_gold distribution
        pg = sorted(r["pool_gold"] for r in recs)
        agg["pool_gold_median"] = pg[len(pg) // 2]
        agg["pool_gold_min"] = pg[0]
        agg["pool_gold_max"] = pg[-1]
        agg["frac_pool_gold_ge_k"] = _mean(1.0 if r["pool_gold"] >= K else 0.0 for r in recs)
        # verdict per family, from the fixed threshold
        for fam, key in (("R", "capture_R"), ("P", "capture_P"), ("nDCG", "capture_nDCG")):
            cap = agg[key]
            agg[f"verdict_{fam}"] = "metric-limited" if cap >= CAPTURE_THRESHOLD else "ranker-limited"
        out["by_type"][t] = {"aggregate": agg, "per_query": recs}

    allrecs = [r for t in out["by_type"].values() for r in t["per_query"]]
    ov = {"n": len(allrecs)}
    for key in ("R_ceil_label", "R_ceil_pool", "P_ceil_label", "P_ceil_pool", "nDCG_ceil_pool",
                "realised_R", "realised_P", "realised_nDCG",
                "capture_R", "capture_P", "capture_nDCG"):
        ov[key] = _mean(r[key] for r in allrecs if r[key] is not None)
    for fam, key in (("R", "capture_R"), ("P", "capture_P"), ("nDCG", "capture_nDCG")):
        cap = ov[key]
        ov[f"verdict_{fam}"] = "metric-limited" if cap >= CAPTURE_THRESHOLD else "ranker-limited"
    out["overall"] = ov
    return out


def mmr_subset(fo: dict) -> dict:
    """Does MMR move the endpoint metric on the very queries where it fires? (§I100 item 4's set.)"""
    rows = fo["per_query"]
    fired = [r for r in rows if r.get("O0_mmr_fired")]
    # §I100 item 4: O1's pool differs from O0's on exactly the queries where O0's MMR fired
    set_eq = sorted(r["id"] for r in fired) == sorted(
        r["id"] for r in rows if r.get("O1_pool_sha") != r.get("O0_pool_sha"))
    per_type = {}
    for t in TYPES:
        sel = [r for r in fired if r["query_type"] == t]
        per_type[t] = len(sel)
    keys = ("ndcg_at_20", "recall_at_20", "mrr_at_20")
    deltas = {k: _mean(r["O1_metrics"][k] - r["O0_metrics"][k] for r in fired) for k in keys}
    per_type_deltas = {}
    for t in TYPES:
        sel = [r for r in fired if r["query_type"] == t]
        per_type_deltas[t] = {k: (_mean(r["O1_metrics"][k] - r["O0_metrics"][k] for r in sel) if sel else None)
                              for k in keys}
    return {
        "n_fired": len(fired),
        "n_total": len(rows),
        "fired_set_equals_pool_diff": set_eq,
        "fired_by_type": per_type,
        "O1_minus_O0_on_firing": deltas,
        "O1_minus_O0_on_firing_by_type": per_type_deltas,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    t4 = json.loads(T4.read_text())
    t0 = json.loads(T0.read_text())
    fo = json.loads(FO.read_text())

    res = {
        "meta": {
            "harness": "overview_metric_diag.py",
            "read_only": True,
            "capture_threshold": CAPTURE_THRESHOLD,
            "inputs": {
                "t4_endpoint.json": _sha256(T4),
                "t0_baseline.json": _sha256(T0),
                "fusion_order.json": _sha256(FO),
            },
            "definition": ("realised vs LABEL and POOL-AWARE ceilings per query, averaged within type; "
                           "capture = realised/ceiling_pool; metric-limited iff capture >= 0.90"),
        },
        "diagnosis": diagnose(t4),
        "mmr_subset": mmr_subset(fo),
    }

    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))
    d = res["diagnosis"]

    print(f"wrote {out}  ({out.stat().st_size} bytes)")
    print()
    hdr = (f"{'type':10s} {'R@20':>6s} {'Rcl_pool':>8s} {'cap_R':>6s} | "
           f"{'P@20':>6s} {'Pcl_pool':>8s} {'cap_P':>6s} | "
           f"{'nDCG':>6s} {'ncl_pool':>8s} {'cap_nD':>6s} | {'poolgold>=20':>12s}")
    print(hdr)
    print("-" * len(hdr))
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        print(f"{t:10s} {a['realised_R']:6.3f} {a['R_ceil_pool']:8.3f} {a['capture_R']:6.3f} | "
              f"{a['realised_P']:6.3f} {a['P_ceil_pool']:8.3f} {a['capture_P']:6.3f} | "
              f"{a['realised_nDCG']:6.3f} {a['nDCG_ceil_pool']:8.3f} {a['capture_nDCG']:6.3f} | "
              f"{a['frac_pool_gold_ge_k']:12.2f}")
    a = d["overall"]
    print(f"{'ALL 133':10s} {a['realised_R']:6.3f} {a['R_ceil_pool']:8.3f} {a['capture_R']:6.3f} | "
          f"{a['realised_P']:6.3f} {a['P_ceil_pool']:8.3f} {a['capture_P']:6.3f} | "
          f"{a['realised_nDCG']:6.3f} {a['nDCG_ceil_pool']:8.3f} {a['capture_nDCG']:6.3f} |")
    print()
    print("verdicts (overview):", {f: d['by_type']['overview']['aggregate'][f'verdict_{f}'] for f in ('R', 'P', 'nDCG')})
    ms = res["mmr_subset"]
    print(f"MMR: fired {ms['n_fired']}/{ms['n_total']} by type {ms['fired_by_type']}; "
          f"set==pool-diff {ms['fired_set_equals_pool_diff']}")
    print("     O1-O0 on firing queries:", {k: round(v, 5) for k, v in ms["O1_minus_O0_on_firing"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
