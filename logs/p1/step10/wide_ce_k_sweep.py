"""WIDE-CE k SWEEP — the cross-encoder's full ranking over a wide pool, per query type.

READ-ONLY. Reads ONE existing artifact and writes one JSON. No cluster, no LLM, no collection write.

    logs/p1/step10/wide_ce_endpoint.json  -- CE_pages (the CE's full ranking over the wide pool, k<=500)

The question (pre-registration .hermes/plans/2026-11-01-p1-wide-ce-endpoint-preregistration.md):

    Does a wider pool + higher k improve the metric per type, on the LAST layer (the cross-encoder)?
    The POOL arm is `wide_pool_k_sweep.py`; this is the CE arm.

Usage:  python logs/p1/step10/wide_ce_k_sweep.py [--out PATH]
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
RUN = HERE / "wide_ce_endpoint.json"
REF = HERE / "per_type_k_sweep.json"     # SSI105, for the reported CE@20 cross-check
DEFAULT_OUT = HERE / "wide_ce_k_sweep.json"

TYPES = ("factual", "overview", "multihop")
KS = (1, 2, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200, 250)
K_ANCHOR = 20
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261031
TOL = 5e-5


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _idcg(n, k):
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


def metrics_at_k(pages, rel, k):
    rel = set(rel)
    seen, gains = set(), []
    for p in pages[:k]:
        if p in rel and p not in seen:
            gains.append(1); seen.add(p)
        else:
            gains.append(0)
    n_hits = sum(gains)
    rec = (n_hits / len(rel)) if rel else None
    prec = n_hits / k if k else None
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = _idcg(len(rel), k)
    return rec, prec, (dcg / idcg if idcg > 0 else 0.0)


def coverage_at_k(pages, rel, n_reach, k):
    return (len(set(pages[:k]) & set(rel)) / n_reach) if n_reach else None


def ceilings(n_rel, n_reach, pool_gold, k):
    pg = min(int(round(pool_gold)), n_reach)
    ir = _idcg(n_rel, k)
    return (min(k, pg) / n_rel if n_rel else 0.0, (_idcg(pg, k) / ir) if ir > 0 else 0.0)


def _ci(ds):
    n = len(ds)
    if n == 0:
        return (None, None)
    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(BOOTSTRAP_N):
        s = 0.0
        for _ in range(n):
            s += ds[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return (means[int(0.025 * BOOTSTRAP_N)], means[int(0.975 * BOOTSTRAP_N) - 1])


def _delta(recs, key):
    ds = [r[key] for r in recs if r.get(key) is not None]
    lo, hi = _ci(ds)
    return dict(mean=_mean(ds), ci=[lo, hi], resolved=(lo is not None and (lo > 0 or hi < 0)),
                wlt=[sum(1 for d in ds if d > 0), sum(1 for d in ds if d < 0), sum(1 for d in ds if d == 0)])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    run = json.loads(RUN.read_text())
    ref = json.loads(REF.read_text())
    rows = [r for r in run["per_query"] if "error" not in r]

    per_query = []
    for r in rows:
        rel, n_rel, n_reach = r["relevant_pages"], r["n_relevant"], r["n_reachable"]
        pages = r["CE_pages"]
        pool_gold = round(r["pool_cov"] * n_reach)
        rec: dict = dict(id=r["id"], query_type=r["query_type"], n_rel=n_rel, n_reach=n_reach,
                         pool_gold=pool_gold, avail=len(pages))
        for k in KS:
            R, P, N = metrics_at_k(pages, rel, k)
            cov = coverage_at_k(pages, rel, n_reach, k)
            rc, nc = ceilings(n_rel, n_reach, pool_gold, k)
            rec[f"R@{k}"] = R; rec[f"P@{k}"] = P; rec[f"nDCG@{k}"] = N; rec[f"cov@{k}"] = cov
            rec[f"Rceil@{k}"] = rc; rec[f"nDCGceil@{k}"] = nc
            rec[f"capR@{k}"] = (R / rc) if (R is not None and rc > 0) else None
            rec[f"capN@{k}"] = (N / nc) if nc > 0 else None
        for k in KS:
            if k == K_ANCHOR:
                continue
            rec[f"dR@{k}"] = (rec[f"R@{k}"] - rec[f"R@{K_ANCHOR}"]) if (rec[f"R@{k}"] is not None and rec[f"R@{K_ANCHOR}"] is not None) else None
            rec[f"dnDCG@{k}"] = rec[f"nDCG@{k}"] - rec[f"nDCG@{K_ANCHOR}"]
            rec[f"dcov@{k}"] = (rec[f"cov@{k}"] - rec[f"cov@{K_ANCHOR}"]) if (rec[f"cov@{k}"] is not None and rec[f"cov@{K_ANCHOR}"] is not None) else None
        per_query.append(rec)

    by_type = {}
    for t in TYPES:
        sel = [r for r in per_query if r["query_type"] == t]
        if not sel:
            continue
        cell = {"n": len(sel), "per_k": {}}
        for k in KS:
            cell["per_k"][k] = dict(
                R=_mean(r[f"R@{k}"] for r in sel if r[f"R@{k}"] is not None),
                nDCG=_mean(r[f"nDCG@{k}"] for r in sel),
                P=_mean(r[f"P@{k}"] for r in sel if r[f"P@{k}"] is not None),
                cov=_mean(r[f"cov@{k}"] for r in sel if r[f"cov@{k}"] is not None),
                Rceil=_mean(r[f"Rceil@{k}"] for r in sel),
                nDCGceil=_mean(r[f"nDCGceil@{k}"] for r in sel),
                capN=_mean(r[f"capN@{k}"] for r in sel if r[f"capN@{k}"] is not None),
                pg=_mean(r["pool_gold"] for r in sel),
                nrel_mean=_mean(r["n_rel"] for r in sel),
            )
            if k != K_ANCHOR:
                cell["per_k"][k]["dR"] = _delta(sel, f"dR@{k}")
                cell["per_k"][k]["dnDCG"] = _delta(sel, f"dnDCG@{k}")
                cell["per_k"][k]["dcov"] = _delta(sel, f"dcov@{k}")
        # comparability: k < n_rel (comparable) vs k >= n_rel (IDCG saturates -> construction)
        cell["comparable_k_lt_nrel"] = {}
        for k in KS:
            if k == K_ANCHOR:
                continue
            sub = [r for r in sel if k < r["n_rel"]]
            cell["comparable_k_lt_nrel"][k] = dict(n=len(sub), dnDCG=_delta(sub, f"dnDCG@{k}"))
        by_type[t] = cell

    res = {"meta": {"harness": "wide_ce_k_sweep.py", "read_only": True,
                    "inputs": {"wide_ce_endpoint.json": _sha256(RUN)},
                    "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
                    "ks": list(KS), "k_anchor": K_ANCHOR},
           "guards": {}, "results": {"CE": {"ks": list(KS), "by_type": by_type, "per_query": per_query}}}

    # guards
    rg = run["guards"]
    res["guards"]["G1_population"] = rg["G1_population"]
    res["guards"]["G1_types"] = rg["G1_types"]
    res["guards"]["G2_reachable_pages"] = rg["G2_reachable_pages"]
    res["guards"]["G3_errors"] = rg["G3_errors"]
    res["guards"]["G4_reranker_fallbacks"] = rg["G4_reranker_fallbacks"]
    res["guards"]["G5_ce_len_min_gt_20"] = rg["G5_ce_len_min"]
    res["guards"]["G6_pool_mean_gt_86"] = rg["G6_pool_mean"]
    res["guards"]["G7_k_exceeds_list"] = {str(k): [r["id"] for r in rows if len(r["CE_pages"]) < k]
                                          for k in KS if any(len(r["CE_pages"]) < k for r in rows)}
    # cross-run CE@20 overlap vs SSI105's CE arm (REPORTED, not asserted -- different runs)
    refb = ref["results"]["CE"]["by_type"]
    ov = {}
    for t in TYPES:
        got = res["results"]["CE"]["by_type"][t]["per_k"][K_ANCHOR]
        ov[t] = {"wide_ce_R20": got["R"], "ssi105_ce_R20": refb[t]["per_k"][str(K_ANCHOR)]["R"],
                 "wide_ce_nDCG20": got["nDCG"], "ssi105_ce_nDCG20": refb[t]["per_k"][str(K_ANCHOR)]["nDCG"]}
    res["guards"]["G8_ce20_vs_ssi105_reported"] = ov

    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))
    print(f"wrote {out}  ({out.stat().st_size} bytes)")
    print(f"G1 n={res['guards']['G1_population']} {res['guards']['G1_types']}  reachable={res['guards']['G2_reachable_pages']}  "
          f"fallbacks={res['guards']['G4_reranker_fallbacks']}  CE len min={res['guards']['G5_ce_len_min_gt_20']}  "
          f"pool mean={res['guards']['G6_pool_mean_gt_86']}")
    print(f"G7 k>list: {res['guards']['G7_k_exceeds_list']}")
    print()
    c = res["results"]["CE"]["by_type"]
    print("CE arm over the WIDE pool (k grid):")
    for metric in ("R", "nDCG", "cov", "capN"):
        print(f"  {metric:5s} {'type':9s} | " + " | ".join(f"{k:>5}" for k in KS))
        for t in TYPES:
            row = c[t]["per_k"]
            print(f"        {t:9s} | " + " | ".join(f"{row[k][metric]:5.3f}" if row[k].get(metric) is not None else "   - " for k in KS))
        print()
    print("n_rel mean by type:", {t: round(c[t]['per_k'][20]['nrel_mean'],1) for t in TYPES})
    print("comparable block (k < n_rel) dnDCG vs k=20:")
    for t in TYPES:
        blk = c[t]["comparable_k_lt_nrel"]
        for k in KS:
            if k == K_ANCHOR or k not in blk:
                continue
            d = blk[k]["dnDCG"]
            ci = "n/a" if d["ci"][0] is None else f"[{d['ci'][0]:+.4f},{d['ci'][1]:+.4f}]"
            print(f"   {t:9s} k={k:>3} n={blk[k]['n']:>3} dnDCG={d['mean']:+.4f} ci={ci} resolved={d['resolved']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
