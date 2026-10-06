#!/usr/bin/env python3
"""Measure recall at every boundary of the retrieval funnel, plus the final metrics.

Why: the funnel is 1000 -> 500 -> 250 -> 100 -> 20, but evaluation only ever reported
recall@100 and recall@20. Two points cannot tell you WHICH stage loses the relevant
pages — and that decides whether the fix is chunking (loss at the wide end) or ranking
(loss at the narrow end).

The funnel is executed server-side as ONE nested Qdrant prefetch, so intermediate pools
are invisible from a single call. This script replays each stage as its own query,
mirroring store._qdrant_search exactly:

  B1  dense_64            @1000   the only stage that faces the whole corpus
  B2  dense_64 -> dense_768 @500  full-resolution rescore of B1
  B3  sparse (SPLADE)     @250    independent lexical branch
  B4  RRF union of B2+B3  @100    merge WITHOUT late interaction
  B5  ColBERT over B2+B3  @100    the merge the app actually uses
  B6  cross-encoder       @20     final precision stage

Final metrics are computed on B6: Precision@20, Recall@20, Hit@20, R-precision.

Usage:
  uv run python scripts/funnel_boundary_recall.py
  uv run python scripts/funnel_boundary_recall.py --limit-queries 5   # smoke test
  uv run python scripts/funnel_boundary_recall.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from loguru import logger

TOP_K = 20


def pages_of(points) -> set[int]:
    return {p.payload.get("page_number") for p in points if p.payload.get("page_number")}


def build_filter(cfg, tenant_id: str, source_type: str | None):
    from qdrant_client.models import (
        FieldCondition, Filter, MatchValue, Range,
    )
    must_not = []
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number",
                                       range=Range(lt=cfg.min_content_page)))
    if source_type is None:
        return Filter(
            must_not=must_not,
            should=[
                Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]),
                Filter(must=[FieldCondition(key="tenant_id",
                                            match=MatchValue(value=cfg.global_tenant_id))]),
            ],
        )
    must = [FieldCondition(key="source_type", match=MatchValue(value=source_type))]
    must.append(FieldCondition(
        key="tenant_id",
        match=MatchValue(value=cfg.global_tenant_id if source_type == "base_textbook" else tenant_id),
    ))
    return Filter(must=must, must_not=must_not if cfg.min_content_page > 0 else [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", default="data/eval_queries.json")
    ap.add_argument("--tenant", default="global")
    ap.add_argument("--limit-queries", type=int, default=0, help="0 = all calibrated")
    ap.add_argument("--json", default=None, help="write per-query results here")
    ap.add_argument("--hyde", action="store_true",
                    help="use HyDE for factual/overview (matches the deployed system "
                         "when HYDE_ENABLED=true)")
    args = ap.parse_args()

    from qdrant_client.models import Fusion, FusionQuery, Prefetch

    from src.core.config import get_settings
    from src.pdf_ingestion.embedder import get_embedder
    from src.pdf_ingestion.store import DocumentStore

    cfg = get_settings()
    store = DocumentStore(cfg)
    embedder = get_embedder(cfg)
    q = store._qdrant
    coll = cfg.qdrant_collection

    queries = [x for x in json.loads(Path(args.queries).read_text())
               if x.get("calibrated") and x.get("relevant_pages")]
    if args.limit_queries:
        queries = queries[: args.limit_queries]
    logger.info(f"{len(queries)} calibrated queries with labels")

    # SPLADE + ColBERT are optional lanes; report honestly if absent.
    splade_on = bool(cfg.splade_enabled)
    colbert_on = bool(cfg.colbert_enabled)
    is_local = not cfg.qdrant_host and not cfg.qdrant_url
    logger.info(f"lanes: splade={splade_on} colbert={colbert_on} (local_qdrant={is_local})")

    from src.pdf_ingestion.reranker import get_reranker
    reranker = get_reranker(cfg)

    BOUNDARIES = ["B1_dense64_1000", "B2_dense768_500", "B3_sparse_250",
                  "B4_rrf_union_100", "B5_colbert_100",
                  "B5b_retriever_top20", "B6_rerank_20"]
    per_query = []

    for item in queries:
        qid, text = item["id"], item["query"]
        qtype = item.get("query_type", "factual")
        relevant = set(item["relevant_pages"])
        filt = build_filter(cfg, args.tenant, None)

        rerank_query = text
        vec = np.asarray(embedder.embed_query(text), dtype=np.float32)

        # HyDE — the deployed system uses it for factual/overview, and it changes both
        # the dense search vector AND the cross-encoder's query. Measuring without it
        # measures a system that is not deployed.
        if args.hyde and qtype in ("factual", "overview"):
            try:
                from src.core.llm import call_llm
                hyp = call_llm(
                    prompt=(f"Write 2-3 sentences of physics textbook content "
                            f"that directly answers: {text}"),
                    system=("You are a physics textbook author. Write factual content only. "
                            "No preamble, no 'Here is...', just the content itself."),
                    settings=cfg,
                )
                if hyp:
                    vec = np.asarray(embedder.embed_query(hyp), dtype=np.float32)
                    rerank_query = hyp
            except Exception as exc:
                logger.warning(f"HyDE failed for {qid} ({exc}); using the raw query")

        vec_64 = vec[: cfg.embedding_dim_low].copy()
        vec_64 /= np.linalg.norm(vec_64) + 1e-9

        dense_prefetch = Prefetch(
            prefetch=[Prefetch(query=vec_64.tolist(), using="dense_64", limit=1000)],
            query=vec.tolist(), using="dense_768", limit=500,
        )
        prefetches = [dense_prefetch]

        sv = None
        if splade_on:
            try:
                from src.pdf_ingestion.splade_embedder import get_splade_embedder
                sv = get_splade_embedder(cfg).encode_sparse(text)
                prefetches.append(
                    Prefetch(query=sv.to_qdrant(), using="sparse", limit=250))
            except Exception as exc:
                logger.warning(f"SPLADE failed for {qid}: {exc}")

        def post(points):
            return [p for p in points
                    if (p.payload.get("page_number") or 0) >= cfg.min_content_page]

        row = {"id": qid, "n_relevant": len(relevant), "pages": {}}

        # B1 dense_64 @1000
        r = q.query_points(collection_name=coll, query=vec_64.tolist(),
                           using="dense_64", query_filter=filt, limit=1000,
                           with_payload=True).points
        row["pages"]["B1_dense64_1000"] = pages_of(post(r))

        # B2 dense_64 -> dense_768 @500
        r = q.query_points(collection_name=coll, prefetch=[dense_prefetch],
                           query=vec.tolist(), using="dense_768", query_filter=filt,
                           limit=500, with_payload=True).points
        row["pages"]["B2_dense768_500"] = pages_of(post(r))

        # B3 sparse @250
        if sv is not None:
            r = q.query_points(collection_name=coll, query=sv.to_qdrant(),
                               using="sparse", query_filter=filt, limit=250,
                               with_payload=True).points
            row["pages"]["B3_sparse_250"] = pages_of(post(r))

        # B4 RRF union @100 (merge without late interaction)
        if len(prefetches) > 1:
            r = q.query_points(collection_name=coll, prefetch=prefetches,
                               query=FusionQuery(fusion=Fusion.RRF), query_filter=filt,
                               limit=100, with_payload=True).points
            row["pages"]["B4_rrf_union_100"] = pages_of(post(r))

        # B5 ColBERT over the merge @100 (what the app uses)
        final_points = []
        if colbert_on and not is_local:
            try:
                from src.pdf_ingestion.colbert_embedder import get_colbert_embedder
                cq = get_colbert_embedder(cfg).embed_query(text)
                final_points = q.query_points(
                    collection_name=coll, prefetch=prefetches, query=cq.tolist(),
                    using="colbert", query_filter=filt, limit=100,
                    with_payload=True).points
                row["pages"]["B5_colbert_100"] = pages_of(post(final_points))
            except Exception as exc:
                logger.error(f"ColBERT failed for {qid}: {exc}")

        # B6 cross-encoder @20 — rerank whatever B5 produced (or B4 if no ColBERT)
        pool = post(final_points)
        if not pool:
            if len(prefetches) > 1:
                pool = q.query_points(collection_name=coll, prefetch=prefetches,
                                      query=FusionQuery(fusion=Fusion.RRF),
                                      query_filter=filt, limit=100,
                                      with_payload=True).points
            else:
                pool = r
        chunks = [{"text": p.payload.get("text", ""),
                   "page_number": p.payload.get("page_number"),
                   "score": p.score} for p in pool]

        # CONTROL: the retriever's OWN top-20, before any reranking. Without this,
        # B6's lower recall is confounded with pool size (100 -> 20) and tells us
        # nothing about whether the reranker's ordering helped or hurt.
        row["pages"]["B5b_retriever_top20"] = {
            p.payload.get("page_number") for p in pool[:TOP_K]
            if p.payload.get("page_number")
        }

        if chunks:
            ranked = reranker.rerank(rerank_query, chunks, top_k=TOP_K)
        else:
            ranked = []
        top20 = [c for c in ranked][:TOP_K]
        row["pages"]["B6_rerank_20"] = {c.get("page_number") for c in top20 if c.get("page_number")}
        row["top20_pages"] = [c.get("page_number") for c in top20]
        per_query.append(row)

    # ── Report ────────────────────────────────────────────────────────────
    qrel = {row["id"]: set(next(x["relevant_pages"] for x in queries
                                if x["id"] == row["id"]))
            for row in per_query}

    print("\n" + "=" * 92)
    print("FUNNEL BOUNDARY RECALL  (page-level; a boundary 'has' a page if it is in that pool)")
    print("=" * 92)
    print(f"\n  {'boundary':22} {'pool':>6}  {'mean recall':>12}  "
          f"{'#queries missing >=1 relevant page':>36}")
    summary = {}
    for b in BOUNDARIES:
        vals, missing, pool_sizes = [], 0, []
        for row in per_query:
            pages = row["pages"].get(b)
            if pages is None:
                continue
            rel = qrel[row["id"]]
            vals.append(len(rel & pages) / len(rel))
            pool_sizes.append(len(pages))
            if len(rel & pages) < len(rel):
                missing += 1
        if not vals:
            print(f"  {b:22} {'n/a':>6}  {'lane inactive':>12}")
            continue
        m = statistics.mean(vals)
        summary[b] = m
        print(f"  {b:22} {int(statistics.mean(pool_sizes)):>6}  {m:>12.3f}  {missing:>36}")

    print("\n" + "=" * 92)
    print(f"FINAL METRICS on the reranked top-{TOP_K}")
    print("=" * 92)
    print(f"\n  {'query':12} {'|rel|':>5} {'P@20':>7} {'R@20':>7} {'Hit@20':>7} {'R-prec':>7}")
    agg = {"P@20": [], "R@20": [], "Hit@20": [], "Rprec": []}
    for row in per_query:
        rel = qrel[row["id"]]
        top = set(row["pages"]["B6_rerank_20"])
        hits = len(rel & top)
        p20 = hits / TOP_K
        r20 = hits / len(rel)
        hit = 1.0 if hits else 0.0
        R = len(rel)
        rprec = len(rel & set(row["top20_pages"][:R])) / R if R else 0.0
        agg["P@20"].append(p20); agg["R@20"].append(r20)
        agg["Hit@20"].append(hit); agg["Rprec"].append(rprec)
        print(f"  {row['id']:12} {len(rel):>5} {p20:>7.3f} {r20:>7.3f} {hit:>7.1f} {rprec:>7.3f}")

    print(f"\n  {'MEAN':12} {'':>5} " + " ".join(f"{statistics.mean(agg[k]):>7.3f}"
                                                for k in ("P@20", "R@20", "Hit@20", "Rprec")))
    ceiling = statistics.mean([min(len(qrel[r['id']]), TOP_K) / TOP_K for r in per_query])
    print(f"\n  Precision@20 ceiling for this ground truth (mean min(|rel|,20)/20): {ceiling:.3f}")
    print(f"  -> P@20 of {statistics.mean(agg['P@20']):.3f} is "
          f"{100*statistics.mean(agg['P@20'])/ceiling:.0f}% of the achievable maximum.\n")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"boundaries": summary,
             "metrics": {k: statistics.mean(v) for k, v in agg.items()},
             "per_query": [{k: (list(v) if isinstance(v, set) else v)
                            for k, v in row.items()} for row in per_query]},
            indent=2, default=str))
        logger.info(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
