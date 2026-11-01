"""4B — the ENDPOINT CUT measured as nDCG@k / R@k / P@k (not just coverage).

READ-ONLY. Reads ONE existing artifact and writes one JSON. No cluster, no LLM, no collection write.

    logs/p1/step10/t4_endpoint.json   -- arm C (CE, top-20) and arm W50 (CE, top-50), same pool

The question (pre-registration .hermes/plans/2026-10-31-p1-cut-ndcg-k-preregistration.md):

    Does widening the endpoint cut (20 -> 50) improve the RANKING, or only the coverage?  T4 (SSI97 P3)
    measured the coverage half (+0.1451) and only that.

Structural fact (asserted as a guard, G2): on 133/133 queries W50_pages[:20] == C_pages and the pools are
identical -- the CE's top-20 is a PREFIX of its top-50, so the cut cannot move any @20 metric. What the
extra slots (21-50) are worth is what this measures: nDCG@50 vs nDCG@20, R@50 vs R@20, with paired CIs.

Usage:  python logs/p1/step10/cut_ndcg_k.py [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
T4 = HERE / "t4_endpoint.json"
DEFAULT_OUT = HERE / "cut_ndcg_k.json"

TYPES = ("factual", "overview", "multihop")
KS = (20, 50)
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261031


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _idcg(n: int, k: int) -> float:
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


def metrics_at_k(pages, relevant, k):
    """evaluate_rag.py convention: binary gains, page-deduped, IDCG over min(n_rel, k)."""
    rel = set(relevant)
    seen, gains = set(), []
    for p in pages[:k]:
        if p in rel and p not in seen:
            gains.append(1)
            seen.add(p)
        else:
            gains.append(0)
    n_hits = sum(gains)
    recall = (n_hits / len(rel)) if rel else None
    precision = n_hits / k if k else None
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = _idcg(len(rel), k)
    ndcg = dcg / idcg if idcg > 0 else 0.0
    return recall, precision, ndcg


def ceilings(n_rel, n_reach, pool_gold, k):
    pool_gold = min(int(round(pool_gold)), n_reach)
    idcg_r = _idcg(n_rel, k)
    return dict(
        R_ceil_label=min(k, n_rel) / n_rel,
        R_ceil_pool=min(k, pool_gold) / n_rel,
        P_ceil_label=min(n_rel, k) / k,
        P_ceil_pool=min(pool_gold, k) / k,
        nDCG_ceil_pool=(_idcg(pool_gold, k) / idcg_r) if idcg_r > 0 else 0.0,
    )


def _boot_ci(deltas, rng=None):
    """Paired percentile bootstrap CI of the mean. Seeds FRESH per call (the seed is the identity),
    so any block can be re-derived independently -- a running RNG would make the CI depend on the
    order the blocks were computed in."""
    n = len(deltas)
    if n == 0:
        return (None, None)
    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(BOOTSTRAP_N):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * BOOTSTRAP_N)]
    hi = means[int(0.975 * BOOTSTRAP_N) - 1]
    return (lo, hi)


def run(t4: dict) -> dict:
    rows = t4["per_query"]
    out = {"n_queries": len(rows), "ks": list(KS), "by_type": {}, "overall": {}}

    for t in TYPES:
        sel = [r for r in rows if r["query_type"] == t]
        if not sel:
            continue
        recs = []
        for r in sel:
            rel = r["relevant_pages"]
            n_rel, n_reach = r["n_relevant"], r["n_reachable"]
            pool_gold = r["C_pool_cov"] * n_reach
            C, W = r["C_pages"], r["W50_pages"]
            m20 = metrics_at_k(C, rel, 20)          # arm C @20
            m50 = metrics_at_k(W, rel, 50)          # arm W50 @50
            c20, c50 = ceilings(n_rel, n_reach, pool_gold, 20), ceilings(n_rel, n_reach, pool_gold, 50)
            recs.append(dict(
                id=r["id"], n_rel=n_rel, n_reach=n_reach, pool_gold=pool_gold,
                R20=m20[0], P20=m20[1], nDCG20=m20[2],
                R50=m50[0], P50=m50[1], nDCG50=m50[2],
                dR=m50[0] - m20[0], dP=m50[1] - m20[1], dnDCG=m50[2] - m20[2],
                extra_slots_gold=len(set(W[20:50]) & set(rel)),
                **{f"ceil20_{k}": v for k, v in c20.items()},
                **{f"ceil50_{k}": v for k, v in c50.items()},
            ))
        rng = random.Random(BOOTSTRAP_SEED)
        agg = {"n": len(recs)}
        for key in ("R20", "P20", "nDCG20", "R50", "P50", "nDCG50",
                    "extra_slots_gold", "ceil20_R_ceil_label", "ceil20_R_ceil_pool",
                    "ceil20_P_ceil_pool", "ceil20_nDCG_ceil_pool",
                    "ceil50_R_ceil_label", "ceil50_R_ceil_pool",
                    "ceil50_P_ceil_pool", "ceil50_nDCG_ceil_pool"):
            agg[key] = _mean(r[key] for r in recs)
        for name, key in (("dR", "dR"), ("dP", "dP"), ("dnDCG", "dnDCG")):
            ds = [r[key] for r in recs]
            lo, hi = _boot_ci(ds, rng)
            agg[name] = _mean(ds)
            agg[f"{name}_ci"] = [lo, hi]
            agg[f"{name}_resolved"] = (lo is not None and (lo > 0 or hi < 0))
            agg[f"{name}_wlt"] = [sum(1 for d in ds if d > 0), sum(1 for d in ds if d < 0),
                                  sum(1 for d in ds if d == 0)]
        out["by_type"][t] = {"aggregate": agg, "per_query": recs}

    allrecs = [r for t in TYPES for r in out["by_type"][t]["per_query"]]
    rng = random.Random(BOOTSTRAP_SEED)
    ov = {"n": len(allrecs)}
    for key in ("R20", "P20", "nDCG20", "R50", "P50", "nDCG50",
                "ceil20_R_ceil_pool", "ceil20_P_ceil_pool", "ceil20_nDCG_ceil_pool",
                "ceil50_R_ceil_pool", "ceil50_P_ceil_pool", "ceil50_nDCG_ceil_pool"):
        ov[key] = _mean(r[key] for r in allrecs)
    for name, key in (("dR", "dR"), ("dP", "dP"), ("dnDCG", "dnDCG")):
        ds = [r[key] for r in allrecs]
        lo, hi = _boot_ci(ds, rng)
        ov[name] = _mean(ds)
        ov[f"{name}_ci"] = [lo, hi]
        ov[f"{name}_resolved"] = (lo is not None and (lo > 0 or hi < 0))
        ov[f"{name}_wlt"] = [sum(1 for d in ds if d > 0), sum(1 for d in ds if d < 0),
                             sum(1 for d in ds if d == 0)]
    out["overall"] = ov
    out["comparability"] = comparability(allrecs)
    return out


def comparability(allrecs):
    """⚠️ nDCG@50 vs nDCG@20 is only a LIKE-FOR-LIKE comparison where the IDCG denominator is the SAME,
    i.e. where n_rel <= 20 (then IDCG@20 == IDCG@50 and the 50-list is a superset, so the delta is
    NON-NEGATIVE BY CONSTRUCTION). Split the population so the aggregate is not read as a finding."""
    blocks = {}
    for label, pred in (("n_rel_le_20_same_denominator", lambda n: n <= 20),
                        ("n_rel_gt_20_comparable", lambda n: n > 20)):
        sel = [r for r in allrecs if pred(r["n_rel"])]
        rng = random.Random(BOOTSTRAP_SEED)
        ds = [r["dnDCG"] for r in sel]
        lo, hi = _boot_ci(ds, rng) if ds else (None, None)
        blocks[label] = dict(
            n=len(sel),
            mean_dnDCG=_mean(ds),
            dnDCG_ci=[lo, hi],
            dnDCG_resolved=(lo is not None and (lo > 0 or hi < 0)),
            mean_dR=_mean(r["dR"] for r in sel),
            mean_extra_slots_gold=_mean(r["extra_slots_gold"] for r in sel),
        )
    return blocks


def guards(t4: dict) -> dict:
    rows = t4["per_query"]
    prefix_bad = [r["id"] for r in rows if r["W50_pages"][:len(r["C_pages"])] != r["C_pages"]]
    pool_bad = [r["id"] for r in rows if r["C_pool_sha"] != r["W50_pool_sha"]]
    len_bad = [r["id"] for r in rows if len(r["W50_pages"]) < len(r["C_pages"])]
    return {
        "G1_population": len(rows),
        "G2_prefix_identity_bad": prefix_bad,
        "G2b_pool_sha_bad": pool_bad,
        "G5_len_bad": len_bad,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    t4 = json.loads(T4.read_text())
    res = {
        "meta": {
            "harness": "cut_ndcg_k.py",
            "read_only": True,
            "inputs": {"t4_endpoint.json": _sha256(T4)},
            "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
            "definition": ("arm C @20 vs arm W50 @50; paired per-query deltas; nDCG/R/P by the "
                           "evaluate_rag.py convention; ceilings label + pool-aware"),
        },
        "guards": guards(t4),
        "cut_ndcg_k": run(t4),
    }
    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))
    d = res["cut_ndcg_k"]

    print(f"wrote {out}  ({out.stat().st_size} bytes)")
    g = res["guards"]
    print(f"G1 n={g['G1_population']}  G2 prefix-bad={len(g['G2_prefix_identity_bad'])}  "
          f"pool-sha-bad={len(g['G2b_pool_sha_bad'])}  len-bad={len(g['G5_len_bad'])}")
    print()
    hdr = (f"{'type':10s} {'nDCG20':>7s} {'nDCG50':>7s} {'d nDCG':>8s} {'CI':>20s} {'res':>4s} | "
           f"{'R20':>6s} {'R50':>6s} {'dR':>7s} {'res':>4s} | {'extra':>6s}")
    print(hdr)
    print("-" * len(hdr))
    for t in TYPES + ("overall",):
        a = d["overall"] if t == "overall" else d["by_type"][t]["aggregate"]
        ci = f"[{a['dnDCG_ci'][0]:+.4f},{a['dnDCG_ci'][1]:+.4f}]"
        print(f"{t:10s} {a['nDCG20']:7.4f} {a['nDCG50']:7.4f} {a['dnDCG']:+8.4f} {ci:>20s} "
              f"{'YES' if a['dnDCG_resolved'] else 'no':>4s} | {a['R20']:6.4f} {a['R50']:6.4f} "
              f"{a['dR']:+7.4f} {'YES' if a['dR_resolved'] else 'no':>4s} | "
              f"{a.get('extra_slots_gold', 0):6.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
