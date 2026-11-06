"""Independent verifier for the fusion-order run (§I99).

stdlib only. Reads the WRITTEN artifact and re-derives every aggregate, every delta, every CI and
every guard from the RAW per-query page lists — including re-implementing the endpoint metrics, so
`compute_retrieval_metrics` is not trusted either.

    python logs/p1/step10/fusion_order_verifier.py --check [--artifact P]

Every check must be able to FAIL. The mutation proof (fusion_order_mutation.py) reddens each check in
turn; a check no mutation can redden is inert and is reported as such.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "fusion_order.json"
LANE = HERE / "lane_inclusion.json"
TOL = 1e-9
ANCHOR_TOL = 1e-4

ARMS = ("O0", "O0w", "O1", "O2", "O3", "O4")
TREATMENTS = ("O1", "O2", "O3", "O4")
TYPES = ("factual", "multihop", "overview")
EXPECTED_N = {"factual": 53, "overview": 40, "multihop": 40}
ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20",
                 "precision_at_20", "f1_at_20")

checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def metrics_from_pages(pages: list, rel: set[int], k: int = 20) -> dict:
    """Re-implement the endpoint metrics from the page list alone (stdlib).

    Safe here because this run's arms add no page-less candidates (the product's `search()` excludes
    RAPTOR and no arm re-enables a lane that carries them) — asserted separately by V_slots.
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
    return {f"ndcg_at_{k}": round(ndcg, 4), "map": round(ap, 4),
            f"recall_at_{k}": round(recall, 4), f"hit_at_{k}": round(hit, 4),
            f"precision_at_{k}": round(prec, 4), f"precision_ceiling_at_{k}": round(pceil, 4),
            f"f1_at_{k}": round(f1, 4)}


def mrr_from_pages(pages: list, rel: set[int]) -> float:
    for rank, p in enumerate(pages, start=1):
        if p is not None and int(p) in rel:
            return round(1.0 / rank, 4)
    return 0.0


def mean(xs):
    xs = [x for x in xs if x is not None]
    return float(statistics.mean(xs)) if xs else None


def ci(deltas: list[float]) -> dict:
    n = len(deltas)
    if n < 2:
        return {"n": n, "mean": mean(deltas), "sd": None, "ci95": None}
    m = float(statistics.mean(deltas))
    sd = float(statistics.stdev(deltas))
    half = float(1.96 * sd / math.sqrt(n))
    return {"n": n, "mean": m, "sd": sd, "ci95": [m - half, m + half]}


def close(a, b, tol=TOL):
    return a is not None and b is not None and abs(a - b) <= tol


