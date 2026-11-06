#!/usr/bin/env python3
"""THE ROUTER-IN-THE-LOOP RUN (§I116) — does the product's REAL routing cost at the endpoint?

Pre-registration: `.hermes/plans/2026-11-05-p1-router-in-the-loop-preregistration.md` (committed
ALONE, D6.1). The eval feeds the GOLD `query_type`; the product routes with
`IntentRouter.classify()` (agreement 0.5714, D6.5/§I82), which gates HyDE, lane selection and the
rerank query. This measures the cost of the real routing versus the oracle routing.

Arms (identical but for where `query_type` comes from):
  A  the GOLD `query_type`   (today's eval — the oracle)
  B  `IntentRouter.classify(q_vec)`   (the product's real routing)

READ-ONLY. No collection write, no re-ingest, no `src/` change. Retrieval-only (no generator).

Run:  .venv/bin/python logs/p1/step10/router_in_loop.py [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from loguru import logger  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402
from evaluate_rag import compute_retrieval_metrics, run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
OUT = Path("logs/p1/step10/router_in_loop.json")
F0_R20, F0_NDCG = 0.4563, 0.5503   # lane_inclusion.json arm F0 (the product endpoint)
ANCHOR_TOL = 0.02
METRICS = ("recall_at_20", "ndcg_at_20", "map", "mrr", "hit_at_20", "coverage_reachable")


def _text_lane() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    return [x for x in raw if isinstance(x, dict) and x.get("answerable") is True
            and x.get("query_type") != "visual" and (x.get("relevant_pages") or [])]


def _paired(deltas: list[float]) -> dict:
    if len(deltas) < 2:
        return {"n": len(deltas), "mean": None, "ci": None, "resolved": False}
    m = statistics.mean(deltas)
    half = 1.96 * statistics.stdev(deltas) / (len(deltas) ** 0.5)
    return {"n": len(deltas), "mean": m, "ci": [m - half, m + half],
            "resolved": (m - half > 0 or m + half < 0),
            "wins": sum(1 for d in deltas if d > 0), "losses": sum(1 for d in deltas if d < 0)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cfg = get_settings()
    queries = _text_lane()
    if args.limit:
        queries = queries[: args.limit]
    logger.info("text-lane queries: {}", len(queries))

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    from src.core.intent_router import get_intent_router
    router = get_intent_router(cfg)

    # HyDE frozen (a miss RAISES rather than calling the LLM mid-run).
    hyde = load_hyde(Path(QUERIES), cfg=cfg)
    # ⚠️ The cache holds ONLY factual/overview entries (`hyde_cache.build` targets those types).
    # Arm B can ROUTE a gold-multihop query to factual/overview (10 of 133), where HyDE fires but
    # no hypothetical is cached. Freezing to "" there keeps the run deterministic (no live LLM
    # call, §I25's rule); the count is recorded (G7) and stated as a limitation (prereg addendum).
    prompt_map = {prompt_for(q["query"]): hyde.get(q["id"])
                  for q in queries if q["query_type"] in ("factual", "overview")}
    hyde_misses: list[str] = []
    import src.core.llm as llm_mod
    _real = llm_mod.call_llm

    def _frozen(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        hyde_misses.append(prompt)   # an uncached HyDE prompt — frozen to no-hypothetical
        return ""
    llm_mod.call_llm = _frozen

    per, errors = [], []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text, gold = q["id"], q["query"], q["query_type"]
        rel = list(q["relevant_pages"])
        try:
            qv = embedder.embed_query(text)
            intent = router.classify(qv)
            route = intent.value if hasattr(intent, "value") else str(intent)
            rA = run_retrieval(text, store, embedder, reranker, cfg, "global", 0.0, query_type=gold)
            rB = run_retrieval(text, store, embedder, reranker, cfg, "global", 0.0, query_type=route)
            per.append({
                "id": qid, "gold": gold, "router": route, "differs": route != gold,
                "A": compute_retrieval_metrics(rA, rel, cfg),
                "B": compute_retrieval_metrics(rB, rel, cfg),
            })
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("[{}] FAILED: {}", qid, exc)
        if i % 10 == 0:
            logger.info("  {}/{} queries", i, len(queries))
    llm_mod.call_llm = _real
    wall = time.time() - t0

    def _vals(arm, key):
        return [r[arm][key] for r in per if r[arm].get(key) is not None]

    def _mean(arm, key):
        v = _vals(arm, key)
        return statistics.mean(v) if v else None

    deltas = {k: _paired([r["B"][k] - r["A"][k] for r in per
                          if r["A"].get(k) is not None and r["B"].get(k) is not None])
              for k in METRICS}
    pred_dist: dict[str, int] = {}
    for r in per:
        pred_dist[r["router"]] = pred_dist.get(r["router"], 0) + 1
    confusion: dict[str, dict[str, int]] = {}
    for r in per:
        confusion.setdefault(r["gold"], {})
        confusion[r["gold"]][r["router"]] = confusion[r["gold"]].get(r["router"], 0) + 1
    # Queries where HyDE fires (router -> factual/overview) but the gold is not factual/overview —
    # the exact set whose hypothetical is not cached.
    expected_hyde_miss = sum(1 for r in per
                             if r["gold"] not in ("factual", "overview")
                             and r["router"] in ("factual", "overview"))

    a_r20, a_ndcg = _mean("A", "recall_at_20"), _mean("A", "ndcg_at_20")
    guards = {
        "G1_population_133": len(per) == 133 or bool(args.limit),
        "G2_zero_errors": len(errors) == 0,
        "G3_router_differs_from_gold": any(r["differs"] for r in per),
        "G4_armA_reproduces_F0": (a_r20 is not None and a_ndcg is not None
                                  and abs(a_r20 - F0_R20) <= ANCHOR_TOL
                                  and abs(a_ndcg - F0_NDCG) <= ANCHOR_TOL),
        "G5_determinism": True,   # asserted by the verifier on the recorded arrays
        "G6_router_distribution_recorded": bool(pred_dist),
        "G7_hyde_misses_are_the_expected_set": len(hyde_misses) == expected_hyde_miss,
    }

    artifact = {
        "meta": {"question": "does the product's real routing cost at the endpoint?",
                 "prereg": ".hermes/plans/2026-11-05-p1-router-in-the-loop-preregistration.md",
                 "arms": {"A": "gold query_type", "B": "IntentRouter.classify"},
                 "collection": cfg.qdrant_collection, "wall_seconds": round(wall, 1),
                 "n_queries": len(per),
                 "router_agreement": round(sum(1 for r in per if not r["differs"]) / len(per), 4) if per else None,
                 "router_prediction_distribution": pred_dist,
                 "confusion_gold_to_router": confusion,
                 "n_hyde_misses": len(hyde_misses),
                 "expected_hyde_miss": expected_hyde_miss},
        "aggregates": {f"A_{k}": _mean("A", k) for k in METRICS} |
                      {f"B_{k}": _mean("B", k) for k in METRICS},
        "deltas": deltas, "guards": guards, "errors": errors, "per_query": per,
    }
    OUT.write_text(json.dumps(artifact, indent=1))
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(json.dumps({"aggregates": artifact["aggregates"], "deltas": deltas,
                      "guards": guards, "router_agreement": artifact["meta"]["router_agreement"],
                      "pred_dist": pred_dist}, indent=1))
    print(f"\nartifact: {OUT}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if not v]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
