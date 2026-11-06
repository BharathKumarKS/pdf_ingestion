"""WIDE-POOL k SWEEP: does a wider pool + higher k change the per-type picture?

READ-ONLY. Reads ONE existing artifact and writes one JSON. No cluster, no LLM, no collection write.

    logs/p1/step10/fusion_attribution.json  -- POOL100 = C_pages (pool order, cap 100)
                                            -- POOL500 = W500_pages (pool order, cap 500)

The question (pre-registration .hermes/plans/2026-11-01-p1-wide-pool-k-sweep-preregistration.md):

    Does the per-type k sweep change on a WIDER pool, and does SSI105's capture artifact (a shrinking
    ceiling) survive a wider pool?  The CE arm at k>50 is NOT here -- it needs a run.

Usage:  python logs/p1/step10/wide_pool_k_sweep.py [--out PATH]
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
FA = HERE / "fusion_attribution.json"
T0 = HERE / "t0_baseline.json"
REF = HERE / "per_type_k_sweep.json"      # SSI105, for the G6 reproduction guard
DEFAULT_OUT = HERE / "wide_pool_k_sweep.json"

TYPES = ("factual", "overview", "multihop")
ARMS = {"POOL100": ("C_pages", "C_cov", (1, 2, 5, 10, 20, 30, 40, 50)),
        "POOL500": ("W500_pages", "W500_cov", (1, 2, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200, 250))}
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


def _pages(xs):
    return [x[0] if isinstance(x, (list, tuple)) else x for x in xs]


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
    if not n_reach:
        return None
    return len(set(pages[:k]) & set(rel)) / n_reach


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


def build_arm(rows, ks):
    per_query = []
    for r in rows:
        rel, n_rel, n_reach, pool_gold, pages = r["rel"], r["n_rel"], r["n_reach"], r["pool_gold"], r["pages"]
        rec: dict = dict(id=r["id"], query_type=r["t"], n_rel=n_rel, n_reach=n_reach,
                         pool_gold=pool_gold, avail=len(pages))
        for k in ks:
            R, P, N = metrics_at_k(pages, rel, k)
            cov = coverage_at_k(pages, rel, n_reach, k)
            rc, nc = ceilings(n_rel, n_reach, pool_gold, k)
            rec[f"R@{k}"] = R; rec[f"P@{k}"] = P; rec[f"nDCG@{k}"] = N; rec[f"cov@{k}"] = cov
            rec[f"Rceil@{k}"] = rc; rec[f"nDCGceil@{k}"] = nc
            rec[f"capR@{k}"] = (R / rc) if (R is not None and rc > 0) else None
            rec[f"capN@{k}"] = (N / nc) if nc > 0 else None
        for k in ks:
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
        for k in ks:
            cell["per_k"][k] = dict(
                R=_mean(r[f"R@{k}"] for r in sel if r[f"R@{k}"] is not None),
                nDCG=_mean(r[f"nDCG@{k}"] for r in sel),
                P=_mean(r[f"P@{k}"] for r in sel if r[f"P@{k}"] is not None),
                cov=_mean(r[f"cov@{k}"] for r in sel if r[f"cov@{k}"] is not None),
                Rceil=_mean(r[f"Rceil@{k}"] for r in sel),
                nDCGceil=_mean(r[f"nDCGceil@{k}"] for r in sel),
                capN=_mean(r[f"capN@{k}"] for r in sel if r[f"capN@{k}"] is not None),
                pg=_mean(r["pool_gold"] for r in sel),
            )
            if k != K_ANCHOR:
                cell["per_k"][k]["dR"] = _delta(sel, f"dR@{k}")
                cell["per_k"][k]["dnDCG"] = _delta(sel, f"dnDCG@{k}")
                cell["per_k"][k]["dcov"] = _delta(sel, f"dcov@{k}")
        cell["comparability"] = {}
        for label, pred in (("n_rel_le_20_same_denominator", lambda n: n <= K_ANCHOR),
                            ("n_rel_gt_20_comparable", lambda n: n > K_ANCHOR)):
            sub = [r for r in sel if pred(r["n_rel"])]
            cell["comparability"][label] = {"n": len(sub),
                                            "per_k": {k: _delta(sub, f"dnDCG@{k}") for k in ks if k != K_ANCHOR}}
        by_type[t] = cell
    return {"ks": list(ks), "by_type": by_type, "per_query": per_query}


def guards(fa, t0):
    rows, r0 = fa["per_query"], t0["per_query"]
    anchor_bad = [a["id"] for a, b in zip(rows, r0) if _pages(a["C_pages"])[:20] != _pages(b["fusion_ranked"])[:20]]
    super_bad = [a["id"] for a in rows if not set(_pages(a["C_pages"])) <= set(_pages(a["W500_pages"]))]
    g5 = {arm: {str(k): [r["id"] for r in rows if len(_pages(r[f"{ARMS[arm][0]}"])) < k]
                for k in ARMS[arm][2]} for arm in ARMS}
    return {
        "G1_population": len(rows),
        "G1_types": {t: sum(1 for r in rows if r["query_type"] == t) for t in TYPES},
        "G2_cross_artifact_anchor_bad": anchor_bad,
        "G3_set_superset_bad": super_bad,
        "G5_k_exceeds_list": {a: {k: v for k, v in d.items() if v} for a, d in g5.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    fa = json.loads(FA.read_text())
    t0 = json.loads(T0.read_text())
    rows = fa["per_query"]

    src = {}
    for arm, (pk, ck, ks) in ARMS.items():
        src[arm] = [dict(id=r["id"], t=r["query_type"], rel=r["relevant_pages"], n_rel=r["n_relevant"],
                         n_reach=r["n_reachable"], pool_gold=round(r[ck] * r["n_reachable"]),
                         pages=_pages(r[pk])) for r in rows]

    res = {"meta": {"harness": "wide_pool_k_sweep.py", "read_only": True,
                    "inputs": {"fusion_attribution.json": _sha256(FA), "t0_baseline.json": _sha256(T0)},
                    "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
                    "arms": {a: list(ARMS[a][2]) for a in ARMS}, "k_anchor": K_ANCHOR},
           "guards": guards(fa, t0), "results": {}}

    for arm in ARMS:
        res["results"][arm] = build_arm(src[arm], ARMS[arm][2])

    # G4 monotone R, per arm
    def _mono(recs, ks):
        bad = []
        for r in recs:
            v = [r[f"R@{k}"] for k in ks if r.get(f"R@{k}") is not None]
            if any(v[i + 1] < v[i] - 1e-12 for i in range(len(v) - 1)):
                bad.append(r["id"])
        return bad
    res["guards"]["G4_monotone_R_bad"] = {a: _mono(res["results"][a]["per_query"], ARMS[a][2]) for a in ARMS}

    # G6 reproduce SSI105's POOL arm on the shared k grid
    ref = json.loads(REF.read_text())["results"]["POOL"]["by_type"]
    g6 = []
    for t in TYPES:
        for k in (20, 30, 40, 50):
            for key in ("R", "nDCG"):
                got = res["results"]["POOL100"]["by_type"][t]["per_k"][k][key]
                exp = ref[t]["per_k"][str(k)][key]
                if abs(got - exp) > TOL:
                    g6.append((t, k, key, got, exp))
    res["guards"]["G6_ssi105_reproduction_bad"] = g6

    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))
    g = res["guards"]
    print(f"wrote {out}  ({out.stat().st_size} bytes)")
    print(f"G1 n={g['G1_population']} types={g['G1_types']}  G2 anchor-bad={len(g['G2_cross_artifact_anchor_bad'])}  "
          f"G3 superset-bad={len(g['G3_set_superset_bad'])}  G6 ssi105-bad={len(g['G6_ssi105_reproduction_bad'])}")
    print(f"G4 mono-bad: " + str({a: len(g['G4_monotone_R_bad'][a]) for a in ARMS}))
    print(f"G5 k>list: {g['G5_k_exceeds_list']}")
    print()
    for arm in ARMS:
        ks = res["results"][arm]["ks"]
        print(f"=== arm {arm}  (k={ks}) ===")
        for metric in ("R", "nDCG", "cov", "capN"):
            print(f"  {metric:5s}: {'type':9s} | " + " | ".join(f"{k:>5}" for k in ks))
            for t in TYPES:
                row = res["results"][arm]["by_type"][t]["per_k"]
                print(f"           {t:9s} | " + " | ".join(f"{row[k][metric]:5.3f}" if row[k].get(metric) is not None else "   - " for k in ks))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
