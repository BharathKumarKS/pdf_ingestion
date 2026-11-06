#!/usr/bin/env python
"""policy_ab_verifier.py — an INDEPENDENT, stdlib-only re-derivation of the policy before/after.

Written separately from `policy_ab.py`, and it does NOT import it. It reads:
  * the RAW source  `t4_endpoint.json`  (the per-query C_metrics / Q_metrics T4 measured),
  * the router cache `policy_router_classes.json`,
  * the artifact     `policy_ab.json`,
and re-derives every aggregate, delta, CI and guard from the raw arrays, then compares the
artifact's recorded values against them. Any mismatch is a FAIL.

Run:  unset PYTHONPATH; uv run python -u logs/p1/step10/policy_ab_verifier.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
T4 = REPO / "logs/p1/step10/t4_endpoint.json"
ROUTER = REPO / "logs/p1/step10/policy_router_classes.json"
ART = REPO / "logs/p1/step10/policy_ab.json"

METRICS = ["ndcg_at_20", "map", "mrr_at_20", "recall_at_20",
           "hit_at_20", "precision_at_20", "f1_at_20"]
Z = 1.96
TOL = 1e-6

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok), detail))


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--t4", default=str(T4))
    ap.add_argument("--router", default=str(ROUTER))
    ap.add_argument("--art", default=str(ART))
    args = ap.parse_args()

    t4 = json.loads(Path(args.t4).read_text())
    router = json.loads(Path(args.router).read_text())["classes"]
    art = json.loads(Path(args.art).read_text())

    raw = {r["id"]: r for r in t4["per_query"]}

    # ── V1: the artifact covers the same 133 queries, keyed by id ─────────────
    ids_art = [r["id"] for r in art["per_query"]]
    check("V1 133 rows, same ids as T4",
          len(ids_art) == 133 and set(ids_art) == set(raw) and len(set(ids_art)) == 133,
          f"{len(ids_art)} rows, {len(set(ids_art))} unique")

    # ── V2: re-derive the SELECTION for both arms, per row ───────────────────
    sel_ok = True
    for r in art["per_query"]:
        qt = raw[r["id"]]["query_type"]
        exp_gold = "Q" if qt == "factual" else "C"
        exp_router = "Q" if router[r["id"]] == "factual" else "C"
        if r["selection_gold"] != exp_gold or r["selection_router"] != exp_router:
            sel_ok = False
            break
    check("V2 selection (gold + router) re-derived per row", sel_ok)

    # ── V3: re-derive each arm's per-query metrics and compare to the artifact ─
    bad = []
    for r in art["per_query"]:
        rid = r["id"]
        for arm, sel in (("C", "C"), ("P_gold", r["selection_gold"]),
                         ("P_router", r["selection_router"])):
            want = {k: raw[rid][f"{sel}_metrics"][k] for k in METRICS}
            if r[arm]["metrics"] != want:
                bad.append((rid, arm))
    check("V3 every arm's per-query metrics re-derived from T4's raw arrays",
          not bad, f"{len(bad)} mismatches" + (f" e.g. {bad[:3]}" if bad else ""))

    # ── V4: re-derive the aggregates (mean per metric, overall + per type) ────
    agg_bad = []
    for arm in ("C", "P_gold", "P_router"):
        rows = art["per_query"]
        for scope, sel in (("overall", rows),
                           *[(t, [r for r in rows if r["query_type"] == t])
                             for t in ("factual", "multihop", "overview")]):
            blk = (art["aggregate"][arm]["overall"] if scope == "overall"
                   else art["aggregate"][arm]["by_type"][scope])
            for k in METRICS:
                got = mean([r[arm]["metrics"][k] for r in sel])
                if abs(round(got, 6) - blk[k]) > TOL:
                    agg_bad.append((arm, scope, k, round(got, 6), blk[k]))
    check("V4 aggregates (mean per metric, overall + per type) re-derived",
          not agg_bad, f"{len(agg_bad)} mismatches" + (f" e.g. {agg_bad[:3]}" if agg_bad else ""))

    # ── V5: re-derive the paired deltas, CIs, resolved flags and W/L/T ────────
    d_bad = []
    for arm_key in ("P_gold_minus_C", "P_router_minus_C"):
        arm = arm_key.split("_minus_")[0]
        for scope, sel in (("overall", art["per_query"]),
                           *[(t, [r for r in art["per_query"] if r["query_type"] == t])
                             for t in ("factual", "multihop", "overview")]):
            blk = (art["deltas"][arm_key]["overall"] if scope == "overall"
                   else art["deltas"][arm_key]["by_type"][scope])
            for k in METRICS:
                diffs = [r[arm]["metrics"][k] - r["C"]["metrics"][k] for r in sel]
                m = mean(diffs)
                sd = math.sqrt(sum((x - m) ** 2 for x in diffs) / (len(diffs) - 1)) if len(diffs) > 1 else 0.0
                half = Z * sd / math.sqrt(len(diffs))
                lo, hi = round(m - half, 6), round(m + half, 6)
                exp_res = (m - half) * (m + half) > 0 and len(diffs) > 1
                wlt = [sum(1 for x in diffs if x > 0), sum(1 for x in diffs if x < 0),
                       sum(1 for x in diffs if x == 0)]
                if (abs(round(m, 6) - blk[k]["mean"]) > TOL
                        or [lo, hi] != blk[k]["ci95"]
                        or blk[k]["resolved"] != exp_res
                        or blk[k]["wlt"] != wlt):
                    d_bad.append((arm_key, scope, k, round(m, 6), blk[k]["mean"]))
    check("V5 paired deltas: mean, CI95, resolved flag, W/L/T all re-derived",
          not d_bad, f"{len(d_bad)} mismatches" + (f" e.g. {d_bad[:3]}" if d_bad else ""))

    # ── V6: G1 — the composition selects the RIGHT arm's raw metrics ──────────
    g1_bad = [r["id"] for r in art["per_query"]
              if r["P_gold"]["metrics"] != {k: raw[r["id"]][
                  f"{'Q' if raw[r['id']]['query_type'] == 'factual' else 'C'}_metrics"][k]
                  for k in METRICS}]
    check("V6 G1 composition wired exactly (re-derived)", not g1_bad, f"{len(g1_bad)} bad")

    # ── V7: G2/G3b — policy == C on overview + multihop, every metric ─────────
    other = [r for r in art["per_query"] if r["query_type"] in ("overview", "multihop")]
    check("V7 G2/G3b policy == C on overview+multihop (every metric)",
          all(r["P_gold"]["metrics"] == r["C"]["metrics"] for r in other),
          f"{len(other)} rows")

    # ── V8: G3a — the pool is identical per query ─────────────────────────────
    check("V8 G3a pool size+sha identical per query",
          all(r["C"]["pool_size"] == r["P_gold"]["pool_size"] == r["P_router"]["pool_size"]
              and r["C"]["pool_sha"] == r["P_gold"]["pool_sha"] == r["P_router"]["pool_sha"]
              for r in art["per_query"]))

    # ── V9: the router agreement + distribution re-derived ────────────────────
    agree = mean([1.0 if router[r["id"]] == raw[r["id"]]["query_type"] else 0.0
                  for r in art["per_query"]])
    dist = {c: sum(1 for v in router.values() if v == c) for c in set(router.values())}
    check("V9 router-vs-gold agreement + class distribution re-derived",
          abs(round(agree, 4) - art["router_vs_gold"]["agreement"]) <= 1e-9
          and dist == art["router_class_distribution"],
          f"agreement {round(agree, 4)} vs {art['router_vs_gold']['agreement']}; dist {dist}")

    # ── V10: G3c — the factual recall movement is reported and re-derived ─────
    fact = [r for r in art["per_query"] if r["query_type"] == "factual"]
    r20 = [r["P_gold"]["metrics"]["recall_at_20"] - r["C"]["metrics"]["recall_at_20"] for r in fact]
    rec = art["g3c_factual_recall_movement"]["recall_at_20"]
    check("V10 G3c factual R@20 movement re-derived",
          rec["n"] == len(fact) and abs(rec["mean"] - round(mean(r20), 6)) <= TOL
          and rec["n_moved"] == sum(1 for x in r20 if x != 0),
          f"n={rec['n']} mean={rec['mean']} moved={rec['n_moved']}")

    # ── V11: the headline direction (the whole point of the run) ─────────────
    o_gold = art["deltas"]["P_gold_minus_C"]["overall"]["ndcg_at_20"]
    o_rt = art["deltas"]["P_router_minus_C"]["overall"]["ndcg_at_20"]
    check("V11 P_gold and P_router both POSITIVE and RESOLVED on overall nDCG, "
          "and P_router <= P_gold (the attenuation)",
          o_gold["mean"] > 0 and o_gold["resolved"]
          and o_rt["mean"] > 0 and o_rt["resolved"]
          and o_rt["mean"] <= o_gold["mean"],
          f"P_gold {o_gold['mean']:+.4f} (R={o_gold['resolved']}), "
          f"P_router {o_rt['mean']:+.4f} (R={o_rt['resolved']})")

    # ── V12: the guard block is ALL TRUE and every guard re-derives ───────────
    check("V12 every recorded guard is True", all(art["guards"].values()),
          f"{sum(art['guards'].values())}/{len(art['guards'])}")

    print("=== policy_ab verifier ===")
    ok = True
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and passed
    print(f"\n{len(checks)} checks, {sum(1 for _, p, _ in checks if p)} passed")
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
