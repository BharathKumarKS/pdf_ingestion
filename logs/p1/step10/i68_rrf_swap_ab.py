"""§I68 before/after — the funnel moves from Qdrant's server-side RRF to a client-side merge.

WHAT THIS MEASURES, and why it is needed. §I68 measured that Qdrant's server-side
``FusionQuery(fusion=Fusion.RRF)`` is NON-DETERMINISTIC — the same query, same lanes, returned a
different fused candidate set on consecutive calls — while every individual lane is deterministic.
The fix queries each lane itself and fuses them in Python (``store._rrf_merge``, ``rrf_k=1``). §I68
requires that swap to carry its own before/after rather than be a silent change, because the ranking
*may* differ (ties, and the merge constant).

Three things are measured, over the SAME 133 gold queries and the SAME lanes:
  A. DETERMINISM — 6 identical repeats of each arm on a fixed query set. The BEFORE arm is expected
     to show >1 distinct candidate set (the defect); the AFTER arm must show exactly 1.
  B. RANKING AGREEMENT — paired, per query, the BEFORE top-100 vs the AFTER top-100: identical
     id-sequence count, mean Jaccard overlap, and page-level R@20 (the PRODUCT convention, pages of
     the top-k CHUNKS) both raw and ceiling-normalised (§I58).
  C. NEGATIVE CONTROL — the AFTER arm run twice must be bit-identical (A-vs-A).

BEFORE  = the retired product call (prefetch=lanes, query=FusionQuery(RRF), limit=100).
AFTER   = ``store._qdrant_search(...)`` — the live product path (client-side fusion).

Read-only: no writes to any collection, no LLM calls. HyDE off, so both arms share one query vector.
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

import numpy as np
from loguru import logger
from qdrant_client.models import Fusion, FusionQuery, Prefetch

from src.core.config import get_settings
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
from src.pdf_ingestion.store import DocumentStore, _resolve_low_lane

DET_QUERIES = ["ovw-041", "gold-004", "gold-078", "gold-052"]
DET_REPEATS = 6
TOP_K = 20
FETCH = 100


def _lanes(store, cfg, vec, text, low_name, low_size, dense_name):
    """Build the live lane prefetches — identical for both arms."""
    v64 = vec[:low_size].copy()
    v64 /= np.linalg.norm(v64) + 1e-9
    prefetches = [Prefetch(
        prefetch=[Prefetch(query=v64.tolist(), using=low_name, limit=cfg.dense_prefetch_limit)],
        query=vec.tolist(), using=dense_name, limit=cfg.dense_rescore_limit)]
    if cfg.splade_enabled and text:
        from src.pdf_ingestion.splade_embedder import get_splade_embedder
        sv = get_splade_embedder(cfg).encode_sparse(text)
        prefetches.append(Prefetch(query=sv.to_qdrant(), using="sparse", limit=250))
    is_local = not cfg.qdrant_host and not cfg.qdrant_url
    if cfg.colbert_enabled and text and not is_local:
        from src.pdf_ingestion.colbert_embedder import get_colbert_embedder
        cq = get_colbert_embedder(cfg).embed_query(text)
        prefetches.append(Prefetch(query=cq.tolist(), using="colbert", limit=250))
    return prefetches


def _before(store, cfg, prefetches, filt):
    """The retired product call — server-side RRF."""
    return store._qdrant.query_points(
        collection_name=cfg.qdrant_collection, prefetch=prefetches,
        query=FusionQuery(fusion=Fusion.RRF), query_filter=filt,
        limit=FETCH, with_payload=True).points


def _after(store, vec, filt, text):
    """The live product path — client-side fusion. Returns the fused response."""
    return store._qdrant_search(query_vector=vec, filter_=filt, limit=FETCH, query_text=text)


def _ids(points):
    return tuple(str(p.id) for p in points)


def _pages(points, k):
    return {p.payload.get("page_number") for p in points[:k] if p.payload.get("page_number")}


def _r_at(points, rel, k):
    return len(_pages(points, k) & rel) / len(rel) if rel else 0.0


def _ci(diffs):
    n = len(diffs)
    if n < 2:
        return (float("nan"), float("nan"))
    sd = statistics.stdev(diffs)
    half = 1.96 * sd / (n ** 0.5)
    m = statistics.mean(diffs)
    return (m - half, m + half)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default="data/eval_queries_v2.json")
    ap.add_argument("--tenant", default="global")
    ap.add_argument("--limit-queries", type=int, default=0)
    ap.add_argument("--out", default="logs/p1/step10/i68_rrf_swap_ab.json")
    args = ap.parse_args()

    cfg = get_settings()
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    dense_name = store._dense_vector_name()
    low_name, low_size = _resolve_low_lane(store._collection_vectors(), cfg)
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range
    # Mirror store.search()'s filter EXACTLY, including the RAPTOR exclusion — without it the
    # comparison runs on a candidate pool the product never sees.
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    filt = Filter(must_not=must_not, should=[
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=args.tenant))]),
        Filter(must=[FieldCondition(key="tenant_id",
                                    match=MatchValue(value=cfg.global_tenant_id))]),
    ])
    is_local = not cfg.qdrant_host and not cfg.qdrant_url

    logger.info("collection={} host={} model={} dim={} low={}({}) splade={} colbert={} local={}",
                cfg.qdrant_collection, cfg.qdrant_host or "(local)", cfg.dense_model, cfg.dense_dim,
                low_name, low_size, cfg.splade_enabled, cfg.colbert_enabled, is_local)

    # The 133-query gold set: eval_queries_v2, ids gold-*/ovw-* with labels (§I63/§I70 convention).
    raw = json.loads(Path(args.queries).read_text())
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit_queries:
        queries = queries[:args.limit_queries]
    by_id = {q["id"]: q for q in queries}

    # ── A. determinism ────────────────────────────────────────────────────────
    det = {}
    for qid in DET_QUERIES:
        item = by_id.get(qid)
        if item is None:
            continue
        vec = np.asarray(embedder.embed_query(item["query"]), dtype=np.float32)
        pfs = _lanes(store, cfg, vec, item["query"], low_name, low_size, dense_name)
        before_sets, after_sets = set(), set()
        for _ in range(DET_REPEATS):
            before_sets.add(_ids(_before(store, cfg, pfs, filt)))
            after_sets.add(_ids(_after(store, vec, filt, item["query"]).points))
        det[qid] = {"before_distinct": len(before_sets), "after_distinct": len(after_sets)}
        logger.info("determinism {}: before {}/{} distinct, after {}/{} distinct",
                    qid, len(before_sets), DET_REPEATS, len(after_sets), DET_REPEATS)

    # ── B + C. ranking agreement over the full set ────────────────────────────
    per_query = []
    t0 = time.time()
    for i, item in enumerate(queries, 1):
        qid, text = item["id"], item["query"]
        rel = set(item["relevant_pages"])
        vec = np.asarray(embedder.embed_query(text), dtype=np.float32)
        pfs = _lanes(store, cfg, vec, text, low_name, low_size, dense_name)

        before = _before(store, cfg, pfs, filt)
        before_again = _before(store, cfg, pfs, filt)  # the BEFORE arm's own repeat (control)
        after = _after(store, vec, filt, text).points
        after_again = _after(store, vec, filt, text).points  # negative control (A-vs-A)

        rb, ra = _r_at(before, rel, TOP_K), _r_at(after, rel, TOP_K)
        ceil = min(len(rel), TOP_K) / TOP_K
        per_query.append({
            "id": qid, "n_relevant": len(rel),
            "identical": _ids(before) == _ids(after),
            "jaccard": (len(set(_ids(before)) & set(_ids(after)))
                        / len(set(_ids(before)) | set(_ids(after)))),
            # The BEFORE arm run twice — how much of the set difference above is the DEFECT itself.
            "before_self_identical": _ids(before) == _ids(before_again),
            "before_self_jaccard": len(set(_ids(before)) & set(_ids(before_again)))
            / len(set(_ids(before)) | set(_ids(before_again))),
            "r20_before": rb, "r20_after": ra, "r20_delta": rb - ra,
            "cr20_before": rb / ceil, "cr20_after": ra / ceil, "cr20_delta": (rb - ra) / ceil,
            "avsa_identical": _ids(after) == _ids(after_again),
        })
        if i % 20 == 0:
            logger.info("  {}/{} queries", i, len(queries))
    wall = time.time() - t0

    deltas = [r["r20_delta"] for r in per_query]
    cdeltas = [r["cr20_delta"] for r in per_query]
    rlo, rhi = _ci(deltas)
    clo, chi = _ci(cdeltas)
    n_ident = sum(1 for r in per_query if r["identical"])
    n_avsa = sum(1 for r in per_query if r["avsa_identical"])
    n = len(per_query)

    guards = {
        "G1_after_is_deterministic": (all(v["after_distinct"] == 1 for v in det.values())
                                      and bool(det)),
        "G2_before_shows_the_defect": any(v["before_distinct"] > 1 for v in det.values()),
        "G3_avsa_bit_identical": n_avsa == n,
        "G4_endpoint_near_zero": abs(statistics.mean(deltas)) < 0.02,
        "G5_every_query_scored": n == len(queries) and n > 0,
    }
    artifact = {
        "meta": {
            "collection": cfg.qdrant_collection, "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model, "dense_dim": cfg.dense_dim,
            "low_lane": low_name, "low_size": low_size,
            "splade": cfg.splade_enabled, "colbert": cfg.colbert_enabled, "is_local": is_local,
            "fetch_k": FETCH, "top_k": TOP_K, "hyde": False,
            "rrf_k_after": 1, "n_queries": n, "wall_seconds": round(wall, 1),
        },
        "determinism": det,
        "summary": {
            "identical_id_sequences": n_ident, "n_queries": n,
            "mean_jaccard": statistics.mean(r["jaccard"] for r in per_query),
            "before_self_identical": sum(1 for r in per_query if r["before_self_identical"]),
            "before_self_jaccard_mean": statistics.mean(
                r["before_self_jaccard"] for r in per_query),
            "r20_before": statistics.mean(r["r20_before"] for r in per_query),
            "r20_after": statistics.mean(r["r20_after"] for r in per_query),
            "r20_delta_mean": statistics.mean(deltas), "r20_delta_ci": [rlo, rhi],
            "cr20_before": statistics.mean(r["cr20_before"] for r in per_query),
            "cr20_after": statistics.mean(r["cr20_after"] for r in per_query),
            "cr20_delta_mean": statistics.mean(cdeltas), "cr20_delta_ci": [clo, chi],
            "wins": sum(1 for d in deltas if d > 0), "losses": sum(1 for d in deltas if d < 0),
            "ties": sum(1 for d in deltas if d == 0),
        },
        "guards": guards,
        "per_query": per_query,
    }
    Path(args.out).write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()

    print(json.dumps({k: artifact[k] for k in ("determinism", "summary", "guards")}, indent=2))
    print(f"\nartifact: {args.out}\nsha256: {sha}")
    print("ALL GUARDS PASS" if all(guards.values()) else "GUARD FAILURE: " +
          ", ".join(k for k, v in guards.items() if not v))
    return 0 if all(guards.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
