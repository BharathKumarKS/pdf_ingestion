"""Independent verifier for wide_ce_k_sweep.json. STDLIB ONLY.

Re-derives every recorded cell from the RAW per-query CE page lists in wide_ce_endpoint.json.
Exit 0 iff every check passes.

Usage:  python logs/p1/step10/wide_ce_k_sweep_verifier.py [--artifact PATH]
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
ART = HERE / "wide_ce_k_sweep.json"
RUN = HERE / "wide_ce_endpoint.json"

TYPES = ("factual", "overview", "multihop")
KS = (1, 2, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200, 250)
K_ANCHOR = 20
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261031
TOL = 5e-9
RESULTS: list = []


def check(cid, passed, detail=""):
    RESULTS.append({"id": cid, "passed": bool(passed), "detail": detail})
    return passed


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _idcg(n, k):
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


def _metrics(pages, rel, k):
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


def _cov(pages, rel, n_reach, k):
    return (len(set(pages[:k]) & set(rel)) / n_reach) if n_reach else None


def _ceil(n_rel, n_reach, pg, k):
    pg = min(int(round(pg)), n_reach)
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


def build_source(run):
    rows = [r for r in run["per_query"] if "error" not in r]
    return [dict(id=r["id"], t=r["query_type"], rel=r["relevant_pages"], n_rel=r["n_relevant"],
                 n_reach=r["n_reachable"], pg=round(r["pool_cov"] * r["n_reachable"]),
                 pages=r["CE_pages"]) for r in rows]


def metrics_for(r):
    out = {}
    for k in KS:
        R, P, N = _metrics(r["pages"], r["rel"], k)
        rc, nc = _ceil(r["n_rel"], r["n_reach"], r["pg"], k)
        out[k] = dict(R=R, P=P, nDCG=N, cov=_cov(r["pages"], r["rel"], r["n_reach"], k),
                      Rceil=rc, nDCGceil=nc, capN=(N / nc) if nc > 0 else None,
                      capR=(R / rc) if (R is not None and rc > 0) else None)
    for k in KS:
        if k == K_ANCHOR:
            continue
        a = out[K_ANCHOR]
        out[k]["dR"] = (out[k]["R"] - a["R"]) if (out[k]["R"] is not None and a["R"] is not None) else None
        out[k]["dnDCG"] = out[k]["nDCG"] - a["nDCG"]
        out[k]["dcov"] = (out[k]["cov"] - a["cov"]) if (out[k]["cov"] is not None and a["cov"] is not None) else None
    return out


def verify(art, run):
    src = build_source(run)
    g = art["guards"]

    check("V1_population", g["G1_population"] == 133 and len(src) == 133)
    check("V1_types", g["G1_types"] == {t: sum(1 for r in src if r["t"] == t) for t in TYPES})
    check("V2_reachable_888", g["G2_reachable_pages"] == run["guards"]["G2_reachable_pages"] == 888)
    check("V2_no_errors", g["G3_errors"] == run["guards"]["G3_errors"] == [])
    check("V2_no_fallbacks", g["G4_reranker_fallbacks"] == run["guards"]["G4_reranker_fallbacks"] == 0)
    check("V2_cap_widened", g["G5_ce_len_min_gt_20"] == min(len(r["pages"]) for r in src) and g["G5_ce_len_min_gt_20"] > 20)
    check("V2_pool_widened", g["G6_pool_mean_gt_86"] == run["guards"]["G6_pool_mean"] and g["G6_pool_mean_gt_86"] > 86.47)

    by_id = {r["id"]: r for r in art["results"]["CE"]["per_query"]}
    bad = []
    for r in src:
        m = metrics_for(r)
        rec = by_id[r["id"]]
        for k in KS:
            for key, ak in (("R", f"R@{k}"), ("nDCG", f"nDCG@{k}"), ("cov", f"cov@{k}"),
                            ("Rceil", f"Rceil@{k}"), ("nDCGceil", f"nDCGceil@{k}"),
                            ("capR", f"capR@{k}"), ("capN", f"capN@{k}")):
                got, exp = rec.get(ak), m[k][key]
                if (got is None) != (exp is None) or (got is not None and abs(got - exp) > TOL):
                    bad.append((r["id"], ak, got, exp))
            if k != K_ANCHOR:
                for key, ak in (("dR", f"dR@{k}"), ("dnDCG", f"dnDCG@{k}"), ("dcov", f"dcov@{k}")):
                    got, exp = rec.get(ak), m[k][key]
                    if (got is None) != (exp is None) or (got is not None and abs(got - exp) > TOL):
                        bad.append((r["id"], ak, got, exp))
    check("V3_per_query_CE", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    mets = {r["id"]: metrics_for(r) for r in src}
    bad = []
    for t in TYPES:
        sel = [r for r in src if r["t"] == t]
        if not sel:
            continue
        cell = art["results"]["CE"]["by_type"][t]["per_k"]
        for k in KS:
            for key, ak in (("R", "R"), ("nDCG", "nDCG"), ("P", "P"), ("cov", "cov"),
                            ("Rceil", "Rceil"), ("nDCGceil", "nDCGceil"), ("capN", "capN")):
                vals = [mets[r["id"]][k][key] for r in sel if mets[r["id"]][k][key] is not None]
                if abs(cell[str(k)][ak] - _mean(vals)) > TOL:
                    bad.append((t, k, ak))
            if k != K_ANCHOR:
                for key in ("dR", "dnDCG", "dcov"):
                    ds = [mets[r["id"]][k][key] for r in sel if mets[r["id"]][k][key] is not None]
                    lo, hi = _ci(ds)
                    got = cell[str(k)][key]
                    ok = (abs(got["mean"] - _mean(ds)) <= TOL
                          and (got["ci"][0] is None) == (lo is None)
                          and (lo is None or (abs(got["ci"][0] - lo) <= TOL and abs(got["ci"][1] - hi) <= TOL))
                          and got["resolved"] == (lo is not None and (lo > 0 or hi < 0)))
                    if not ok:
                        bad.append((t, k, key))
    check("V4_aggregates_CE", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    # V8 comparability block (k < n_rel)
    bad = []
    for t in TYPES:
        sel = [r for r in src if r["t"] == t]
        blk = art["results"]["CE"]["by_type"][t]["comparable_k_lt_nrel"]
        for k in KS:
            if k == K_ANCHOR:
                continue
            sub = [r for r in sel if k < r["n_rel"]]
            ds = [mets[r["id"]][k]["dnDCG"] for r in sub]
            lo, hi = _ci(ds)
            got = blk[str(k)]
            ok = (got["n"] == len(sub) and abs(got["dnDCG"]["mean"] - _mean(ds)) <= TOL
                  and (got["dnDCG"]["ci"][0] is None) == (lo is None)
                  and (lo is None or (abs(got["dnDCG"]["ci"][0] - lo) <= TOL and abs(got["dnDCG"]["ci"][1] - hi) <= TOL)))
            if not ok:
                bad.append((t, k))
    check("V8_comparability", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    check("V10_input_sha", art["meta"]["inputs"]["wide_ce_endpoint.json"] == hashlib.sha256(RUN.read_bytes()).hexdigest())
    return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    art = json.loads(Path(args.artifact).read_text())
    verify(art, json.loads(RUN.read_text()))
    n_pass = sum(1 for r in RESULTS if r["passed"])
    if not args.quiet:
        for r in RESULTS:
            print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['id']:28s} {r['detail']}")
        print(f"\n{n_pass}/{len(RESULTS)} checks PASS")
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