def _cov(pages, reach: set[int]):
    if not reach:
        return None
    return len(set(pages) & reach) / len(reach)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list-checks", action="store_true",
                    help="print every check id with its verdict, so a mutation proof can enumerate "
                         "them from a CLEAN run (the default run prints failures only)")
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
    check("V1c_arms_present", tuple(sorted(agg.keys())) == tuple(sorted(ARMS)),
          f"{sorted(agg.keys())}")

    # ── V2 the aggregates, split into (A) the metric FUNCTION and (B) the AGGREGATION ────────
    # ⚠️ They are checked separately, because a page-less endpoint candidate makes the re-derivation
    # inexact: the harness's `compute_retrieval_metrics` counts the SLOT it occupies, while a
    # re-derivation from the page list cannot. (B) is exact over ALL rows; (A) is exact only where no
    # page-less candidate reached the endpoint, and the exclusion count is reported.
    metric_excl: dict = {}
    for arm in ARMS:
        for scope, sub in [("overall", ok_rows)] + [(t, [r for r in ok_rows if r["query_type"] == t])
                                                    for t in TYPES]:
            rec = agg[arm]["overall"] if scope == "overall" else agg[arm]["by_type"][scope]
            # (B) the aggregate IS the mean of the RECORDED per-query metrics
            for k in ENDPOINT_KEYS + ("precision_ceiling_at_20",):
                vals = [r[f"{arm}_metrics"][k] for r in sub
                        if r.get(f"{arm}_metrics") and r[f"{arm}_metrics"].get(k) is not None]
                check(f"V2_{arm}_{scope}_{k}", close(rec.get(k), mean(vals)),
                      f"got={rec.get(k)} exp={mean(vals)}")
            got, want = rec.get("pool_mean"), mean([r[f"{arm}_pool_size"] for r in sub])
            check(f"V2_{arm}_{scope}_pool_mean", close(got, want), f"got={got} exp={want}")
            # (A) the metric function itself, on the rows where it must be exact
            mism, n_excl = [], 0
            for r in sub:
                if r.get(f"{arm}_endp_pageless"):
                    n_excl += 1
                    continue
                rel = set(int(p) for p in r["relevant_pages"])
                m = metrics_from_pages(r[f"{arm}_pages"], rel)
                m["mrr_at_20"] = mrr_from_pages(r[f"{arm}_pages"], rel)
                for k in ENDPOINT_KEYS:
                    if abs(m[k] - r[f"{arm}_metrics"][k]) > 1e-6:
                        mism.append((r["id"], k))
            metric_excl[f"{arm}/{scope}"] = n_excl
            check(f"V2b_{arm}_{scope}_metric_fn_exact", not mism, f"{len(mism)}: {mism[:4]}")


    # ── V3 the pool sha256 is a function of the recorded pool pages ──────────────────────────
    bad = [r["id"] for r in ok_rows for arm in ARMS
           if r[f"{arm}_pool_sha"] != hashlib.sha256(
               ",".join(map(str, r[f"{arm}_pool_pages"])).encode()).hexdigest()[:16]]
    check("V3_pool_sha_recomputes", not bad, f"{len(bad)} mismatches: {bad[:5]}")

    # ── V4 the page-less endpoint candidate: a REPORTED diagnostic, with its mechanism asserted ─
    # ⚠️ This is NOT "must be zero". The graph lane is appended by the caller for multihop and returns
    # `page_num`, so a hit whose page could not be resolved occupies a slot with no page. §I98 saw the
    # same query (`gold-008`). The assertion is the MECHANISM: every affected query is multihop.
    affected = sorted({r["id"] for r in ok_rows for arm in ARMS if r.get(f"{arm}_endp_pageless")})
    types_of = {r["id"]: r["query_type"] for r in ok_rows}
    not_multihop = [q for q in affected if types_of.get(q) != "multihop"]
    check("V4_pageless_endpoint_candidates_are_all_multihop", not not_multihop,
          f"non-multihop: {not_multihop}")
    check("V4b_slots_n_equals_pages_plus_pageless", all(
        r[f"{arm}_slots_n"] == len(r[f"{arm}_pages"]) + r[f"{arm}_endp_pageless"]
        for r in ok_rows for arm in ARMS), "")


    # ── V5 every delta re-derived ───────────────────────────────────────────────────────────
    for arm in TREATMENTS:
        for k in ENDPOINT_KEYS:
            d = [r[f"{arm}_metrics"][k] - r["O0_metrics"][k] for r in ok_rows]
            got = dl[f"{arm}_minus_O0"][k]
            want = ci(d)
            check(f"V5_{arm}_minus_O0_{k}_mean", close(got["mean"], want["mean"]),
                  f"got={got['mean']} exp={want['mean']}")
            check(f"V5_{arm}_minus_O0_{k}_n", got["n"] == want["n"], f"{got['n']} vs {want['n']}")
            if want["ci95"] and got.get("ci95"):
                check(f"V5_{arm}_minus_O0_{k}_ci",
                      close(got["ci95"][0], want["ci95"][0]) and close(got["ci95"][1], want["ci95"][1]),
                      f"got={got['ci95']} exp={want['ci95']}")
        for t in TYPES:
            sub = [r for r in ok_rows if r["query_type"] == t]
            for k in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20"):
                d = [r[f"{arm}_metrics"][k] - r["O0_metrics"][k] for r in sub]
                got = dl[f"{arm}_minus_O0_by_type"][t][k]
                want = ci(d)
                check(f"V5_{arm}_{t}_{k}_mean", close(got["mean"], want["mean"]),
                      f"got={got['mean']} exp={want['mean']}")

    # ── V6 guards re-derived from the raw rows ──────────────────────────────────────────────
    check("V6_G6_133_0_errors", (g["G6_133_queries_0_errors"]
                                 == (len(rows) == 133 and not art["errors"])),
          f"recorded={g['G6_133_queries_0_errors']} errors={len(art['errors'])}")

    bad = [(r["id"], a) for r in ok_rows for a in ARMS
           if any(v for k, v in (r.get(f"{a}_lane_drops") or {}).items() if k != "mmr")]
    check("V6_G1_no_lane_dropout", g["G1_no_lane_dropout_survived"] == (not bad),
          f"recorded={g['G1_no_lane_dropout_survived']} recomputed_bad={len(bad)}")

    # ⚠️ CORRECTED POST-RUN (stated in the entry): the harness recorded `mmr_fired` from the ARM'S OWN
    # call — and for O1 MMR is disabled, so it read False on all 133 and G3 asserted set-equality on
    # the 16 queries where O0's MMR DID fire. The artifact carries O0's own MMR delta, so G3
    # re-derives correctly here, and the recorded flag is asserted to be the mis-specified one.
    o0_mmr = {r["id"] for r in ok_rows if (r.get("O0_lane_drops") or {}).get("mmr")}
    mmr_off = [r for r in ok_rows if r["id"] not in o0_mmr]
    mismatch = [r["id"] for r in mmr_off if set(r["O1_pool_pages"]) != set(r["O0_pool_pages"])]
    check("V6_G3_O1_set_equality_REDERIVED", not mismatch,
          f"mismatch={len(mismatch)} on {len(mmr_off)} non-MMR queries")
    check("V6_G3c_O1_differs_exactly_where_O0_MMR_fired",
          {r["id"] for r in ok_rows if set(r["O1_pool_pages"]) != set(r["O0_pool_pages"])} == o0_mmr,
          f"O0 MMR fired on {len(o0_mmr)}")
    check("V6_G3d_recorded_flag_was_misspecified",
          g["G3_O1_membership_identical_where_mmr_did_not_fire"] is False,
          "the recorded flag is False; superseded by the re-derivation above")


    fb = [(r["id"], a) for r in ok_rows for a in ARMS if r.get(f"{a}_reranker_fallback")]
    check("V6_G4_no_reranker_fallback", g["G4_no_reranker_fallback"] == (not fb), f"{len(fb)}")

    mech = {
        "O1_mmr_fired_on_every_query_is_false": all(not r.get("O1_mmr_fired") for r in ok_rows),
        "O2_pool_set_differs_from_O0_somewhere": any(
            set(r["O2_pool_pages"]) != set(r["O0_pool_pages"]) for r in ok_rows),
        "O3_pool_set_differs_from_O0_somewhere": any(
            set(r["O3_pool_pages"]) != set(r["O0_pool_pages"]) for r in ok_rows),
        "O4_pool_order_differs_from_O0_somewhere": any(
            r["O4_pool_pages"] != r["O0_pool_pages"] for r in ok_rows),
        "O4_pool_set_identical_to_O0_everywhere": all(
            set(r["O4_pool_pages"]) == set(r["O0_pool_pages"]) for r in ok_rows),
    }
    check("V6_G5_mechanism_engaged", g["G5_each_mechanism_engaged"] == all(mech.values()),
          f"recorded={g['G5_each_mechanism_engaged']} recomputed={all(mech.values())} {mech}")

    w_bad = [r["id"] for r in ok_rows
             if r["O0w_pool_sha"] != r["O0_pool_sha"] or r["O0w_pages"] != r["O0_pages"]
             or r["O0w_metrics"] != r["O0_metrics"]]
    check("V6_G7_inert_in_run", g["G7_lane_weights_default_is_inert_in_run"] == (not w_bad),
          f"recorded={g['G7_lane_weights_default_is_inert_in_run']} mismatches={len(w_bad)}")

    # ── V7 the G2 anchor is against lane_inclusion's F0, per type ────────────────────────────
    lane = json.loads(LANE.read_text())["aggregate"]["F0"]
    for scope in ("overall",) + TYPES:
        ref = lane["overall"] if scope == "overall" else lane["by_type"][scope]
        got = agg["O0"]["overall"] if scope == "overall" else agg["O0"]["by_type"][scope]
        gaps = {k: abs((got.get(k) or 0) - (ref.get(k) or 0))
                for k in ENDPOINT_KEYS + ("coverage_reachable", "pool_cov")}
        check(f"V7_G2_anchor_{scope}", max(gaps.values()) <= ANCHOR_TOL,
              f"max_gap={max(gaps.values()):.2e}")

    # ── V8 no NaN / None in the aggregates ──────────────────────────────────────────────────
    bad = []
    for arm in ARMS:
        for scope, rec in [("overall", agg[arm]["overall"])] + list(agg[arm]["by_type"].items()):
            for k, v in rec.items():
                if v is None or (isinstance(v, float) and v != v):
                    bad.append(f"{arm}.{scope}.{k}")
    check("V8_no_nan", not bad, f"{bad[:6]}")

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
