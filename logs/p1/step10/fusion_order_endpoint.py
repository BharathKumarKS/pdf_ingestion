"""§I99 / the fusion-order run — THE POOL'S ORDER: which mechanism produces `waste_order`, and does
changing it move the endpoint's top-20, per type?

Pre-registration: `.hermes/plans/2026-10-30-p1-fusion-order-preregistration.md` (§1–§10, committed
ALONE as `e8dda1a` per D6.1) **as AMENDED by §11** (committed ALONE as `c65e4a6`, before this run).
Implements §2/§4/§5 and nothing else.

THE QUESTION (§1). §I99 decomposes the endpoint's top-20 loss per type and finds it is NOT the pool's
coverage (0.1734) and NOT the cross-encoder (0.0050) — it is the pool's ORDER (0.1791 overall, 0.1652
for overview against a `waste_pool` of only 0.0236). No run has ever contrasted the pool's own ORDER:
§I92 tested the cap and MMR on COVERAGE, §I67 the width on COVERAGE, T4 the cross-encoder's query
text, §I98 lane placement.

THE ARMS (§2 + §11b). Every arm uses TODAY'S WIRING (`lanes=None`) so the only variation is the
mechanism under test:
  O0  — the product's order.                                    the reference; anchored (§4 G2)
  O0w — O0 with `lane_weights={}`.                              a GUARD ARM, not a treatment (§11b)
  O1  — `mmr_enabled=False`.                                    order-only; MMR's ORDER effect
  O2  — `colbert_enabled=False`.                                level-1 dilution, first step
  O3  — `colbert_enabled=False` + `splade_enabled=False`.       the dilution limit case: dense only
  O4  — `lane_weights={"dense":1.0,"sparse":0.5,"colbert":0.5}` dilution WITHOUT removing candidates

⚠️ §11b — `O0w` must be BIT-IDENTICAL to `O0` on every query. It is the live proof that the O4 code
change (`_qdrant_search(lane_weights=…)`) is inert by default; a mismatch VOIDs the run, because it
would make every O4 number uninterpretable.

⚠️ §11a — G2 anchors on `lane_inclusion.json`'s arm F0 (same index, same day, same code path), NOT on
T4's arm C, which predates the shipped per-type rerank policy.

READ-ONLY. No writes to any collection, no re-ingest, no re-embed. HyDE ON and frozen (a miss RAISES).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import socket
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
from loguru import logger

from src.core.config import get_settings
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for
from src.pdf_ingestion.reranker import get_reranker
from src.pdf_ingestion.store import DocumentStore

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from evaluate_rag import compute_retrieval_metrics, run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
LANE_ARTIFACT = "logs/p1/step10/lane_inclusion.json"      # §11a — the corrected G2 anchor
POLICY_CONFIRM = "logs/p1/step10/policy_confirm.json"     # reported, not asserted
BASE = Path("logs/p1/step10")
ANCHOR_TOL = 1e-4

# arm -> (cfg overrides, lane_weights)
ARM_SPEC: dict[str, dict] = {
    "O0":  {},
    "O0w": {"lane_weights": {}},
    "O1":  {"mmr_enabled": False},
    "O2":  {"colbert_enabled": False},
    "O3":  {"colbert_enabled": False, "splade_enabled": False},
    "O4":  {"lane_weights": {"dense": 1.0, "sparse": 0.5, "colbert": 0.5}},
}
TREATMENTS = ("O1", "O2", "O3", "O4")
GUARD_ARMS = ("O0w",)
CFG_KEYS = ("mmr_enabled", "colbert_enabled", "splade_enabled")

ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20",
                 "precision_at_20", "f1_at_20")
TYPES = ("factual", "multihop", "overview")

socket.setdefaulttimeout(90)
RETRIES = 3
LANE_RETRIES = 3

_COLBERT_DROP: dict[str, int] = {"n": 0}


def _install_colbert_watch() -> None:
    """Count ColBERT query failures — the store swallows them and fuses from a REDUCED lane set."""
    from src.pdf_ingestion import colbert_embedder as ce

    for cls in (ce.StubColBERTEmbedder, ce.ClusterColBERTEmbedder, ce.FastembedColBERTEmbedder):
        orig = cls.embed_query

        def wrap(self, text, _o=orig):
            try:
                return _o(self, text)
            except Exception:
                _COLBERT_DROP["n"] += 1
                raise

        cls.embed_query = wrap


def _load_queries() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _reachable_pages(store, cfg) -> set[int]:
    """T0's `coll_pages`: every in-window content page the product filter can reach (read-only)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    flt = Filter(must_not=must_not)

    pages: set[int] = set()
    offset = None
    while True:
        recs, offset = store._qdrant.scroll(
            collection_name=cfg.qdrant_collection, scroll_filter=flt,
            limit=1000, offset=offset, with_payload=["page_number"], with_vectors=False)
        for r in recs:
            p = (r.payload or {}).get("page_number")
            if p is not None:
                pages.add(int(p))
        if offset is None:
            break
    return pages


