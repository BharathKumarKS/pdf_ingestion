"""Independent verifier for wide_pool_k_sweep.json. STDLIB ONLY.

Reads the artifact + the two SOURCE artifacts and RE-DERIVES every recorded cell from the RAW per-query
page lists. Prints one line per check; exit 0 iff every check passes.

Usage:  python logs/p1/step10/wide_pool_k_sweep_verifier.py [--artifact PATH]
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
ART = HERE / "wide_pool_k_sweep.json"
FA = HERE / "fusion_attribution.json"
T0 = HERE / "t0_baseline.json"
REF = HERE / "per_type_k_sweep.json"

TYPES = ("factual", "overview", "multihop")
ARMS = {"POOL100": ("C_pages", "C_cov", (1, 2, 5, 10, 20, 30, 40, 50)),
        "POOL500": ("W500_pages", "W500_cov", (1, 2, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200, 250))}
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


def _pages(xs):
    return [x[0] if isinstance(x, (list, tuple)) else x for x in xs]


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
    if not n_reach:
        return None
    return len(set(pages[:k]) & set(rel)) / n_reach


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


def build_source(fa):
    out = {}
    for arm, (pk, ck, ks) in ARMS.items():
        out[arm] = [dict(id=r["id"], t=r["query_type"], rel=r["relevant_pages"], n_rel=r["n_relevant"],
                         n_reach=r["n_reachable"], pg=round(r[ck] * r["n_reachable"]),
                         pages=_pages(r[pk])) for r in fa["per_query"]]
    return out


def metrics_for(r, ks):
    out = {}
    for k in ks:
        R, P, N = _metrics(r["pages"], r["rel"], k)
        rc, nc = _ceil(r["n_rel"], r["n_reach"], r["pg"], k)
        out[k] = dict(R=R, P=P, nDCG=N, cov=_cov(r["pages"], r["rel"], r["n_reach"], k),
                      Rceil=rc, nDCGceil=nc, capN=(N / nc) if nc > 0 else None,
                      capR=(R / rc) if (R is not None and rc > 0) else None)
    for k in ks:
        if k == K_ANCHOR:
            continue
        a = out[K_ANCHOR]
        out[k]["dR"] = (out[k]["R"] - a["R"]) if (out[k]["R"] is not None and a["R"] is not None) else None
        out[k]["dnDCG"] = out[k]["nDCG"] - a["nDCG"]
        out[k]["dcov"] = (out[k]["cov"] - a["cov"]) if (out[k]["cov"] is not None and a["cov"] is not None) else None
    return out


def verify(art, fa, t0, ref):
    src = build_source(fa)

    check("V1_population", art["guards"]["G1_population"] == 133 and len(fa["per_query"]) == 133)
    check("V1_types", art["guards"]["G1_types"] == {t: sum(1 for r in fa["per_query"] if r["query_type"] == t) for t in TYPES})

    ab = [a["id"] for a, b in zip(fa["per_query"], t0["per_query"]) if _pages(a["C_pages"])[:20] != _pages(b["fusion_ranked"])[:20]]
    sb = [a["id"] for a in fa["per_query"] if not set(_pages(a["C_pages"])) <= set(_pages(a["W500_pages"]))]
    check("V2_cross_artifact_anchor", ab == art["guards"]["G2_cross_artifact_anchor_bad"] == [])
    check("V2_set_superset", sb == art["guards"]["G3_set_superset_bad"] == [])

    for arm, (pk, ck, ks) in ARMS.items():
        by_id = {r["id"]: r for r in art["results"][arm]["per_query"]}
        bad = []
        for r in src[arm]:
            m = metrics_for(r, ks)
            rec = by_id[r["id"]]
            for k in ks:
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
        check(f"V3_per_query_{arm}", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))
    # NOTE: no monotonicity check here. R@k is a truncation identity on BOTH arms (no anchor override,
    # unlike SSI105's CE arm), so such a check could never fail -- an inert check is worse than none.
    # The harness reports it as G4 instead.

    for arm, (pk, ck, ks) in ARMS.items():
        mets = {r["id"]: metrics_for(r, ks) for r in src[arm]}
        bad = []
        for t in TYPES:
            sel = [r for r in src[arm] if r["t"] == t]
            if not sel:
                continue
            cell = art["results"][arm]["by_type"][t]["per_k"]
            for k in ks:
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
        check(f"V4_aggregates_{arm}", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    # V9 SSI105 reproduction (POOL100 vs per_type_k_sweep POOL arm)
    refb = ref["results"]["POOL"]["by_type"]
    bad = []
    for t in TYPES:
        for k in (20, 30, 40, 50):
            for key in ("R", "nDCG"):
                if abs(art["results"]["POOL100"]["by_type"][t]["per_k"][str(k)][key] - refb[t]["per_k"][str(k)][key]) > 5e-5:
                    bad.append((t, k, key))
    check("V9_ssi105_reproduction", bad == art["guards"]["G6_ssi105_reproduction_bad"] == [])

    check("V10_input_sha_fa", art["meta"]["inputs"]["fusion_attribution.json"] == hashlib.sha256(FA.read_bytes()).hexdigest())
    check("V10_input_sha_t0", art["meta"]["inputs"]["t0_baseline.json"] == hashlib.sha256(T0.read_bytes()).hexdigest())
    return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    art = json.loads(Path(args.artifact).read_text())
    verify(art, json.loads(FA.read_text()), json.loads(T0.read_text()), json.loads(REF.read_text()))
    n_pass = sum(1 for r in RESULTS if r["passed"])
    if not args.quiet:
        for r in RESULTS:
            print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['id']:32s} {r['detail']}")
        print(f"\n{n_pass}/{len(RESULTS)} checks PASS")
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
