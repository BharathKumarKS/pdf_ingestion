#!/usr/bin/env python
"""Independent verifier for lane plan S5 — reads ONLY written JSON, re-derives from the RAW per-query
arrays, stdlib only (no numpy, no project imports).

Pre-registration §7: `logs/p1/step10/lane_inclusion_verifier.py`, re-deriving G1-G6, the per-arm
aggregates, every paired delta with its CI, and every ratio quoted.

WHAT IT DOES NOT RE-DERIVE, stated rather than implied: the POOL's page-less candidate count
(`{arm}_pool_pageless`). Re-deriving it needs the pool's positional slot list, which this run does
not record — `{arm}_pool_pages` is page-DEDUPED and drops the page-less candidates by construction
(the T4 §15 lesson, applied to the pool). The field is a reported diagnostic, and a future run should
record `{arm}_pool_slots` so it becomes re-derivable. No tolerance is widened to cover this.

Usage:
  python lane_inclusion_verifier.py --check          # verify the artifact as written
  python lane_inclusion_verifier.py --extract        # write a compact reviewer pack
  python lane_inclusion_verifier.py --artifact X --base logs/p1/step10   # a mutation copy
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

BASE = Path("logs/p1/step10")
ARTIFACT = "lane_inclusion.json"
T0 = "t0_baseline.json"
POLICY_CONFIRM = "policy_confirm.json"
QUERIES = "data/eval_queries_v2.json"

ARMS = ("F0", "F0f", "F1", "F2", "F3", "F4")
TREATMENTS = ("F1", "F2", "F3", "F4")
ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20",
                 "precision_at_20", "f1_at_20")
TYPES = ("factual", "multihop", "overview")
TOL = 5e-5          # the metrics are round(..., 4)
CUT = 100           # `reranker_fetch_k` — `_mmr_select` only fires above it

checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


# ── metric re-derivation (mirrors compute_retrieval_metrics' ENDPOINT keys, stdlib) ──────────────

def metrics_from_slots(slots: list, rel: set[int], k: int = 20) -> dict:
    """`slots` = the reranked list's page numbers, None preserved (a page-less candidate consumes a
    POSITION even though it adds no gain — the T4 §15 lesson)."""
    seen: set[int] = set()
    gains = []
    for p in slots:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=ARTIFACT)
    ap.add_argument("--base", default=str(BASE))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--extract", action="store_true")
    args = ap.parse_args()

    base = Path(args.base)
    art = json.loads((base / args.artifact).read_text())
    t0 = json.loads((base / T0).read_text())
    pc = json.loads((base / POLICY_CONFIRM).read_text())
    reach = {int(p) for p in t0["meta"]["coll_pages"]}
    reach_sha = hashlib.sha256(",".join(str(p) for p in sorted(reach)).encode()).hexdigest()[:16]

    rows = art["per_query"]
    ok_rows = [r for r in rows if "error" not in r]
    agg = art["aggregate"]
    deltas = art["deltas"]
    guards = art["guards"]

    # ── V1/V2 — per-query endpoint metrics, re-derived from the RAW slots ────────────────────────
    v1_bad, v2_bad = [], []
    for r in ok_rows:
        rel = {int(p) for p in r["relevant_pages"]}
        for arm in ARMS:
            want = metrics_from_slots(r[f"{arm}_slots"], rel)
            got = r[f"{arm}_metrics"]
            for k, w in want.items():
                if not close(got.get(k), w):
                    v1_bad.append(f"{r['id']}/{arm}/{k}: {got.get(k)} != {w}")
            if not close(got.get("mrr_at_20"), mrr_from_pages(r[f"{arm}_pages"], rel)):
                v2_bad.append(f"{r['id']}/{arm}: {got.get('mrr_at_20')} != "
                              f"{mrr_from_pages(r[f'{arm}_pages'], rel)}")
    check("V1 per-query endpoint metrics re-derived from the slots", not v1_bad,
          f"{len(v1_bad)} mismatches" + (f" e.g. {v1_bad[:3]}" if v1_bad else ""))
    check("V2 mrr_at_20 re-derived from the page list", not v2_bad,
          f"{len(v2_bad)} mismatches" + (f" e.g. {v2_bad[:3]}" if v2_bad else ""))

    # ── V3/V4 — coverage, from the pages and the reachable set ──────────────────────────────────
    v3_bad, v4_bad = [], []
    for r in ok_rows:
        rq = {int(p) for p in r["relevant_pages"]} & reach
        for arm in ARMS:
            if not close(r.get(f"{arm}_cov"),
                         len(set(r[f"{arm}_pages"]) & rq) / len(rq) if rq else None):
                v3_bad.append(f"{r['id']}/{arm}")
            if not close(r.get(f"{arm}_pool_cov"),
                         len(set(r[f"{arm}_pool_pages"]) & rq) / len(rq) if rq else None):
                v4_bad.append(f"{r['id']}/{arm}")
    check("V3 endpoint coverage re-derived", not v3_bad, f"{len(v3_bad)} mismatches {v3_bad[:3]}")
    check("V4 pool coverage re-derived from pool_pages", not v4_bad,
          f"{len(v4_bad)} mismatches {v4_bad[:3]}")

    # ── V5 — aggregates, overall and per type ───────────────────────────────────────────────────
    v5_bad = []
    for arm in ARMS:
        for scope, sub in [("overall", ok_rows)] + [(qt, [r for r in ok_rows
                                                          if r["query_type"] == qt]) for qt in TYPES]:
            a = agg[arm]["overall"] if scope == "overall" else agg[arm]["by_type"][scope]
            for key in ("coverage_reachable", "pool_cov") + ENDPOINT_KEYS:
                col = {"coverage_reachable": f"{arm}_cov", "pool_cov": f"{arm}_pool_cov"}.get(
                    key, f"{arm}_metrics")
                vals = ([r[col] for r in sub] if col.endswith(("_cov",))
                        else [r[col].get(key) for r in sub])
                if not close(a.get(key), mean(vals)):
                    v5_bad.append(f"{arm}/{scope}/{key}: {a.get(key)} != {mean(vals)}")
    check("V5 aggregates re-derived (overall + by type)", not v5_bad,
          f"{len(v5_bad)} mismatches" + (f" e.g. {v5_bad[:3]}" if v5_bad else ""))

    # ── V6 — every paired delta and its CI ──────────────────────────────────────────────────────
    v6_bad = []
    for arm in TREATMENTS:
        for other in ("F0f", "F0"):
            want = {k: ci([r[f"{arm}_metrics"][k] - r[f"{other}_metrics"][k] for r in ok_rows
                           if r[f"{arm}_metrics"].get(k) is not None
                           and r[f"{other}_metrics"].get(k) is not None])
                    for k in ENDPOINT_KEYS}
            got = deltas[f"{arm}_minus_{other}"]
            for k in ENDPOINT_KEYS:
                if not close(got[k].get("mean"), want[k]["mean"]):
                    v6_bad.append(f"{arm}-{other}/{k}: {got[k].get('mean')} != {want[k]['mean']}")
                g, w = got[k].get("ci95"), want[k]["ci95"]
                if (g is None) != (w is None) or (g is not None
                                                  and any(not close(x, y) for x, y in zip(g, w))):
                    v6_bad.append(f"{arm}-{other}/{k}/ci95: {g} != {w}")
    check("V6 paired deltas + CIs re-derived", not v6_bad,
          f"{len(v6_bad)} mismatches" + (f" e.g. {v6_bad[:3]}" if v6_bad else ""))

    # ── V7 — the run-integrity guards, re-derived from the raw rows ─────────────────────────────
    drops = [f"{r['id']}/{a}" for r in ok_rows for a in ARMS
             if (r.get(f"{a}_lane_drops") or {}).get("colbert")]
    rdrops = [f"{r['id']}/{a}" for r in ok_rows for a in ARMS
              if (r.get(f"{a}_lane_drops") or {}).get("raptor")]
    falls = [f"{r['id']}/{a}" for r in ok_rows for a in ARMS if r.get(f"{a}_reranker_fallback")]
    g1 = len(ok_rows) == art["meta"]["n_queries"] == len(rows) and not art["errors"]
    g4 = not falls
    g5 = (sum(r["F1_contrib"]["da"] for r in ok_rows) > 0
          and sum(r["F2_contrib"]["graph"] for r in ok_rows) > 0
          and sum(r["F3_contrib"]["raptor"] for r in ok_rows) > 0
          and sum(r["F3_contrib"]["raptor"] for r in ok_rows
                  if r["query_type"] == "overview") > 0)
    g6 = not drops
    g6b = not rdrops
    g7 = art["meta"]["reachable_pages_set_sha"] == reach_sha == t0["meta"].get(
        "reachable_pages_set_sha", t0["meta"].get("coll_pages_sha", reach_sha))
    for name, want, got in (("G1", g1, guards.get("G1_133_queries_0_errors")),
                            ("G4", g4, guards.get("G4_no_reranker_fallback_in_any_arm")),
                            ("G5", g5, guards.get("G5_each_treatment_lane_contributed_candidates")),
                            ("G6", g6, guards.get("G6_no_colbert_lane_dropout_in_accepted_calls")),
                            ("G6b", g6b, guards.get("G6b_no_raptor_lane_dropout_in_accepted_calls")),
                            ("G7", g7, guards.get("G7_reachable_set_matches_T0"))):
        check(f"V7 {name} re-derived", bool(got) is bool(want),
              f"artifact={got} re-derived={want}")

    # ── V8 — G2, the anchor: F0 vs the shipped product run, per type, re-derived ────────────────
    pc_rows = {r["id"]: r for r in pc["per_query"] if "pages" in r}
    v8_bad = []
    for qt in ("factual", "multihop"):
        sub = [r for r in ok_rows if r["query_type"] == qt]
        for k in ENDPOINT_KEYS:
            mine = mean([r["F0_metrics"].get(k) for r in sub])
            theirs = mean([metrics_from_slots([int(p) for p in pc_rows[r["id"]]["pages"]],
                                              {int(p) for p in r["relevant_pages"]}).get(k)
                           if k != "mrr_at_20" else
                           mrr_from_pages([int(p) for p in pc_rows[r["id"]]["pages"]],
                                          {int(p) for p in r["relevant_pages"]})
                           for r in sub if r["id"] in pc_rows])
            if not close(mine, theirs, 1e-4):
                v8_bad.append(f"{qt}/{k}: {mine} != {theirs}")
    check("V8 G2 anchor re-derived (factual + multihop, per type)", not v8_bad,
          f"{len(v8_bad)} mismatches" + (f" e.g. {v8_bad[:3]}" if v8_bad else ""))

    # ── V9 — G3, the superset property, re-derived (graph-free arms, cut-aware) ─────────────────
    v9_bad, cut = [], []
    for r in ok_rows:
        if any((r.get(f"{a}_pool_size") or 0) >= CUT for a in ARMS):
            cut.append(r["id"])
            continue
        base_pages = set(r["F0f_pool_pages"])
        for arm in ("F1", "F3"):
            if not base_pages <= set(r[f"{arm}_pool_pages"]):
                v9_bad.append(f"{r['id']}/{arm}")
    check("V9 G3 superset re-derived (F1/F3, cut-aware)", not v9_bad,
          f"{len(v9_bad)} violations {v9_bad[:3]}; cut-affected queries: {len(cut)}")
    check("V9b the artifact's G3 flag matches the re-derivation",
          bool(guards.get("G3_F0f_subset_each_treatment_pool")) is (not v9_bad),
          f"artifact={guards.get('G3_F0f_subset_each_treatment_pool')} re-derived={not v9_bad}")

    # ── V10 — the pool sha is the sha of the pool's page list ──────────────────────────────────
    v10_bad = []
    for r in ok_rows:
        for arm in ARMS:
            sha = hashlib.sha256(",".join(map(str, r[f"{arm}_pool_pages"])).encode()).hexdigest()[:16]
            if sha != r[f"{arm}_pool_sha"]:
                v10_bad.append(f"{r['id']}/{arm}")
    check("V10 pool_sha matches the pool page list", not v10_bad, f"{len(v10_bad)} mismatches")

    # ── V11 — shape: 133 rows, unique ids, every arm present, no error rows ────────────────────
    ids = [r["id"] for r in rows]
    v11_bad = []
    if len(rows) != art["meta"]["n_queries"]:
        v11_bad.append(f"per_query n={len(rows)} != meta.n_queries={art['meta']['n_queries']}")
    if args.artifact == ARTIFACT and art["meta"]["n_queries"] != 133:
        v11_bad.append(f"the registered run must carry 133 queries, not {art['meta']['n_queries']}")
    if len(set(ids)) != len(ids):
        v11_bad.append("duplicate ids")
    for r in rows:
        for arm in ARMS:
            for suffix in ("_pages", "_slots", "_pool_pages", "_metrics", "_contrib"):
                if f"{arm}{suffix}" not in r:
                    v11_bad.append(f"{r['id']} missing {arm}{suffix}")
    check("V11 shape: 133 rows, unique ids, all arms present", not v11_bad,
          f"{len(v11_bad)} problems {v11_bad[:3]}")

    # ── V12 — the page-less slot counts (the RAPTOR displacement channel, §11b) ────────────────
    v12_bad = []
    for r in ok_rows:
        for arm in ARMS:
            if r[f"{arm}_endp_pageless"] != sum(1 for p in r[f"{arm}_slots"] if p is None):
                v12_bad.append(f"{r['id']}/{arm}")
    check("V12 endp_pageless matches the slots' None count", not v12_bad, f"{len(v12_bad)} rows")

    # ── V13 — the RAPTOR lane is gated to overview, re-derived ─────────────────────────────────
    v13_bad = [r["id"] for r in ok_rows
               if r["query_type"] != "overview" and r["F3_contrib"]["raptor"] > 0]
    check("V13 F3's RAPTOR lane fires on overview only", not v13_bad, f"{v13_bad[:3]}")

    n_pass = sum(1 for _, ok, _ in checks if ok)
    print("=== lane-inclusion independent verifier (stdlib, artifact-only) ===")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"\n{len(checks)} checks, {n_pass} passed")
    print("ALL PASS" if n_pass == len(checks) else "FAILED")

    if args.extract:
        pack = {
            "artifact_sha256": hashlib.sha256((base / args.artifact).read_bytes()).hexdigest(),
            "meta": art["meta"],
            "aggregate": agg,
            "deltas": deltas,
            "guards": guards,
            "guard_detail": {k: v for k, v in art.get("guard_detail", {}).items()
                             if k != "G2_policy_confirm_aggregate_by_type"},
            "verifier": {n: ok for n, ok, _ in checks},
            "per_query_slim": [{k: v for k, v in r.items()
                                if k.endswith(("_pages", "_cov", "_pool_size", "_contrib",
                                               "_endp_pageless", "_pool_pageless",
                                               "_reranker_fallback", "_lane_drops"))}
                               for r in rows],
        }
        (base / "lane_inclusion_verifier_extract.json").write_text(json.dumps(pack, indent=2))
        print(f"extract: {base / 'lane_inclusion_verifier_extract.json'}")

    return 0 if n_pass == len(checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
