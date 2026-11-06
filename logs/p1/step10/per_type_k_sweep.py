"""PER-TYPE k SWEEP at the endpoint: does a wider cut improve the metric, per query type?

READ-ONLY. Reads TWO existing artifacts and writes one JSON. No cluster, no LLM, no collection write.

    logs/p1/step10/t4_endpoint.json   -- arm CE  = W50_pages (the cross-encoder's ranked pages, k<=50)
    logs/p1/step10/t0_baseline.json   -- arm POOL= fusion_ranked (the fused pool's own order, k<=100)

The question (pre-registration .hermes/plans/2026-11-01-p1-per-type-k-sweep-preregistration.md):

    Does widening the endpoint cut improve R@k / nDCG@k / coverage, PER QUERY TYPE, against the
    per-type pool-aware ceiling?  SSI97 P3 / SSI102 measured the cut on the whole population only.

Usage:  python logs/p1/step10/per_type_k_sweep.py [--out PATH]
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
T4 = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"
DEFAULT_OUT = HERE / "per_type_k_sweep.json"

TYPES = ("factual", "overview", "multihop")
CE_KS = (1, 2, 5, 10, 20, 30, 40, 47)
POOL_KS = (1, 2, 5, 10, 20, 30, 40, 50)
K_ANCHOR = 20
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261031
TOL = 5e-5


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _idcg(n: int, k: int) -> float:
    """Ideal DCG, binary gains, page-deduped -- identical to evaluate_rag.py:406-407."""
    return sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))


def _pages(xs) -> list:
    """Normalise a ranked list to page numbers. t4 stores ints; t0 stores [page, score] pairs."""
    out = []
    for x in xs:
        out.append(x[0] if isinstance(x, (list, tuple)) else x)
    return out


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


def coverage_at_k(pages, relevant, n_reach, k):
    if not n_reach:
        return None
    hit = len(set(pages[:k]) & set(relevant))
    return hit / n_reach


def ceilings(n_rel, n_reach, pool_gold, k):
    pool_gold = min(int(round(pool_gold)), n_reach)
    idcg_r = _idcg(n_rel, k)
    return dict(
        R_ceil_pool=min(k, pool_gold) / n_rel if n_rel else 0.0,
        nDCG_ceil_pool=(_idcg(pool_gold, k) / idcg_r) if idcg_r > 0 else 0.0,
    )


def _boot_ci(deltas):
    """Paired percentile bootstrap CI of the mean. Seeds FRESH per call (the seed IS the identity),
    so any block re-derives independently of the order the blocks were computed in."""
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


def _agg_delta(recs, key):
    ds = [r[key] for r in recs if r.get(key) is not None]
    lo, hi = _boot_ci(ds)
    return dict(
        mean=_mean(ds), ci=[lo, hi],
        resolved=(lo is not None and (lo > 0 or hi < 0)),
        wlt=[sum(1 for d in ds if d > 0), sum(1 for d in ds if d < 0), sum(1 for d in ds if d == 0)],
    )


def build_arm(rows, arm):
    """rows: list of dicts with id, query_type, relevant_pages, n_relevant, n_reachable, pages, pool_gold."""
    ks = CE_KS if arm == "CE" else POOL_KS
    per_query = []
    for r in rows:
        rel, n_rel, n_reach, pool_gold = r["relevant_pages"], r["n_relevant"], r["n_reachable"], r["pool_gold"]
        pages = r["pages"]
        anchor_pages = r.get("anchor_pages")  # arm C's own list; exact at k=K_ANCHOR (§I97 §15)
        rec: dict = dict(id=r["id"], query_type=r["query_type"], n_rel=n_rel, n_reach=n_reach,
                         pool_gold=pool_gold, avail=len(pages))
        for k in ks:
            use = anchor_pages if (k == K_ANCHOR and anchor_pages is not None) else pages
            R, P, N = metrics_at_k(use, rel, k)
            cov = coverage_at_k(use, rel, n_reach, k)
            ce = ceilings(n_rel, n_reach, pool_gold, k)
            rec[f"R@{k}"] = R
            rec[f"P@{k}"] = P
            rec[f"nDCG@{k}"] = N
            rec[f"cov@{k}"] = cov
            rec[f"Rceil@{k}"] = ce["R_ceil_pool"]
            rec[f"nDCGceil@{k}"] = ce["nDCG_ceil_pool"]
            rec[f"capR@{k}"] = (R / ce["R_ceil_pool"]) if (R is not None and ce["R_ceil_pool"] > 0) else None
            rec[f"capN@{k}"] = (N / ce["nDCG_ceil_pool"]) if ce["nDCG_ceil_pool"] > 0 else None
        # Deltas vs the anchor, computed AFTER every k exists (k < anchor is computed first).
        for k in ks:
            if k == K_ANCHOR:
                continue
            rec[f"dR@{k}"] = (rec[f"R@{k}"] - rec[f"R@{K_ANCHOR}"]) if (rec[f"R@{k}"] is not None and rec[f"R@{K_ANCHOR}"] is not None) else None
            rec[f"dnDCG@{k}"] = rec[f"nDCG@{k}"] - rec[f"nDCG@{K_ANCHOR}"]
            rec[f"dcov@{k}"] = (rec[f"cov@{k}"] - rec[f"cov@{K_ANCHOR}"]) if (rec[f"cov@{k}"] is not None and rec[f"cov@{K_ANCHOR}"] is not None) else None
        per_query.append(rec)

    by_type, overall = {}, {}
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
                capR=_mean(r[f"capR@{k}"] for r in sel if r[f"capR@{k}"] is not None),
                capN=_mean(r[f"capN@{k}"] for r in sel if r[f"capN@{k}"] is not None),
            )
            if k != K_ANCHOR:
                cell["per_k"][k]["dR"] = _agg_delta(sel, f"dR@{k}")
                cell["per_k"][k]["dnDCG"] = _agg_delta(sel, f"dnDCG@{k}")
                cell["per_k"][k]["dcov"] = _agg_delta(sel, f"dcov@{k}")
        cell["comparability"] = _comparability(sel, ks)
        by_type[t] = cell

    cell = {"n": len(per_query), "per_k": {}}
    for k in ks:
        cell["per_k"][k] = dict(
            R=_mean(r[f"R@{k}"] for r in per_query if r[f"R@{k}"] is not None),
            nDCG=_mean(r[f"nDCG@{k}"] for r in per_query),
            cov=_mean(r[f"cov@{k}"] for r in per_query if r[f"cov@{k}"] is not None),
            capN=_mean(r[f"capN@{k}"] for r in per_query if r[f"capN@{k}"] is not None),
        )
        if k != K_ANCHOR:
            cell["per_k"][k]["dR"] = _agg_delta(per_query, f"dR@{k}")
            cell["per_k"][k]["dnDCG"] = _agg_delta(per_query, f"dnDCG@{k}")
            cell["per_k"][k]["dcov"] = _agg_delta(per_query, f"dcov@{k}")
    overall = cell
    return {"ks": list(ks), "by_type": by_type, "overall": overall, "per_query": per_query}


def _comparability(sel, ks):
    """SSI102's trap: where n_rel <= K_ANCHOR the IDCG denominator is the SAME at every k>20, so the
    nDCG delta is non-negative BY CONSTRUCTION. Only the n_rel > 20 block is a finding."""
    blocks = {}
    for label, pred in (("n_rel_le_20_same_denominator", lambda n: n <= K_ANCHOR),
                        ("n_rel_gt_20_comparable", lambda n: n > K_ANCHOR)):
        sub = [r for r in sel if pred(r["n_rel"])]
        blocks[label] = {"n": len(sub), "per_k": {}}
        for k in ks:
            if k == K_ANCHOR:
                continue
            blocks[label]["per_k"][k] = _agg_delta(sub, f"dnDCG@{k}")
    return blocks


def guards(t4, t0):
    r4, r0 = t4["per_query"], t0["per_query"]
    prefix_bad = [r["id"] for r in r4 if _pages(r["W50_pages"])[:len(r["C_pages"])] != r["C_pages"]]
    sha_bad = [r["id"] for r in r4 if r["C_pool_sha"] != r["W50_pool_sha"]]
    anchor_bad = [a["id"] for a, b in zip(r0, r4) if _pages(a["fusion_ranked"])[:20] != b["N_pages"]]
    # G6: which k exceed a query's available list
    g6 = {"CE": {str(k): [r["id"] for r in r4 if len(_pages(r["W50_pages"])) < k] for k in CE_KS},
          "POOL": {str(k): [r["id"] for r in r0 if len(_pages(r["fusion_ranked"])) < k] for k in POOL_KS}}
    return {
        "G1_population": len(r4),
        "G1_types": {t: sum(1 for r in r4 if r["query_type"] == t) for t in TYPES},
        "G1_ids_align": [r["id"] for r in r4] == [r["id"] for r in r0],
        "G2_prefix_identity_bad": prefix_bad,
        "G2b_pool_sha_bad": sha_bad,
        "G3_cross_artifact_anchor_bad": anchor_bad,
        "G6_k_exceeds_list": {arm: {k: v for k, v in d.items() if v} for arm, d in g6.items()},
    }


def anchor_check(t4, recs):
    """G5: the CE arm @20 reproduces t4.C_metrics' recall_at_20 / ndcg_at_20."""
    bad = []
    by_id = {r["id"]: r for r in recs}
    for r in t4["per_query"]:
        rec = by_id[r["id"]]
        cm = r["C_metrics"]
        if abs(rec["R@20"] - cm["recall_at_20"]) > TOL or abs(rec["nDCG@20"] - cm["ndcg_at_20"]) > TOL:
            bad.append(r["id"])
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    t4 = json.loads(T4.read_text())
    t0 = json.loads(T0.read_text())
    r4, r0 = t4["per_query"], t0["per_query"]

    ce_rows, pool_rows = [], []
    for a, b in zip(r4, r0):
        assert a["id"] == b["id"], "id misalignment"
        n_reach = a["n_reachable"]
        ce_rows.append(dict(id=a["id"], query_type=a["query_type"], relevant_pages=a["relevant_pages"],
                            n_relevant=a["n_relevant"], n_reachable=n_reach,
                            pool_gold=round(a["C_pool_cov"] * n_reach), pages=_pages(a["W50_pages"]),
                            anchor_pages=a["C_pages"]))
        pool_rows.append(dict(id=b["id"], query_type=b["query_type"], relevant_pages=b["relevant_pages"],
                              n_relevant=b["n_relevant"], n_reachable=n_reach,
                              pool_gold=round(b["cov_fusion"] * n_reach), pages=_pages(b["fusion_ranked"])))

    res = {
        "meta": {
            "harness": "per_type_k_sweep.py",
            "read_only": True,
            "inputs": {"t4_endpoint.json": _sha256(T4), "t0_baseline.json": _sha256(T0)},
            "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
            "arms": {"CE": list(CE_KS), "POOL": list(POOL_KS)},
            "k_anchor": K_ANCHOR,
            "definition": ("R@k/nDCG@k/P@k by the evaluate_rag.py convention; cov@k = |gold in top-k|/n_reach; "
                           "ceilings pool-aware; capture = realised/ceiling, per-query then averaged"),
        },
        "guards": guards(t4, t0),
        "results": {},
    }
    ce = build_arm(ce_rows, "CE")
    res["guards"]["G5_anchor_bad"] = anchor_check(t4, ce["per_query"])
    # G3b: the two arms' pool_gold agree
    pg_ce = {r["id"]: r["pool_gold"] for r in ce_rows}
    pg_pool = {r["id"]: r["pool_gold"] for r in pool_rows}
    res["guards"]["G3b_pool_gold_mismatch"] = [i for i in pg_ce if pg_ce[i] != pg_pool[i]]
    # G4: monotone R@k and cov@k
    def _mono_bad(recs, ks, key):
        bad = []
        for r in recs:
            vals = [r[f"{key}@{k}"] for k in ks if r.get(f"{key}@{k}") is not None]
            if any(vals[i + 1] < vals[i] - 1e-12 for i in range(len(vals) - 1)):
                bad.append(r["id"])
        return bad
    res["guards"]["G4_monotone_R_bad"] = {"CE": _mono_bad(ce["per_query"], CE_KS, "R"),
                                          "POOL": _mono_bad(pool_rows, POOL_KS, "R")}
    res["results"]["CE"] = ce
    res["results"]["POOL"] = build_arm(pool_rows, "POOL")

    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))

    g = res["guards"]
    print(f"wrote {out}  ({out.stat().st_size} bytes)")
    print(f"G1 n={g['G1_population']} types={g['G1_types']} ids_align={g['G1_ids_align']}")
    print(f"G2 prefix-bad={len(g['G2_prefix_identity_bad'])}  G2b sha-bad={len(g['G2b_pool_sha_bad'])}  "
          f"G3 anchor-bad={len(g['G3_cross_artifact_anchor_bad'])}  G3b pool-gold-mismatch={len(g['G3b_pool_gold_mismatch'])}  "
          f"G5 anchor-bad={len(g['G5_anchor_bad'])}")
    print(f"G4 mono-bad R: CE={len(g['G4_monotone_R_bad']['CE'])} POOL={len(g['G4_monotone_R_bad']['POOL'])}")
    print()
    for arm in ("CE", "POOL"):
        ks = res["results"][arm]["ks"]
        print(f"=== arm {arm}  (k={ks}) ===")
        print(f"{'type':9s} | " + " | ".join(f"k={k:<3d}" for k in ks))
        for metric in ("R", "nDCG", "cov", "capN"):
            print(f"  {metric:5s}")
            for t in TYPES:
                row = res["results"][arm]["by_type"][t]["per_k"]
                print(f"  {t:9s} | " + " | ".join(f"{row[k][metric]:.3f}" if row[k].get(metric) is not None else "  -  " for k in ks))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
