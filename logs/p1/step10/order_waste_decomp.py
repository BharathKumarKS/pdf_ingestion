"""Stage 0 — the root-cause decomposition of the endpoint's top-20 loss, PER TYPE.

READ-ONLY. Reads only two existing artifacts and writes one JSON. No collection is touched,
no LLM call, no re-ingest.

    logs/p1/step10/t4_endpoint.json   -- arms C (CE), N (no CE = the pool's own order), Q, W50
    logs/p1/step10/t0_baseline.json   -- the four-boundary funnel, per type

The question this answers, which no existing artifact answers directly:

    Of a query's achievable recall at the endpoint, how much is lost to
      (a) the POOL not containing the gold            -> "coverage",
      (b) the POOL's own ORDER not surfacing it       -> "order",
      (c) the CROSS-ENCODER reordering it lower       -> "ce"
    ... and how do those three split BY QUERY TYPE?

Definitions, all per query, then averaged within a type (never pooled across types):

    n_rel                 labelled pages for the query
    n_reach               of those, reachable (present in the index window)
    pool_gold             = C_pool_cov * n_reach   (labelled pages actually in the product's pool)
    R_ceil_20             = min(20, n_rel) / n_rel         the label-imposed ceiling at 20 slots
    pool_oracle_20        = min(20, pool_gold) / n_rel     the BEST any ranker could do on this pool
    realised_N            = |N_pages ∩ relevant| / n_rel    the pool's own order (no cross-encoder)
    realised_C            = |C_pages ∩ relevant| / n_rel    the product (cross-encoder)

    waste_pool   = R_ceil_20     - pool_oracle_20   the pool does not hold enough gold
    waste_order  = pool_oracle_20 - realised_N      the pool's order buries gold it holds
    waste_ce     = realised_N    - realised_C       the cross-encoder buries it further

⚠️ pool_oracle_20 is an UPPER BOUND: it assumes a ranker that picks the gold perfectly out of the
pool the product built. It is not achievable, and it is not a target -- it is the size of the
recoverable space, which is what tells you whether to look at retrieval, ordering or the CE.

Usage:  python logs/p1/step10/order_waste_decomp.py [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
T4 = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"
DEFAULT_OUT = HERE / "order_waste_decomp.json"

TYPES = ("factual", "overview", "multihop")
K = 20


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def decompose(t4: dict) -> dict:
    rows = t4["per_query"]
    out = {"n_queries": len(rows), "k": K, "by_type": {}, "overall": {}}

    for t in TYPES:
        sel = [r for r in rows if r["query_type"] == t]
        if not sel:
            continue
        recs = []
        for r in sel:
            rel = set(r["relevant_pages"])
            n_rel = r["n_relevant"]
            n_reach = r["n_reachable"]
            pool_gold = r["C_pool_cov"] * n_reach
            recs.append(
                dict(
                    id=r["id"],
                    n_rel=n_rel,
                    n_reach=n_reach,
                    pool_gold=pool_gold,
                    pool_size=r["C_pool_size"],
                    R_ceil_20=min(K, n_rel) / n_rel,
                    pool_oracle_20=min(K, pool_gold) / n_rel,
                    realised_N=len(set(r["N_pages"]) & rel) / n_rel,
                    realised_C=len(set(r["C_pages"]) & rel) / n_rel,
                    gold_in_N=len(set(r["N_pages"]) & rel),
                    gold_in_C=len(set(r["C_pages"]) & rel),
                    gold_in_pool=pool_gold,
                )
            )

        agg = {
            "n": len(recs),
            "mean_n_rel": _mean(r["n_rel"] for r in recs),
            "mean_n_reach": _mean(r["n_reach"] for r in recs),
            "mean_pool_size": _mean(r["pool_size"] for r in recs),
            "mean_pool_gold": _mean(r["pool_gold"] for r in recs),
            "R_ceil_20": _mean(r["R_ceil_20"] for r in recs),
            "pool_oracle_20": _mean(r["pool_oracle_20"] for r in recs),
            "realised_N": _mean(r["realised_N"] for r in recs),
            "realised_C": _mean(r["realised_C"] for r in recs),
        }
        agg["waste_pool"] = agg["R_ceil_20"] - agg["pool_oracle_20"]
        agg["waste_order"] = agg["pool_oracle_20"] - agg["realised_N"]
        agg["waste_ce"] = agg["realised_N"] - agg["realised_C"]
        agg["recoverable_total"] = agg["R_ceil_20"] - agg["realised_C"]
        # share of the total recoverable loss attributable to each mechanism
        tot = agg["recoverable_total"]
        for k_ in ("waste_pool", "waste_order", "waste_ce"):
            agg[f"share_{k_}"] = (agg[k_] / tot) if tot else None
        agg["ce_ceiling_gain"] = max(0.0, agg["realised_N"] - agg["realised_C"])
        out["by_type"][t] = {"aggregate": agg, "per_query": recs}

    # overall = mean over ALL queries, not over the type means (the types are unequal in n)
    allrecs = [r for t in out["by_type"].values() for r in t["per_query"]]
    ov = {
        "n": len(allrecs),
        "R_ceil_20": _mean(r["R_ceil_20"] for r in allrecs),
        "pool_oracle_20": _mean(r["pool_oracle_20"] for r in allrecs),
        "realised_N": _mean(r["realised_N"] for r in allrecs),
        "realised_C": _mean(r["realised_C"] for r in allrecs),
    }
    ov["waste_pool"] = ov["R_ceil_20"] - ov["pool_oracle_20"]
    ov["waste_order"] = ov["pool_oracle_20"] - ov["realised_N"]
    ov["waste_ce"] = ov["realised_N"] - ov["realised_C"]
    ov["recoverable_total"] = ov["R_ceil_20"] - ov["realised_C"]
    out["overall"] = ov
    return out


def funnel(t0: dict) -> dict:
    """The four-boundary coverage funnel per type, straight from T0's aggregate."""
    ag = t0["aggregate"]
    out = {}
    for t in ("overall",) + TYPES:
        row = {}
        for stage in ("base", "cut", "fusion", "ce"):
            blk = ag[stage]
            b = blk.get("overall") if t == "overall" else (blk.get("by_type") or {}).get(t)
            if not b:
                continue
            row[stage] = {
                "coverage": b.get("coverage_reachable", b.get("coverage")),
                "ndcg_at_20": b.get("ndcg_at_20"),
                "recall_at_20": b.get("recall_at_20"),
            }
        out[t] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    t4 = json.loads(T4.read_text())
    t0 = json.loads(T0.read_text())

    res = {
        "meta": {
            "harness": "order_waste_decomp.py",
            "read_only": True,
            "inputs": {
                "t4_endpoint.json": _sha256(T4),
                "t0_baseline.json": _sha256(T0),
            },
            "definition": "per-query ratios, averaged within type; oracle = best-20-pick from the product's own pool",
        },
        "decomposition": decompose(t4),
        "funnel_coverage": funnel(t0),
    }

    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))

    d = res["decomposition"]
    print(f"wrote {out}  ({out.stat().st_size} bytes)")
    print()
    hdr = f"{'type':10s} {'R_ceil':>8s} {'oracle':>8s} {'N':>8s} {'C':>8s} | {'w_pool':>7s} {'w_order':>8s} {'w_ce':>7s} | {'pool_gold':>9s}"
    print(hdr)
    print("-" * len(hdr))
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        print(
            f"{t:10s} {a['R_ceil_20']:8.4f} {a['pool_oracle_20']:8.4f} {a['realised_N']:8.4f} "
            f"{a['realised_C']:8.4f} | {a['waste_pool']:7.4f} {a['waste_order']:8.4f} "
            f"{a['waste_ce']:7.4f} | {a['mean_pool_gold']:9.1f}"
        )
    a = d["overall"]
    print(
        f"{'ALL 133':10s} {a['R_ceil_20']:8.4f} {a['pool_oracle_20']:8.4f} {a['realised_N']:8.4f} "
        f"{a['realised_C']:8.4f} | {a['waste_pool']:7.4f} {a['waste_order']:8.4f} {a['waste_ce']:7.4f} |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
