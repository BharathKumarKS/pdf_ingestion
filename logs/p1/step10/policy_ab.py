#!/usr/bin/env python
"""policy_ab.py — the per-type rerank-query policy's before/after, by RE-DERIVATION over T4's artifact.

Pre-registration: `.hermes/plans/2026-10-29-p1-per-type-rerank-query-preregistration.md`
(committed ALONE as `cb2f99f`, amended `faa7621`, both BEFORE this run).

WHY THIS IS A COMPOSITION, NOT A FRESH RUN. T4 (`logs/p1/step10/t4_endpoint.json`) already ran both
arms the policy selects between, on one index and the SAME pool per query (T4 G6/G6b):

  * arm C = the CE fed the PRODUCT query (`hyp` for factual+overview, raw for multihop);
  * arm Q = the CE fed the RAW query for every type.

The policy IS `Q` on factual and `C` on overview and multihop. So the policy's per-query metrics are
EXACTLY `Q_metrics` for factual and `C_metrics` otherwise — both present on all 133 rows.

ARMS
  C         the product (T4's C_metrics)
  P_gold    the policy gated on the GOLD query_type
  P_router  the policy gated on the INTENT ROUTER's classification  (the product-realistic number)

USAGE
  unset PYTHONPATH
  # 1) compute the router's classes over the 133 gold queries (needs the cluster):
  uv run python -u logs/p1/step10/policy_ab.py --router
  # 2) the re-derivation + guards (read-only, offline):
  uv run python -u logs/p1/step10/policy_ab.py
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

T4 = REPO / "logs/p1/step10/t4_endpoint.json"
OUT = REPO / "logs/p1/step10/policy_ab.json"
ROUTER_CACHE = REPO / "logs/p1/step10/policy_router_classes.json"

# Endpoint metrics the policy can move (the change is the CE's INPUT, downstream of the pool).
ENDPOINT_METRICS = ["ndcg_at_20", "map", "mrr_at_20", "recall_at_20",
                    "hit_at_20", "precision_at_20", "f1_at_20"]
Z = 1.96  # the project's pinned 95% CI multiplier (pre-registration §7)


def load_gold_texts() -> dict[str, str]:
    """The SAME 133 gold queries T4 scored: id starts gold-/ovw- AND has relevant_pages."""
    raw = json.loads((REPO / "data/eval_queries_v2.json").read_text())
    return {str(x["id"]): x["query"] for x in raw
            if isinstance(x, dict)
            and str(x.get("id", "")).startswith(("gold-", "ovw-"))
            and (x.get("relevant_pages") or [])}


# ── the router pass ──────────────────────────────────────────────────────────

def compute_router_classes() -> dict[str, str]:
    """Embed the 133 gold queries with the dense-lane embedder and classify each via IntentRouter."""
    from src.core.config import get_settings
    from src.core.intent_router import IntentRouter
    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder

    cfg = get_settings()
    assert not cfg.use_stub_embedder, "the router needs the REAL embedder (set USE_STUB_EMBEDDER=false)"
    router = IntentRouter(settings=cfg)
    assert router._clf is not None, (
        f"the trained classifier did not load from {cfg.intent_classifier_path} — "
        "P_router would silently fall back to prototype mode")
    emb = ClusterDenseEmbedder(settings=cfg)
    gold = load_gold_texts()
    out: dict[str, str] = {}
    for i, (qid, text) in enumerate(sorted(gold.items()), 1):
        vec = emb.embed_query(text)
        out[qid] = router.classify(vec).value
        if i % 25 == 0:
            print(f"  router: {i}/{len(gold)}", flush=True)
    print(f"  router: {len(out)}/{len(gold)} classified", flush=True)
    return out


def load_router_classes() -> dict[str, str]:
    if not ROUTER_CACHE.exists():
        raise SystemExit(f"router cache missing: {ROUTER_CACHE} — run with --router first")
    return json.loads(ROUTER_CACHE.read_text())["classes"]


# ── arm construction ─────────────────────────────────────────────────────────

def _arm_of_row(row: dict, which: str) -> dict:
    """The metric dict + endpoint coverage for one arm on one row."""
    src = "Q" if which == "Q" else "C"
    return {
        "src": src,
        "metrics": {k: row[f"{src}_metrics"][k] for k in ENDPOINT_METRICS},
        "coverage": row[f"{src}_cov"],
        "pool_size": row[f"{src}_pool_size"],
        "pool_sha": row[f"{src}_pool_sha"],
        "pages": row[f"{src}_pages"],
    }


def build_arms(rows: list[dict], router: dict[str, str]) -> list[dict]:
    out = []
    for r in rows:
        qt = r["query_type"]
        gold_sel = "Q" if qt == "factual" else "C"
        rc = router.get(r["id"])
        if rc is None:
            raise SystemExit(f"router class missing for {r['id']}")
        router_sel = "Q" if rc == "factual" else "C"
        out.append({
            "id": r["id"],
            "query_type": qt,
            "n_relevant": r["n_relevant"],
            "n_reachable": r["n_reachable"],
            "router_class": rc,
            "selection_gold": gold_sel,
            "selection_router": router_sel,
            "C": _arm_of_row(r, "C"),
            "P_gold": _arm_of_row(r, gold_sel),
            "P_router": _arm_of_row(r, router_sel),
        })
    return out


# ── statistics ───────────────────────────────────────────────────────────────

def _mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else float("nan")


def aggregate(rows: list[dict], arm: str) -> dict:
    def block(rs: list[dict]) -> dict:
        d: dict = {"n": len(rs)}
        for k in ENDPOINT_METRICS:
            d[k] = round(_mean([r[arm]["metrics"][k] for r in rs]), 6)
        d["coverage_reachable"] = round(_mean([r[arm]["coverage"] for r in rs]), 6)
        return d
    types = sorted({r["query_type"] for r in rows})
    return {"overall": block(rows),
            "by_type": {t: block([r for r in rows if r["query_type"] == t]) for t in types}}


def paired_delta(rows: list[dict], arm: str, base: str = "C") -> dict:
    """mean ± 1.96·SD/√n over the per-query differences, per metric, overall and per type."""
    def block(rs: list[dict]) -> dict:
        d: dict = {"n": len(rs)}
        for k in ENDPOINT_METRICS:
            diffs = [r[arm]["metrics"][k] - r[base]["metrics"][k] for r in rs]
            m = _mean(diffs)
            sd = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
            half = Z * sd / np.sqrt(len(diffs)) if len(diffs) else 0.0
            d[k] = {
                "mean": round(m, 6),
                "sd": round(sd, 6),
                "ci95": [round(m - half, 6), round(m + half, 6)],
                "resolved": bool(len(diffs) > 1 and (m - half) * (m + half) > 0),
                "wlt": [sum(1 for x in diffs if x > 0), sum(1 for x in diffs if x < 0),
                        sum(1 for x in diffs if x == 0)],
            }
        d["coverage_reachable"] = {
            "mean": round(_mean([r[arm]["coverage"] - r[base]["coverage"] for r in rs]), 6)}
        return d
    types = sorted({r["query_type"] for r in rows})
    return {"overall": block(rows),
            "by_type": {t: block([r for r in rows if r["query_type"] == t]) for t in types}}


# ── guards ───────────────────────────────────────────────────────────────────

def t4_metrics(raw_row: dict, src: str) -> dict:
    return {k: raw_row[f"{src}_metrics"][k] for k in ENDPOINT_METRICS}


def run_guards(rows: list[dict], t4: dict, router: dict[str, str],
               raw_by_id: dict[str, dict]) -> tuple[dict, dict]:
    g: dict[str, bool] = {}
    detail: dict[str, str] = {}

    # G1 — the composition is wired correctly, exactly.
    bad = [r["id"] for r in rows
           if r["P_gold"]["metrics"] != t4_metrics(
               raw_by_id[r["id"]], "Q" if r["query_type"] == "factual" else "C")]
    g["G1_composition_wired_exactly"] = not bad
    detail["G1"] = f"{len(rows) - len(bad)}/{len(rows)} rows select the right arm's metrics"

    # G2 — multihop policy ≡ C exactly (HyDE unused there).
    mh = [r for r in rows if r["query_type"] == "multihop"]
    g["G2_multihop_policy_equals_C"] = all(
        r["P_gold"]["metrics"] == r["C"]["metrics"] and r["P_gold"]["coverage"] == r["C"]["coverage"]
        for r in mh)
    detail["G2"] = f"{len(mh)} multihop rows, all metrics identical to C"

    # G3a — the POOL is identical per query (the real VOID condition).
    g["G3a_pool_identical_per_query"] = all(
        r["C"]["pool_size"] == r["P_gold"]["pool_size"]
        and r["C"]["pool_sha"] == r["P_gold"]["pool_sha"]
        and r["C"]["pool_sha"] == r["P_router"]["pool_sha"] for r in rows)
    detail["G3a"] = "pool size + sha equal across C / P_gold / P_router on every row"

    # G3b — exact equality where the policy IS C (overview + multihop), every metric.
    other = [r for r in rows if r["query_type"] in ("overview", "multihop")]
    g["G3b_policy_equals_C_where_unchanged"] = all(
        r["P_gold"]["metrics"] == r["C"]["metrics"] for r in other)
    detail["G3b"] = f"{len(other)} overview+multihop rows identical to C"

    # G4 — P_router uses the ROUTER's output.
    g["G4_router_arm_uses_router_output"] = all(
        r["selection_router"] == ("Q" if router[r["id"]] == "factual" else "C") for r in rows)
    detail["G4"] = "every router-arm selection reproduces the router's own predicted class"

    # G5 — the re-derivation models the SHIPPED code: the artifact's arm metadata must say which
    #      CE query text each arm used.  A mismatch here means the composition is labelled wrong.
    meta_arms = t4["meta"]["arms"]
    g["G5_arm_query_texts_match_the_code"] = (
        meta_arms["C"]["rerank_query"] == "product" and meta_arms["Q"]["rerank_query"] == "raw")
    detail["G5"] = (f"C.rerank_query={meta_arms['C']['rerank_query']!r} "
                    f"Q.rerank_query={meta_arms['Q']['rerank_query']!r}")

    # G6 — 133 rows, 0 errors, both arm dicts present.
    g["G6_133_rows_0_errors_both_arms"] = (
        len(rows) == 133 and not t4.get("errors")
        and all("C_metrics" in r0 and "Q_metrics" in r0 for r0 in t4["per_query"]))
    detail["G6"] = f"{len(rows)} rows, {len(t4.get('errors', []))} errors"

    # G7 — the router arm is not degenerate.
    dist = collections.Counter(router.values())
    g["G7_router_not_degenerate"] = len(dist) > 1
    detail["G7"] = f"router classes over gold: {dict(dist)}"

    return g, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--router", action="store_true",
                    help="compute the router's classes over the gold set (needs the cluster) and cache them")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if args.router:
        classes = compute_router_classes()
        ROUTER_CACHE.write_text(json.dumps({
            "meta": {"model": "intent_classifier.pkl", "n": len(classes)},
            "classes": classes}, indent=1))
        print(f"wrote {ROUTER_CACHE}")
        return 0

    t4 = json.loads(T4.read_text())
    rows_raw = t4["per_query"]
    router = load_router_classes()
    rows = build_arms(rows_raw, router)
    raw_by_id = {r["id"]: r for r in rows_raw}

    guards, detail = run_guards(rows, t4, router, raw_by_id)

    agg = {a: aggregate(rows, a) for a in ("C", "P_gold", "P_router")}
    deltas = {
        "P_gold_minus_C": paired_delta(rows, "P_gold", "C"),
        "P_router_minus_C": paired_delta(rows, "P_router", "C"),
    }

    # G3c — REPORT the R@20/Hit@20 movement on factual (measured, not held).
    fact = [r for r in rows if r["query_type"] == "factual"]
    g3c = {}
    for k in ("recall_at_20", "hit_at_20"):
        diffs = [r["P_gold"]["metrics"][k] - r["C"]["metrics"][k] for r in fact]
        g3c[k] = {"n": len(fact), "mean": round(_mean(diffs), 6),
                  "n_moved": sum(1 for x in diffs if x != 0)}

    sha = hashlib.sha256(json.dumps(rows_raw, sort_keys=True).encode()).hexdigest()
    artifact = {
        "meta": {
            "question": "does the per-type rerank-query policy (raw for factual, hyp for overview) "
                        "recover T4's Q-C effect, and how much survives the router?",
            "prereg": ".hermes/plans/2026-10-29-p1-per-type-rerank-query-preregistration.md",
            "prereg_commits": ["cb2f99f (committed ALONE, D6.1)", "faa7621 (G3 amendment, pre-run)"],
            "source_artifact": "logs/p1/step10/t4_endpoint.json",
            "source_sha256": "3db7c697a5bb0fecc2969e7dd1be6731a4b8dbbb7458de084d0af48792c66bd3",
            "source_per_query_sha256": sha,
            "n": len(rows),
            "endpoint_metrics": ENDPOINT_METRICS,
            "statistic": "mean +/- 1.96*SD/sqrt(n) over per-query differences",
            "note": "a COMPOSITION of T4's arms C and Q; the live confirmation is a separate gate (pre-reg S8)",
        },
        "aggregate": agg,
        "deltas": deltas,
        "g3c_factual_recall_movement": g3c,
        "guards": guards,
        "guard_detail": detail,
        "router_class_distribution": dict(collections.Counter(router.values())),
        "router_vs_gold": {
            "agreement": round(float(np.mean(
                [1.0 if r["router_class"] == r["query_type"] else 0.0 for r in rows])), 4),
            "n": len(rows),
        },
        "per_query": rows,
        "errors": [],
    }

    Path(args.out).write_text(json.dumps(artifact, indent=1))
    print(f"wrote {args.out}")
    print("\n=== GUARDS ===")
    for k, v in guards.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}: {detail.get(k.split('_')[0], '')}")
    ok = all(guards.values())
    print(f"\n{'ALL GUARDS PASS' if ok else 'GUARD FAILURE'}")
    if not ok:
        return 2

    print("\n=== the headline (paired vs C) ===")
    for arm in ("P_gold_minus_C", "P_router_minus_C"):
        o = deltas[arm]["overall"]
        f = deltas[arm]["by_type"]["factual"]
        print(f"  {arm}")
        print(f"    overall  nDCG {o['ndcg_at_20']['mean']:+.4f} {o['ndcg_at_20']['ci95']} "
              f"{'R' if o['ndcg_at_20']['resolved'] else 'ns'} | "
              f"MAP {o['map']['mean']:+.4f} | MRR@20 {o['mrr_at_20']['mean']:+.4f}")
        print(f"    factual  nDCG {f['ndcg_at_20']['mean']:+.4f} {f['ndcg_at_20']['ci95']} "
              f"{'R' if f['ndcg_at_20']['resolved'] else 'ns'} | "
              f"MAP {f['map']['mean']:+.4f} | MRR@20 {f['mrr_at_20']['mean']:+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
