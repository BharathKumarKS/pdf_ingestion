"""WIDE-CE ENDPOINT RUN — record the CROSS-ENCODER's FULL ranking over a WIDE pool (cap 500).

Pre-registration: `.hermes/plans/2026-11-01-p1-wide-ce-endpoint-preregistration.md` (committed ALONE first).

THE QUESTION. SSI105 swept k at the endpoint but the CE's ranking was only available to k=50 (T4 kept
<=50). The owner asked: widen the pool cap and sweep k higher. The POOL arm is read-only
(`wide_pool_k_sweep.py`, cap 500, from fusion_attribution). THIS run records the missing half: the
CROSS-ENCODER's full ordered page list over the ~300-candidate wide pool, so a per-type k sweep can
reach k ~ 250.

WHAT MOVES. ONLY the product's own config knobs: `mmr_candidates` and `reranker_fetch_k` 100 -> 500
(the pool cap), and `reranker_top_k` 20 -> 500 (so the endpoint KEEPS the CE's whole ranking). One arm.

READ-ONLY. No collection write, no re-ingest, no `src/` change. DA ON and the graph lane ON (T0's lane
set). HyDE ON and frozen (a cache miss RAISES).

Usage:  python logs/p1/step10/wide_ce_endpoint.py [--limit N] [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
from evaluate_rag import run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
BASE = Path("logs/p1/step10")
CAP = 500
# The ONE arm: the product, with the pool cap and the endpoint cut both widened to CAP.
ARM = dict(mmr_enabled=True, mmr_candidates=CAP, reranker_fetch_k=CAP, reranker_top_k=CAP)

socket.setdefaulttimeout(90)
RETRIES = 3


def _load_queries() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _reachable_pages(store, cfg) -> set[int]:
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
            limit=1000, offset=offset, with_payload=["page_number"], with_vectors=False,
        )
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
    return (len(set(pages) & reach) / len(reach)) if reach else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(BASE / "wide_ce_endpoint.json"))
    args = ap.parse_args()

    cfg = get_settings()
    if not cfg.da_enabled:
        logger.error("G-lane: da_enabled is False — this run needs T0's lane set (DA ON)")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)

    queries = _load_queries()
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
        raise RuntimeError(f"HyDE cache miss mid-run for prompt {str(prompt)[:90]!r}")

    llm_mod.call_llm = _frozen_llm

    reach = _reachable_pages(store, cfg)
    logger.info("reachable content pages: {} (T0 recorded 888)", len(reach))

    cfg_arm = cfg.model_copy(update=ARM)
    store_arm = DocumentStore(cfg_arm)

    per_query: list[dict] = []
    errors: list[dict] = []
    fallbacks = 0
    t0 = time.time()
    try:
        for i, q in enumerate(queries, 1):
            qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
            rel = {int(p) for p in q["relevant_pages"]}
            rq = rel & reach
            rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel),
                         "n_reachable": len(rq), "relevant_pages": sorted(rel)}
            try:
                _before = getattr(reranker, "fallbacks", 0)
                ret = _retry(run_retrieval, text, store_arm, embedder, reranker, cfg_arm,
                             "global", 0.0, query_type=qtype)
                rec["CE_pages"] = _pages_of(ret["reranked"])       # the CE's FULL ranking (<= CAP)
                rec["CE_slots"] = len(ret["reranked"])
                rec["pool_pages"] = _pages_of(ret["hits"])
                rec["pool_size"] = sum(1 for h in ret["hits"] if h.get("page_number"))
                rec["cov"] = _cov(rec["CE_pages"], rq)
                rec["pool_cov"] = _cov(rec["pool_pages"], rq)
                rec["reranker_fallback"] = getattr(reranker, "fallbacks", 0) > _before
                rec["colbert_drop"] = bool(getattr(store_arm, "colbert_dropouts", 0) > 0)
                if rec["reranker_fallback"]:
                    fallbacks += 1
                per_query.append(rec)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
                logger.error("[{}] FAILED: {}", qid, exc)
                per_query.append({**rec, "error": str(exc)})
            if i % 20 == 0:
                logger.info("  {}/{} queries", i, len(queries))
    finally:
        llm_mod.call_llm = _real_call_llm
    wall = time.time() - t0

    ok = [r for r in per_query if "error" not in r]
    res = {
        "meta": {
            "harness": "wide_ce_endpoint.py",
            "read_only": True,
            "arm": ARM,
            "collection": cfg.qdrant_collection,
            "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model,
            "dense_dim": cfg.dense_dim,
            "da_enabled": cfg.da_enabled,
            "hyde": "on_frozen",
            "cap": CAP,
            "n_queries": len(queries),
            "n_ok": len(ok),
            "n_errors": len(errors),
            "reranker_fallbacks": fallbacks,
            "reachable_pages": len(reach),
            "wall_seconds": round(wall, 1),
        },
        "guards": {
            "G1_population": len(queries),
            "G1_types": {t: sum(1 for r in ok if r["query_type"] == t) for t in ("factual", "overview", "multihop")},
            "G2_reachable_pages": len(reach),
            "G3_errors": errors,
            "G4_reranker_fallbacks": fallbacks,
            "G5_ce_len_min": min((len(r["CE_pages"]) for r in ok), default=0),
            "G5_ce_len_max": max((len(r["CE_pages"]) for r in ok), default=0),
            "G6_pool_mean": round(statistics.mean([r["pool_size"] for r in ok]), 4) if ok else None,
        },
        "errors": errors,
        "per_query": per_query,
    }
    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))
    g = res["guards"]
    print(f"wrote {out}  ({out.stat().st_size} bytes)  wall {wall:.0f}s")
    print(f"G1 n={g['G1_population']} ok={len(ok)} types={g['G1_types']}")
    print(f"G2 reachable={g['G2_reachable_pages']} (T0: 888)   G4 fallbacks={g['G4_reranker_fallbacks']}")
    print(f"G5 CE len min/max = {g['G5_ce_len_min']}/{g['G5_ce_len_max']}   G6 pool mean={g['G6_pool_mean']}")
    if errors:
        print(f"ERRORS: {len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