def _pages_of(hits) -> list[int]:
    seen, out = set(), []
    for h in hits:
        p = h.get("page_number")
        if p is None:
            continue
        p = int(p)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _retry(fn, *a, **kw):
    last = None
    for attempt in range(RETRIES):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("attempt {}/{} failed: {}", attempt + 1, RETRIES, exc)
            if attempt + 1 < RETRIES:
                time.sleep(5)
    raise last


def _cov(pages, reach: set[int]):
    if not reach:
        return None
    return len(set(pages) & reach) / len(reach)


def _endpoint_mrr(pages: list[int], rel: set[int]) -> float:
    for rank, p in enumerate(pages, start=1):
        if p in rel:
            return round(1.0 / rank, 4)
    return 0.0


def _metrics_from_pages(pages: list[int], rel: list[int], cfg) -> dict:
    synth = [{"page_number": p} for p in pages]
    m = compute_retrieval_metrics({"hits": synth, "hits_above": synth, "reranked": synth}, rel, cfg)
    m["mrr_at_20"] = _endpoint_mrr(pages, set(rel))
    return m


def _ci(deltas: list[float]) -> dict:
    n = len(deltas)
    if n < 2:
        return {"n": n, "mean": float(statistics.mean(deltas)) if deltas else None,
                "sd": None, "ci95": None}
    m = float(statistics.mean(deltas))
    sd = float(statistics.stdev(deltas))
    half = float(1.96 * sd / math.sqrt(n))
    return {"n": n, "mean": m, "sd": sd, "ci95": [m - half, m + half]}


