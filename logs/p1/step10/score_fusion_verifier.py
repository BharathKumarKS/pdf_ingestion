"""Independent verifier for the 4A score-fusion run (§I103).

**stdlib only** — reads the WRITTEN artifact and re-derives every aggregate, every delta, every CI,
every guard and every composition count from the RAW per-query page lists and labels, including
re-implementing the endpoint metrics, so `compute_retrieval_metrics` is not trusted either.

    python logs/p1/step10/score_fusion_verifier.py --check [--artifact P]
    python logs/p1/step10/score_fusion_verifier.py --list-checks   # for the mutation proof

Every check must be able to FAIL. The mutation proof (score_fusion_mutation.py) reddens each check in
turn; a check no mutation can redden is inert and is reported as such.
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
ART = HERE / "score_fusion.json"
LANE = HERE / "lane_inclusion.json"
TOL = 1e-9
ANCHOR_TOL = 1e-4

ARMS = ("S0", "S1", "S2")
TREATMENTS = ("S1", "S2")
TYPES = ("factual", "multihop", "overview")
EXPECTED_N = {"factual": 53, "overview": 40, "multihop": 40}
ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "recall_at_100",
                 "hit_at_20", "precision_at_20", "precision_ceiling_at_20", "f1_at_20")
BOOT_N = 10000
BOOT_SEED = 20261031

checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def metrics_from_pages(pages: list, pool_pages: list, rel: set[int], k: int = 20) -> dict:
    """Re-implement the endpoint metrics from the page lists alone (stdlib).

    Exact where no page-less candidate reached the endpoint (the graph lane can append a page-less
    hit for multihop); the exclusion is reported separately. `recall_at_100` is the POOL recall
    (`hits_above` is the whole pool at threshold 0.0), re-derived from the pool page list.
    """
    seen: set[int] = set()
    gains = []
    for p in pages:
        if p is not None and int(p) in rel and int(p) not in seen:
            gains.append(1)
            seen.add(int(p))
        else:
            gains.append(0)
    n_hits = sum(gains)
    n_rel = len(rel)
    if not n_rel:
        return {}
    recall = n_hits / n_rel
    hit = 1.0 if n_hits > 0 else 0.0
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n_rel, k)))
    ndcg = dcg / idcg if idcg > 0 else 0.0
    prec = n_hits / k
    pceil = min(n_rel, k) / k
    f1 = (2 * prec * recall / (prec + recall)) if (prec + recall) > 0 else 0.0
    ap = 0.0
    running = 0
    for i, g in enumerate(gains, start=1):
        if g:
            running += 1
            ap += running / i
    ap /= n_rel
    pool_recall = len(set(int(p) for p in pool_pages) & rel) / n_rel
    return {f"ndcg_at_{k}": round(ndcg, 4), "map": round(ap, 4),
            f"recall_at_{k}": round(recall, 4), "recall_at_100": round(pool_recall, 4),
            f"hit_at_{k}": round(hit, 4),
            f"precision_at_{k}": round(prec, 4), f"precision_ceiling_at_{k}": round(pceil, 4),
            f"f1_at_{k}": round(f1, 4)}


def mrr_from_pages(pages: list, rel: set[int]) -> float:
    for rank, p in enumerate(pages, start=1):
        if p is not None and int(p) in rel:
            return round(1.0 / rank, 4)
    return 0.0


def boot(deltas: list[float]) -> dict:
    """§4 — the SAME stdlib bootstrap the harness runs (seed 20261031), re-implemented here."""
    n = len(deltas)
    if n < 2:
        return {"n": n, "mean": float(statistics.mean(deltas)) if deltas else None,
                "ci95": None, "resolved": False}
    rng = random.Random(BOOT_SEED)
    means = []
    for _ in range(BOOT_N):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo, hi = means[int(0.025 * BOOT_N)], means[int(0.975 * BOOT_N)]
    return {"n": n, "mean": float(statistics.mean(deltas)), "ci95": [lo, hi],
            "resolved": bool(lo > 0.0 or hi < 0.0)}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return float(statistics.mean(xs)) if xs else None


def close(a, b, tol=TOL):
    return a is not None and b is not None and abs(a - b) <= tol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list-checks", action="store_true")
    ap.add_argument("--artifact", default=str(ART))
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    rows = art["per_query"]
    ok_rows = [r for r in rows if "error" not in r]
    agg = art["aggregate"]
    dl = art["deltas"]
    g = art["guards"]
    gd = art["guard_detail"]

    # ── V1 population ────────────────────────────────────────────────────────────────────────
    check("V1_n_queries_133", art["meta"]["n_queries"] == len(rows) == 133,
          f"meta={art['meta']['n_queries']} rows={len(rows)}")
    for t in TYPES:
        n = len([r for r in ok_rows if r["query_type"] == t])
        check(f"V1b_n_{t}", n == EXPECTED_N[t], f"got={n} expected={EXPECTED_N[t]}")
    check("V1c_arms_present", tuple(sorted(agg.keys())) == tuple(sorted(ARMS)), f"{sorted(agg.keys())}")

    # ── V2 the aggregates: (B) the AGGREGATION and (A) the metric FUNCTION ───────────────────
    metric_excl: dict = {}
    for arm in ARMS:
        for scope, sub in [("overall", ok_rows)] + [(t, [r for r in ok_rows if r["query_type"] == t])
                                                    for t in TYPES]:
            rec = agg[arm]["overall"] if scope == "overall" else agg[arm]["by_type"][scope]
            for k in ENDPOINT_KEYS + ("coverage_reachable", "pool_cov"):
                vals = [r[f"{arm}_metrics"][k] if k not in ("coverage_reachable", "pool_cov")
                        else r[f"{arm}_cov" if k == "coverage_reachable" else f"{arm}_pool_cov"]
                        for r in sub if r.get(f"{arm}_metrics")]
                check(f"V2_{arm}_{scope}_{k}", close(rec.get(k), mean(vals)),
                      f"got={rec.get(k)} exp={mean(vals)}")
            got, want = rec.get("pool_mean"), mean([r[f"{arm}_pool_size"] for r in sub])
            check(f"V2_{arm}_{scope}_pool_mean", close(got, want), f"got={got} exp={want}")
            # (A) the metric function, on the rows where it must be exact
            mism, n_excl = [], 0
            for r in sub:
                if r[f"{arm}_slots_n"] != len(r[f"{arm}_pages"]):
                    n_excl += 1
                    continue
                rel = set(int(p) for p in r["relevant_pages"])
                m = metrics_from_pages(r[f"{arm}_pages"], r[f"{arm}_pool_pages"], rel)
                m["mrr_at_20"] = mrr_from_pages(r[f"{arm}_pages"], rel)
                for k in ENDPOINT_KEYS:
                    if abs(m[k] - r[f"{arm}_metrics"][k]) > 1e-6:
                        mism.append((r["id"], k, m[k], r[f"{arm}_metrics"][k]))
            metric_excl[f"{arm}/{scope}"] = n_excl
            check(f"V2b_{arm}_{scope}_metric_fn_exact", not mism, f"{len(mism)}: {mism[:4]}")

    # ── V3 the pool sha256 is a function of the recorded pool pages ──────────────────────────
    bad = [r["id"] for r in ok_rows for arm in ARMS
           if r[f"{arm}_pool_sha"] != hashlib.sha256(
               ",".join(map(str, r[f"{arm}_pool_pages"])).encode()).hexdigest()[:16]]
    check("V3_pool_sha_recomputes", not bad, f"{len(bad)} mismatches: {bad[:5]}")

    # ── V4 coverage/pool_cov re-derived from the page lists + n_reachable ─────────────────────
    # ⚠️ Exact iff the recorded page set is a SUBSET of the reachable set. The graph lane can append
    # a page for multihop that sits outside the content window, which would make the re-derivation
    # exceed the recorded value — a MECHANISM, asserted, not hidden.
    cov_mism = []
    for r in ok_rows:
        for arm in ARMS:
            nre = r["n_reachable"]
            if not nre:
                continue
            rec_cov = r[f"{arm}_cov"]
            rec_pcov = r[f"{arm}_pool_cov"]
            want_cov = len(set(r[f"{arm}_pages"]) & set(r["relevant_pages"])) / nre
            want_pcov = len(set(r[f"{arm}_pool_pages"]) & set(r["relevant_pages"])) / nre
            if not (close(rec_cov, want_cov, 1e-6) and close(rec_pcov, want_pcov, 1e-6)):
                cov_mism.append((r["id"], arm, r["query_type"]))
    not_multi = [c for c in cov_mism if c[2] != "multihop"]
    check("V4_coverage_rederives_exact", not cov_mism,
          f"{len(cov_mism)} inexact; non-multihop: {not_multi[:5]}")

    # ── V5 the page-less endpoint candidate: a REPORTED diagnostic, with its mechanism ────────
    affected = sorted({r["id"] for r in ok_rows for arm in ARMS
                       if r[f"{arm}_slots_n"] != len(r[f"{arm}_pages"])})
    types_of = {r["id"]: r["query_type"] for r in ok_rows}
    check("V5_pageless_endpoint_candidates_are_all_multihop",
          all(types_of.get(q) == "multihop" for q in affected),
          f"affected={affected[:10]}")

    # ── V6 every delta re-derived (bootstrap, same seed) ──────────────────────────────────────
    for arm in TREATMENTS:
        for k in ENDPOINT_KEYS:
            d = [r[f"{arm}_metrics"][k] - r["S0_metrics"][k] for r in ok_rows]
            got, want = dl[f"{arm}_minus_S0"][k], boot(d)
            check(f"V6_{arm}_minus_S0_{k}_mean", close(got["mean"], want["mean"]),
                  f"got={got['mean']} exp={want['mean']}")
            check(f"V6_{arm}_minus_S0_{k}_n", got["n"] == want["n"], f"{got['n']} vs {want['n']}")
            if want["ci95"] and got.get("ci95"):
                check(f"V6_{arm}_minus_S0_{k}_ci",
                      close(got["ci95"][0], want["ci95"][0]) and close(got["ci95"][1], want["ci95"][1]),
                      f"got={got['ci95']} exp={want['ci95']}")
            check(f"V6_{arm}_minus_S0_{k}_resolved", got["resolved"] == want["resolved"],
                  f"{got['resolved']} vs {want['resolved']}")
        for t in TYPES:
            sub = [r for r in ok_rows if r["query_type"] == t]
            for k in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20"):
                d = [r[f"{arm}_metrics"][k] - r["S0_metrics"][k] for r in sub]
                got, want = dl[f"{arm}_minus_S0_by_type"][t][k], boot(d)
                check(f"V6_{arm}_{t}_{k}_mean", close(got["mean"], want["mean"]),
                      f"got={got['mean']} exp={want['mean']}")
        d = [(r[f"{arm}_pool_cov"] - r["S0_pool_cov"]) for r in ok_rows
             if r.get(f"{arm}_pool_cov") is not None and r.get("S0_pool_cov") is not None]
        got, want = dl[f"poolcov_{arm}_minus_S0"], boot(d)
        check(f"V6_poolcov_{arm}_minus_S0_mean", close(got["mean"], want["mean"]),
              f"got={got['mean']} exp={want['mean']}")

    # ── V7 the guards, re-derived from the raw rows ───────────────────────────────────────────
    counts = {qt: sum(1 for r in rows if r["query_type"] == qt) for qt in TYPES}
    every_arm = all(all(r.get(f"{a}_metrics") for a in ARMS) for r in ok_rows)
    check("V7_G1_population", g["G1_population_133_0_errors_all_arms"] ==
          (len(rows) == 133 and not art["errors"] and every_arm and
           counts == {"factual": 53, "multihop": 40, "overview": 40}),
          f"recorded={g['G1_population_133_0_errors_all_arms']}")

    bad = [(r["id"], a, r[f"{a}_lane_drops"]) for r in ok_rows for a in ARMS
           if any(v for k, v in (r.get(f"{a}_lane_drops") or {}).items() if k != "mmr")]
    check("V7_G5_no_lane_dropout", g["G5_no_lane_dropout_survived"] == (not bad), f"recomputed={len(bad)}")

    g3_set_bad = [r["id"] for r in ok_rows
                  if not (r.get("S0_lane_stats")
                          and [s["n"] for s in r["S0_lane_stats"]]
                          == [s["n"] for s in r.get("S1_lane_stats") or []]
                          == [s["n"] for s in r.get("S2_lane_stats") or []])]
    check("V7_G3_lane_set", g["G3_three_arms_share_the_same_lane_set"] == (not g3_set_bad),
          f"recomputed={len(g3_set_bad)}")
    g3_digest_bad = [r["id"] for r in ok_rows
                     if not (r.get("S0_lane_digest") and r["S0_lane_digest"] == r.get("S1_lane_digest")
                             == r.get("S2_lane_digest"))]
    check("V7_G3_digest_list_reported", gd["G3"]["n_digest_mismatch"] == len(g3_digest_bad),
          f"recorded={gd['G3']['n_digest_mismatch']} recomputed={len(g3_digest_bad)}")
    check("V7_G3b_inert", g["G3b_digest_flip_is_pool_inert"] == all(
        v["pool_sha_stable"] and v["pages_stable"] for v in gd["G3b"].values()),
        f"recorded={g['G3b_digest_flip_is_pool_inert']} n_rechecked={len(gd['G3b'])}")
    check("V7_G3b_covers_every_flip", set(gd["G3b"].keys()) == set(g3_digest_bad),
          f"n_recheck={len(gd['G3b'])} n_flips={len(g3_digest_bad)}")

    fracs, degen = {}, {}
    for pos, name in enumerate(("dense", "sparse", "colbert")):
        gt, tot, dg = 0, 0, 0
        for r in ok_rows:
            st = r.get("S1_lane_stats") or []
            if pos < len(st):
                tot += 1
                if st[pos]["max_gt_min"]:
                    gt += 1
                else:
                    dg += 1
        fracs[name] = round(gt / tot, 4) if tot else None
        degen[name] = dg
    check("V7_G4_normalisers_exercised", g["G4_normalisers_exercised_each_lane"] ==
          all(v is not None and v > 0.0 for v in fracs.values()), f"{fracs}")
    check("V7_G4b_lane_stats_reported", gd["G4"]["max_gt_min_fraction"] == fracs,
          f"got={gd['G4']['max_gt_min_fraction']} exp={fracs}")

    nulls = [f"{a}.{qt}.{k}" for a in ARMS for qt, cell in
             [("overall", agg[a]["overall"])] + list(agg[a]["by_type"].items())
             for k in ("coverage_reachable", "pool_cov", *ENDPOINT_KEYS) if cell.get(k) is None]
    dedup_bad = [r["id"] for r in ok_rows for a in ARMS
                 if len(r[f"{a}_pages"]) != len(set(r[f"{a}_pages"]))]
    check("V7_G6_no_nan_null_dedup", g["G6_no_nan_null_and_page_dedup"] ==
          ((not nulls) and (not dedup_bad)), f"nulls={len(nulls)} dedup={len(dedup_bad)}")

    # ── V8 the G2 anchor against lane_inclusion's F0 (§9) ────────────────────────────────────
    # ⚠️ Only the keys the ANCHOR carries are compared (F0 has no `recall_at_100`); the harness's
    # corrected G2 does the same. Comparing a missing key as 0 is the over-strict-check class.
    lane = json.loads(LANE.read_text())["aggregate"]["F0"]
    for scope in ("overall",) + TYPES:
        ref = lane["overall"] if scope == "overall" else lane["by_type"][scope]
        got = agg["S0"]["overall"] if scope == "overall" else agg["S0"]["by_type"][scope]
        keys = [k for k in ENDPOINT_KEYS + ("pool_cov",) if k in ref]
        gaps = {k: abs(got.get(k) - ref.get(k)) for k in keys}
        check(f"V8_G2_anchor_{scope}", max(gaps.values()) <= ANCHOR_TOL,
              f"max_gap={max(gaps.values()):.2e} keys={len(keys)}")
    check("V8_G2_anchor_reports_missing_keys",
          gd.get("G2_anchor_missing_keys") == [k for k in ENDPOINT_KEYS + ("pool_cov",)
                                               if k not in lane["overall"]],
          f"recorded={gd.get('G2_anchor_missing_keys')}")

    # ── V9 the composition (§4 prediction 3) re-derived ──────────────────────────────────────
    for arm in TREATMENTS:
        diff = [r["id"] for r in ok_rows if set(r[f"{arm}_pool_pages"]) != set(r["S0_pool_pages"])]
        rec = art["composition"][arm]
        check(f"V9_composition_{arm}", rec["n_differs"] == len(diff)
              and rec["majority"] == (len(diff) > len(ok_rows) / 2),
              f"got={rec['n_differs']} exp={len(diff)}")

    # ── V10 no NaN / None in the aggregates ─────────────────────────────────────────────────
    bad = []
    for arm in ARMS:
        for scope, rec in [("overall", agg[arm]["overall"])] + list(agg[arm]["by_type"].items()):
            for k, v in rec.items():
                if v is None or (isinstance(v, float) and v != v):
                    bad.append(f"{arm}.{scope}.{k}")
    check("V10_no_nan", not bad, f"{bad[:6]}")

    print(f"artifact : {args.artifact}")
    print()
    if args.list_checks:
        for name, okk, _ in checks:
            print(f"{'PASS' if okk else 'FAIL'} {name}")
        print(f"{len(checks)} checks")
        return 0
    n_fail = 0
    for name, okk, detail in checks:
        if not okk:
            n_fail += 1
            print(f"  FAIL  {name}   {detail}")
    print(f"{len(checks)} checks, {n_fail} failed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
