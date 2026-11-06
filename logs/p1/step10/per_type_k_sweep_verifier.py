"""Independent verifier for per_type_k_sweep.json.

STDLIB ONLY. Reads the artifact and the two SOURCE artifacts, and RE-DERIVES every recorded cell from
the RAW per-query page lists -- never from the harness's own output. Prints one line per check.

Usage:  python logs/p1/step10/per_type_k_sweep_verifier.py [--artifact PATH]
Exit 0 iff every check passes.
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
ART = HERE / "per_type_k_sweep.json"
T4 = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"

TYPES = ("factual", "overview", "multihop")
CE_KS = (1, 2, 5, 10, 20, 30, 40, 47)
POOL_KS = (1, 2, 5, 10, 20, 30, 40, 50)
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


def _ceil(n_rel, n_reach, pool_gold, k):
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


def build_source(t4, t0):
    """Rebuild the per-query records INDEPENDENTLY from the raw sources."""
    ce, pool = [], []
    for a, b in zip(t4["per_query"], t0["per_query"]):
        assert a["id"] == b["id"]
        nr = a["n_reachable"]
        ce.append(dict(id=a["id"], t=a["query_type"], rel=a["relevant_pages"], n_rel=a["n_relevant"],
                       n_reach=nr, pg=round(a["C_pool_cov"] * nr), pages=_pages(a["W50_pages"]),
                       anchor=a["C_pages"]))
        pool.append(dict(id=b["id"], t=b["query_type"], rel=b["relevant_pages"], n_rel=b["n_relevant"],
                         n_reach=nr, pg=round(b["cov_fusion"] * nr), pages=_pages(b["fusion_ranked"]),
                         anchor=None))
    return ce, pool


def metrics_for(r, ks):
    out = {}
    for k in ks:
        use = r["anchor"] if (k == K_ANCHOR and r["anchor"] is not None) else r["pages"]
        R, P, N = _metrics(use, r["rel"], k)
        cov = _cov(use, r["rel"], r["n_reach"], k)
        rc, nc = _ceil(r["n_rel"], r["n_reach"], r["pg"], k)
        out[k] = dict(R=R, P=P, nDCG=N, cov=cov, Rceil=rc, nDCGceil=nc,
                      capR=(R / rc) if (R is not None and rc > 0) else None,
                      capN=(N / nc) if nc > 0 else None)
    for k in ks:
        if k == K_ANCHOR:
            continue
        a = out[K_ANCHOR]
        out[k]["dR"] = (out[k]["R"] - a["R"]) if (out[k]["R"] is not None and a["R"] is not None) else None
        out[k]["dnDCG"] = out[k]["nDCG"] - a["nDCG"]
        out[k]["dcov"] = (out[k]["cov"] - a["cov"]) if (out[k]["cov"] is not None and a["cov"] is not None) else None
    return out


def verify(art, t4, t0):
    ce, pool = build_source(t4, t0)
    src = {"CE": (ce, CE_KS), "POOL": (pool, POOL_KS)}

    # ---- V1 population ----
    check("V1_population", art["guards"]["G1_population"] == 133 and len(t4["per_query"]) == 133,
          f"n={art['guards']['G1_population']}")
    check("V1_ids_align", art["guards"]["G1_ids_align"] is True)
    check("V1_types", art["guards"]["G1_types"] == {t: sum(1 for r in t4["per_query"] if r["query_type"] == t) for t in TYPES})

    # ---- V2 guards re-derived ----
    prefix_bad = [a["id"] for a in t4["per_query"] if _pages(a["W50_pages"])[:len(a["C_pages"])] != a["C_pages"]]
    sha_bad = [a["id"] for a in t4["per_query"] if a["C_pool_sha"] != a["W50_pool_sha"]]
    anchor_bad = [a["id"] for a, b in zip(t0["per_query"], t4["per_query"]) if _pages(a["fusion_ranked"])[:20] != b["N_pages"]]
    check("V2_prefix_identity", prefix_bad == art["guards"]["G2_prefix_identity_bad"] == [])
    check("V2_pool_sha", sha_bad == art["guards"]["G2b_pool_sha_bad"] == [])
    check("V2_cross_artifact_anchor", anchor_bad == art["guards"]["G3_cross_artifact_anchor_bad"] == [])

    # ---- V3/V6/V7 per-query re-derivation ----
    mono_all = []
    for arm, (rows, ks) in src.items():
        by_id = {r["id"]: r for r in art["results"][arm]["per_query"]}
        bad = []
        for r in rows:
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
            vals = [m[k]["R"] for k in ks if m[k]["R"] is not None]
            if any(vals[i + 1] < vals[i] - 1e-12 for i in range(len(vals) - 1)):
                mono_all.append(f"{arm}:{r['id']}")
        check(f"V3_per_query_{arm}", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))
    # V7 is ONE check: R@k is a truncation identity for POOL, but the CE arm's anchor override at k=20
    # (arm C's own list) CAN break the superset relation -- so the check as a whole is reddenable.
    check("V7_monotone_R", not mono_all, f"{len(mono_all)} non-monotone" + (f" e.g. {mono_all[:2]}" if mono_all else ""))

    # ---- V4 aggregates ----
    for arm, (rows, ks) in src.items():
        mets = {r["id"]: metrics_for(r, ks) for r in rows}
        bad = []
        for t in TYPES:
            sel = [r for r in rows if r["t"] == t]
            if not sel:
                continue
            cell = art["results"][arm]["by_type"][t]["per_k"]
            for k in ks:
                for key, ak in (("R", "R"), ("nDCG", "nDCG"), ("P", "P"), ("cov", "cov"),
                                ("Rceil", "Rceil"), ("nDCGceil", "nDCGceil"), ("capR", "capR"), ("capN", "capN")):
                    vals = [mets[r["id"]][k][key] for r in sel if mets[r["id"]][k][key] is not None]
                    exp = _mean(vals)
                    got = cell[str(k)][ak]
                    if abs(got - exp) > TOL:
                        bad.append((t, k, ak, got, exp))
        check(f"V4_aggregates_{arm}", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    # ---- V5 deltas + CI (same seed/order) ----
    for arm, (rows, ks) in src.items():
        mets = {r["id"]: metrics_for(r, ks) for r in rows}
        bad = []
        for t in TYPES:
            sel = [r for r in rows if r["t"] == t]
            if not sel:
                continue
            cell = art["results"][arm]["by_type"][t]["per_k"]
            for k in ks:
                if k == K_ANCHOR:
                    continue
                for key in ("dR", "dnDCG", "dcov"):
                    ds = [mets[r["id"]][k][key] for r in sel if mets[r["id"]][k][key] is not None]
                    lo, hi = _ci(ds)
                    got = cell[str(k)][key]
                    ok = (abs(got["mean"] - _mean(ds)) <= TOL
                          and (got["ci"][0] is None) == (lo is None)
                          and (lo is None or abs(got["ci"][0] - lo) <= TOL and abs(got["ci"][1] - hi) <= TOL)
                          and got["resolved"] == (lo is not None and (lo > 0 or hi < 0)))
                    if not ok:
                        bad.append((t, k, key, got["mean"], _mean(ds)))
        check(f"V5_deltas_ci_{arm}", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    # ---- V8 comparability split ----
    rows, ks = src["CE"]
    mets = {r["id"]: metrics_for(r, ks) for r in rows}
    bad = []
    for t in TYPES:
        sel = [r for r in rows if r["t"] == t]
        comp = art["results"]["CE"]["by_type"][t]["comparability"]
        for label, pred in (("n_rel_le_20_same_denominator", lambda n: n <= 20), ("n_rel_gt_20_comparable", lambda n: n > 20)):
            sub = [r for r in sel if pred(r["n_rel"])]
            if comp[label]["n"] != len(sub):
                bad.append((t, label, "n", comp[label]["n"], len(sub)))
            for k in ks:
                if k == K_ANCHOR:
                    continue
                ds = [mets[r["id"]][k]["dnDCG"] for r in sub]
                if abs(comp[label]["per_k"][str(k)]["mean"] - _mean(ds)) > TOL:
                    bad.append((t, label, k, comp[label]["per_k"][str(k)]["mean"], _mean(ds)))
    check("V8_comparability", not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:2]}" if bad else ""))

    # ---- V9 G5 anchor to t4.C_metrics ----
    by_id = {r["id"]: r for r in art["results"]["CE"]["per_query"]}
    bad = [a["id"] for a in t4["per_query"]
           if abs(by_id[a["id"]]["R@20"] - a["C_metrics"]["recall_at_20"]) > 5e-5
           or abs(by_id[a["id"]]["nDCG@20"] - a["C_metrics"]["ndcg_at_20"]) > 5e-5]
    check("V9_anchor_to_C_metrics", bad == art["guards"]["G5_anchor_bad"] == [],
          f"{len(bad)} bad")

    # ---- V10 input shas ----
    check("V10_input_sha_t4", art["meta"]["inputs"]["t4_endpoint.json"] == hashlib.sha256(T4.read_bytes()).hexdigest())
    check("V10_input_sha_t0", art["meta"]["inputs"]["t0_baseline.json"] == hashlib.sha256(T0.read_bytes()).hexdigest())
    return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    art = json.loads(Path(args.artifact).read_text())
    t4 = json.loads(T4.read_text())
    t0 = json.loads(T0.read_text())
    verify(art, t4, t0)
    n_pass = sum(1 for r in RESULTS if r["passed"])
    if not args.quiet:
        for r in RESULTS:
            print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['id']:32s} {r['detail']}")
        print(f"\n{n_pass}/{len(RESULTS)} checks PASS")
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
