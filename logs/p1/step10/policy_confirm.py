#!/usr/bin/env python
"""policy_confirm.py — the LIVE confirmation of the per-type rerank-query policy (pre-registration §8).

The re-derivation (`policy_ab.py`) proved the EFFECT by composing T4's arms C and Q. This proves the
SHIPPED CODE emits it: with `evaluate_rag.py` changed to the policy (raw query for FACTUAL, the HyDE
hypothetical for OVERVIEW), one product-endpoint pass over the 133 gold queries must reproduce the
composition's per-query endpoint page lists.

GUARDS (each must be able to FAIL)
  L1  the CE was fed the RIGHT query text on every call — the raw question for factual, the
      hypothetical for overview, the raw question for multihop. A watcher records the text at
      `reranker.rerank`; a mismatch on any query fails.
  L2  the endpoint page list equals T4's `Q_pages` on FACTUAL and T4's `C_pages` on OVERVIEW and
      MULTIHOP — exact, per query. This is the whole claim: the shipped code == the composition.
  L3  lane health: no ColBERT lane dropout survived into any accepted call (the §I96 counter).
  L4  no reranker fallback on any query (otherwise the top-k is unranked, §I55).
  L5  133 queries, 0 errors.

Run:  unset PYTHONPATH; uv run python -u logs/p1/step10/policy_confirm.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[2]))
sys.path.insert(0, str(BASE))

import t4_endpoint as T4  # noqa: E402  (reuse its plumbing; it runs nothing on import)
from loguru import logger  # noqa: E402

from scripts.evaluate_rag import run_retrieval  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

OUT = BASE / "policy_confirm.json"

# L1 — the text the CE actually received, per query.
_SEEN_QUERY: dict[str, str | None] = {}


def _install_query_watcher(reranker) -> None:
    orig = reranker.rerank

    def _wrapped(query, chunks, top_k):
        _SEEN_QUERY["text"] = query
        return orig(query, chunks, top_k)

    reranker.rerank = _wrapped


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="smoke: only the first N queries")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    cfg = get_settings()
    if not cfg.da_enabled:
        logger.error("this confirmation needs T0's lane set (DA ON)")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    _install_query_watcher(reranker)

    queries = T4._load_queries()
    if args.limit:
        queries = queries[: args.limit]
    cache = load_hyde(Path(T4.QUERIES), cfg=cfg)
    prompt_map = {prompt_for(q["query"]): cache.get(q["id"]) for q in queries
                  if q.get("query_type") in ("factual", "overview")}

    import src.core.llm as llm_mod
    def _frozen_llm(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        raise RuntimeError(f"HyDE cache miss mid-run for prompt {str(prompt)[:90]!r}")
    llm_mod.call_llm = _frozen_llm

    # T4's recorded endpoint page lists — the composition this must reproduce.
    t4 = json.loads((BASE / "t4_endpoint.json").read_text())
    t4_by_id = {r["id"]: r for r in t4["per_query"]}

    arm_cfg = cfg.model_copy(update={"reranker_enabled": True, "reranker_top_k": 20})
    arm_store = DocumentStore(arm_cfg)

    per_query, errors = [], []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
        rel = {int(p) for p in q["relevant_pages"]}
        rec = {"id": qid, "query_type": qtype, "n_relevant": len(rel)}
        try:
            # ⚠️ A call whose ColBERT lane dropped OR whose cross-encoder FELL BACK is NOT the
            # treatment: the pool is fused from a reduced lane set, or the top-k is the pool
            # UNRANKED (§I55). Retry it (bounded) and record both, exactly as T4 did for the lane.
            retries = 0
            while True:
                cb_before = getattr(arm_store, "colbert_dropouts", 0)
                fb_before = getattr(reranker, "fallbacks", 0)
                _SEEN_QUERY["text"] = None
                ret = T4._retry(run_retrieval, text, arm_store, embedder, reranker, arm_cfg,
                                "global", 0.0, query_type=qtype)
                dropped = getattr(arm_store, "colbert_dropouts", 0) > cb_before
                fellback = getattr(reranker, "fallbacks", 0) > fb_before
                if (not dropped and not fellback) or retries >= 3:
                    break
                retries += 1
                logger.warning("[{}] lane_drop={} ce_fallback={} — retry {}/3",
                               qid, dropped, fellback, retries)
            rec["pages"] = T4._pages_of(ret["reranked"])
            rec["ce_query_text"] = _SEEN_QUERY["text"]
            rec["colbert_drop"] = dropped
            rec["reranker_fallback"] = fellback
            rec["retries"] = retries
            rec["expect_arm"] = "Q" if qtype == "factual" else "C"
            rec["t4_pages"] = t4_by_id[qid][f"{rec['expect_arm']}_pages"]
            rec["pages_match"] = rec["pages"] == rec["t4_pages"]
            # HyDE is only generated for factual/overview (evaluate_rag.py:190) — asking the cache
            # for a multihop query RAISES, so it must be looked up conditionally.
            rec["hyde"] = cache.get(qid) if qtype in ("factual", "overview") else None
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
            errors.append(rec)
        per_query.append(rec)
        if i % 20 == 0:
            logger.info("  {}/{} ({:.0f}s)", i, len(queries), time.time() - t0)

    ok = [r for r in per_query if "error" not in r]

    # ── guards ────────────────────────────────────────────────────────────────
    def expected_text(r) -> str | None:
        if r["query_type"] == "factual":
            return next(q["query"] for q in queries if q["id"] == r["id"])
        if r["query_type"] == "overview":
            return r.get("hyde")
        return next(q["query"] for q in queries if q["id"] == r["id"])

    l1_bad = [r["id"] for r in ok if r.get("ce_query_text") != expected_text(r)]
    l2_bad = [r["id"] for r in ok if not r["pages_match"]]
    l3_bad = [r["id"] for r in ok if r["colbert_drop"]]
    l4_bad = [r["id"] for r in ok if r["reranker_fallback"]]

    guards = {
        "L1_ce_fed_the_right_query_text": not l1_bad,
        "L2_pages_match_the_composition_exactly": not l2_bad,
        "L3_no_colbert_dropout_in_accepted_calls": not l3_bad,
        "L4_no_reranker_fallback": not l4_bad,
        "L5_133_queries_0_errors": len(per_query) == 133 and not errors,
    }
    detail = {
        "L1": f"{len(ok) - len(l1_bad)}/{len(ok)} queries fed the expected CE text"
              + (f"; bad {l1_bad[:5]}" if l1_bad else ""),
        "L2": f"{len(ok) - len(l2_bad)}/{len(ok)} endpoint page lists match T4 exactly"
              + (f"; bad {l2_bad[:5]}" if l2_bad else ""),
        "L3": f"{len(l3_bad)} dropouts",
        "L4": f"{len(l4_bad)} fallbacks",
        "L5": f"{len(per_query)} queries, {len(errors)} errors",
    }

    artifact = {
        "meta": {
            "question": "does the SHIPPED per-type rerank-query policy reproduce the composition?",
            "prereg": ".hermes/plans/2026-10-29-p1-per-type-rerank-query-preregistration.md",
            "composition": "logs/p1/step10/policy_ab.json (P_gold)",
            "source_artifact": "logs/p1/step10/t4_endpoint.json",
            "n": len(per_query),
            "wall_s": round(time.time() - t0, 1),
        },
        "guards": guards,
        "guard_detail": detail,
        "per_query": per_query,
        "errors": errors,
    }
    Path(args.out).write_text(json.dumps(artifact, indent=1))
    print(f"\nwrote {args.out}")
    print("=== LIVE CONFIRMATION GUARDS ===")
    for k, v in guards.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}: {detail[k.split('_')[0]]}")
    okk = all(guards.values())
    print(f"\n{'ALL GUARDS PASS' if okk else 'GUARD FAILURE'}")
    return 0 if okk else 2


if __name__ == "__main__":
    sys.exit(main())