def _f(x):
    return None if x is None else float(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default=str(BASE / "fusion_order.json"))
    args = ap.parse_args()

    cfg = get_settings()
    if not (cfg.da_enabled and cfg.hyde_enabled):
        logger.error("da_enabled/hyde_enabled must be True — the registered config")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    _install_colbert_watch()

    queries = _load_queries()
    if args.ids:
        want = {s.strip() for s in args.ids.split(",") if s.strip()}
        queries = [q for q in queries if q["id"] in want]
    if args.limit:
        queries = queries[: args.limit]

    cache = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map: dict[str, str] = {}
    for q in queries:
        if q.get("query_type") in ("factual", "overview"):
            prompt_map[prompt_for(q["query"])] = cache.get(q["id"])

    import src.core.llm as llm_mod
    _real_call_llm = llm_mod.call_llm

    def _frozen_llm(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        raise RuntimeError(f"HyDE cache miss mid-run for prompt {str(prompt)[:90]!r} (§4)")

    llm_mod.call_llm = _frozen_llm

    reach = _reachable_pages(store, cfg)
    logger.info("reachable content pages: {} (T0 recorded 888)", len(reach))

    baseline_cfg = {k: getattr(cfg, k) for k in CFG_KEYS}
    logger.info("arm cfg baseline: {}", baseline_cfg)

    per_query: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()
    try:
        for i, q in enumerate(queries, 1):
            qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
            rel = {int(p) for p in q["relevant_pages"]}
            rq = rel & reach
            rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel),
                         "n_reachable": len(rq), "relevant_pages": sorted(rel)}
            try:
                for arm, spec in ARM_SPEC.items():
                    for k in CFG_KEYS:                      # apply the arm's cfg overrides
                        setattr(cfg, k, spec.get(k, baseline_cfg[k]))
                    lane_weights = spec.get("lane_weights")

                    def _call():
                        retries, drops = 0, {}
                        while True:
                            before = {"colbert": _COLBERT_DROP["n"], "da": store.da_dropouts,
                                      "raptor": store.raptor_dropouts,
                                      "mmr": store.mmr_selections}
                            r = _retry(run_retrieval, text, store, embedder, reranker, cfg, "global",
                                       0.0, query_type=qtype, lanes=None,
                                       lane_weights=lane_weights)
                            after = {"colbert": _COLBERT_DROP["n"], "da": store.da_dropouts,
                                     "raptor": store.raptor_dropouts,
                                     "mmr": store.mmr_selections}
                            drops = {k: after[k] - before[k] for k in before}
                            # MMR firing is a MECHANISM, not a dropout — retry only on real drops.
                            lane_drops = {k: v for k, v in drops.items() if k != "mmr"}
                            if not any(lane_drops.values()) or retries >= LANE_RETRIES:
                                return r, drops, retries
                            retries += 1
                            logger.warning("[{}] arm {}: lane dropout {} — retry {}/{}",
                                           qid, arm, lane_drops, retries, LANE_RETRIES)

                    fb_before = getattr(reranker, "fallbacks", 0)
                    ret, drops, lane_retries = _call()
                    fb = getattr(reranker, "fallbacks", 0) > fb_before

                    pool = ret["hits"]
                    endp = ret["reranked"]
                    pages = _pages_of(endp)
                    pool_pages = _pages_of(pool)
                    rec[f"{arm}_pages"] = pages
                    rec[f"{arm}_pool_pages"] = pool_pages
                    rec[f"{arm}_slots_n"] = len(endp)
                    rec[f"{arm}_pool_slots_n"] = len(pool)
                    rec[f"{arm}_endp_pageless"] = sum(1 for h in endp
                                                      if h.get("page_number") is None)
                    rec[f"{arm}_pool_size"] = len(pool_pages)
                    rec[f"{arm}_pool_sha"] = hashlib.sha256(
                        ",".join(map(str, pool_pages)).encode()).hexdigest()[:16]
                    rec[f"{arm}_pool_cov"] = _cov(pool_pages, rq)
                    rec[f"{arm}_cov"] = _cov(pages, rq)
                    rec[f"{arm}_lane_drops"] = drops
                    rec[f"{arm}_lane_retries"] = lane_retries
                    rec[f"{arm}_mmr_fired"] = bool(drops.get("mmr"))
                    rec[f"{arm}_reranker_fallback"] = fb
                    m = compute_retrieval_metrics(ret, sorted(rel), cfg)
                    m["mrr_at_20"] = _endpoint_mrr(pages, rel)
                    rec[f"{arm}_metrics"] = m
                per_query.append(rec)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
                logger.error("[{}] FAILED: {}", qid, exc)
                per_query.append({**rec, "error": str(exc)})
            finally:
                for k in CFG_KEYS:
                    setattr(cfg, k, baseline_cfg[k])
            if i % 5 == 0:
                logger.info("  {}/{} queries ({:.0f}s)", i, len(queries), time.time() - t0)
    finally:
        llm_mod.call_llm = _real_call_llm
    wall = time.time() - t0

    ok = [r for r in per_query if "error" not in r]

    def agg(arm: str, sub=None):
        rows = sub if sub is not None else ok
        out: dict = {"n": len(rows)}
        covs = [r[f"{arm}_cov"] for r in rows if r.get(f"{arm}_cov") is not None]
        out["coverage_reachable"] = _f(statistics.mean(covs)) if covs else None
        pcovs = [r[f"{arm}_pool_cov"] for r in rows if r.get(f"{arm}_pool_cov") is not None]
        out["pool_cov"] = _f(statistics.mean(pcovs)) if pcovs else None
        out["pool_mean"] = _f(statistics.mean([r[f"{arm}_pool_size"] for r in rows])) if rows else None
        for key in ENDPOINT_KEYS:
            vals = [r[f"{arm}_metrics"][key] for r in rows
                    if r.get(f"{arm}_metrics") and r[f"{arm}_metrics"].get(key) is not None]
            out[key] = _f(statistics.mean(vals)) if vals else None
        out["precision_ceiling_at_20"] = _f(statistics.mean(
            [r[f"{arm}_metrics"]["precision_ceiling_at_20"] for r in rows
             if r.get(f"{arm}_metrics")])) if rows else None
        out["mmr_fired_n"] = sum(1 for r in rows if r.get(f"{arm}_mmr_fired"))
        return out

    aggregate = {arm: {"overall": agg(arm),
                       "by_type": {qt: agg(arm, [r for r in ok if r["query_type"] == qt])
                                   for qt in TYPES}}
                 for arm in ARM_SPEC}

    def delta(a_arm: str, b_arm: str, key: str, sub=None) -> dict:
        rows = sub if sub is not None else ok
        d = [(r[f"{b_arm}_metrics"][key] - r[f"{a_arm}_metrics"][key]) for r in rows
             if r.get(f"{a_arm}_metrics") and r.get(f"{b_arm}_metrics")
             and r[f"{a_arm}_metrics"].get(key) is not None
             and r[f"{b_arm}_metrics"].get(key) is not None]
        return _ci(d)

    deltas: dict = {}
    for arm in TREATMENTS:
        deltas[f"{arm}_minus_O0"] = {k: delta("O0", arm, k) for k in ENDPOINT_KEYS}
        deltas[f"{arm}_minus_O0_by_type"] = {
            qt: {k: delta("O0", arm, k, [r for r in ok if r["query_type"] == qt])
                 for k in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20")}
            for qt in TYPES}
    deltas["cov_O3_minus_O0"] = _ci([(r["O3_cov"] - r["O0_cov"]) for r in ok
                                     if r.get("O3_cov") is not None and r.get("O0_cov") is not None])
    deltas["cov_O2_minus_O0"] = _ci([(r["O2_cov"] - r["O0_cov"]) for r in ok
                                     if r.get("O2_cov") is not None and r.get("O0_cov") is not None])
    deltas["cov_O4_minus_O0"] = _ci([(r["O4_cov"] - r["O0_cov"]) for r in ok
                                     if r.get("O4_cov") is not None and r.get("O0_cov") is not None])

    # ── guards ───────────────────────────────────────────────────────────────────────────────
    guards: dict = {}
    detail: dict = {}

    # G6 — 133 queries, 0 errors
    guards["G6_133_queries_0_errors"] = (len(queries) == 133 and not errors)
    detail["G6"] = {"queries": len(queries), "errors": errors}

    # G1 — lane health per query, every arm
    bad = [(r["id"], a, r[f"{a}_lane_drops"])
           for r in ok for a in ARM_SPEC
           if any(v for k, v in (r.get(f"{a}_lane_drops") or {}).items() if k != "mmr")]
    guards["G1_no_lane_dropout_survived"] = not bad
    detail["G1"] = {"queries_with_a_surviving_drop": bad[:20], "n": len(bad)}

    # G2 (§11a) — O0 reproduces lane_inclusion's arm F0, per type
    lane = json.loads(Path(LANE_ARTIFACT).read_text())["aggregate"]["F0"]
    g2: dict = {}
    for qt in ("overall",) + TYPES:
        ref = lane["overall"] if qt == "overall" else lane["by_type"][qt]
        got = aggregate["O0"]["overall"] if qt == "overall" else aggregate["O0"]["by_type"][qt]
        gaps = {k: abs((got.get(k) or 0) - (ref.get(k) or 0))
                for k in ENDPOINT_KEYS + ("coverage_reachable", "pool_cov")}
        g2[qt] = {"max_gap": max(gaps.values()), "gaps": gaps}
    guards["G2_O0_reproduces_the_shipped_product"] = all(
        v["max_gap"] <= ANCHOR_TOL for v in g2.values())
    detail["G2"] = g2

    # G3 (§11 + §11c) — O1's page SET is identical to O0's on the queries MMR did NOT fire on.
    # ⚠️ CORRECTED AFTER THE FIRST RUN (see IMPROVEMENTS.md §I100): `mmr_fired` must be read from the
    # **O0** call. O1 has MMR DISABLED, so its own flag is False on every query — the first version
    # asserted set-equality on all 133, including the 16 where O0's MMR actually fired.
    fired = {r["id"] for r in ok if r.get("O0_mmr_fired")}
    mmr_off = [r for r in ok if r["id"] not in fired]
    set_mismatch = [r["id"] for r in mmr_off
                    if set(r["O1_pool_pages"]) != set(r["O0_pool_pages"])]
    differs = {r["id"] for r in ok if set(r["O1_pool_pages"]) != set(r["O0_pool_pages"])}
    guards["G3_O1_membership_identical_where_mmr_did_not_fire"] = not set_mismatch
    guards["G3b_O1_differs_exactly_where_O0_MMR_fired"] = (differs == fired)
    detail["G3"] = {"queries_mmr_did_not_fire": len(mmr_off),
                    "queries_mmr_fired": len(fired),
                    "set_mismatches": set_mismatch[:20], "n_mismatch": len(set_mismatch)}

    # G4 — no reranker fallback
    fb = [(r["id"], a) for r in ok for a in ARM_SPEC if r.get(f"{a}_reranker_fallback")]
    guards["G4_no_reranker_fallback"] = not fb
    detail["G4"] = {"n": len(fb), "first": fb[:10]}

    # G5 — the arm's mechanism actually engaged
    # G5 — the arm's mechanism actually engaged.
    # ⚠️ CORRECTED AFTER THE FIRST RUN (§I100): the first version also asserted
    # `O4_pool_set_identical_to_O0_everywhere`. That is an INVARIANCE claim, not a mechanism check, and
    # it is FALSE by construction — O4 reorders the LEVEL-1 fusion, which is truncated to `limit`, so
    # the surviving candidate set changes. It is now REPORTED, not asserted.
    mech = {
        "O1_mmr_fired_on_every_query_is_false": all(not r.get("O1_mmr_fired") for r in ok),
        "O2_pool_set_differs_from_O0_somewhere": any(
            set(r["O2_pool_pages"]) != set(r["O0_pool_pages"]) for r in ok),
        "O3_pool_set_differs_from_O0_somewhere": any(
            set(r["O3_pool_pages"]) != set(r["O0_pool_pages"]) for r in ok),
        "O4_pool_order_differs_from_O0_somewhere": any(
            r["O4_pool_pages"] != r["O0_pool_pages"] for r in ok),
    }
    guards["G5_each_mechanism_engaged"] = all(mech.values())
    detail["G5"] = {**mech, "O4_pool_set_identical_to_O0_n_queries": sum(
        1 for r in ok if set(r["O4_pool_pages"]) == set(r["O0_pool_pages"]))}

    # G7 (§11b) — the GUARD ARM: O0w is bit-identical to O0 on every query
    w_bad = [r["id"] for r in ok
             if r["O0w_pool_sha"] != r["O0_pool_sha"] or r["O0w_pages"] != r["O0_pages"]
             or r["O0w_metrics"] != r["O0_metrics"]]
    guards["G7_lane_weights_default_is_inert_in_run"] = not w_bad
    detail["G7"] = {"queries": len(ok), "mismatches": w_bad[:20], "n_mismatch": len(w_bad)}

    res = {
        "meta": {
            "question": "which mechanism produces waste_order, and does changing the pool's ORDER "
                        "move the endpoint's top-20, per type? (§I99 / fusion-order pre-registration)",
            "prereg": ".hermes/plans/2026-10-30-p1-fusion-order-preregistration.md (§1-§10 committed "
                      "ALONE as e8dda1a; §11 amendment committed ALONE as c65e4a6)",
            "collection": cfg.qdrant_collection,
            "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model,
            "dense_dim": cfg.dense_dim,
            "da_enabled": cfg.da_enabled,
            "hyde": "on and frozen",
            "read_only": True,
            "arms": ARM_SPEC,
            "treatments": list(TREATMENTS),
            "guard_arms": list(GUARD_ARMS),
            "cfg_baseline": baseline_cfg,
            "n_queries": len(queries),
            "wall_s": round(wall, 1),
            "reachable_pages": len(reach),
        },
        "guards": guards,
        "guard_detail": detail,
        "aggregate": aggregate,
        "deltas": deltas,
        "errors": errors,
        "per_query": per_query,
    }
    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))

    print(f"\nwrote {out}  ({out.stat().st_size} bytes)  wall {wall:.0f}s")
    print(f"queries {len(queries)}  errors {len(errors)}  reachable pages {len(reach)}")
    print("\nGUARDS")
    for k, v in guards.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print("\nendpoint metrics (overall)")
    hdr = f"{'arm':5s} " + " ".join(f"{k[:11]:>11s}" for k in
                                    ("coverage_reachable", "pool_cov", *ENDPOINT_KEYS))
    print(hdr)
    for arm in ARM_SPEC:
        a = aggregate[arm]["overall"]
        print(f"{arm:5s} " + " ".join(
            f"{(a.get(k) if a.get(k) is not None else float('nan')):11.4f}"
            for k in ("coverage_reachable", "pool_cov", *ENDPOINT_KEYS)))
    return 0 if all(guards.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
