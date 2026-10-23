#!/usr/bin/env python
"""§I61 follow-on — the OUTER re-score cut: how deep must the full-dim ranking go before the
fusion lane stops losing reachable pages?

Why this exists
---------------
The dense funnel is

    dense_64(prefetch, limit=N)  ->  dense_1024 re-score, keep top L  ->  RRF(dense, sparse, colbert)
    -> page dedup -> MMR to fetch_k -> cross-encoder to top-20

§I61 and the A/B (`prefetch_limit_ab.py`) measured the INNER limit N and found it is not the
lever: raising N from 1000 to exact (3489) moves the 64d lane's own pool coverage 0.815 -> 1.000
but moves the product endpoint by +0.003 (unresolved). That leaves the OUTER cut L — hardcoded
`limit=500` in `store._qdrant_search` — as the prime suspect for the loss between the lane and the
funnel's ~100-chunk pool (0.815 -> 0.605 of labelled pages).

This measures the (N, L) ceiling directly, with NO ANN and NO pipeline, so the number is the cut's
own contribution and not a mixture of the cut, the HNSW approximation, RRF, page dedup and MMR:

  * the MRL lane's output at limit N is computed by EXACT brute-force 64d cosine (so the filtered
    HNSW loss — §I60 measured up to 18.5% — is excluded; we are measuring the CUT, not the ANN);
  * within those N, the candidate set passed to fusion is the top L by EXACT full-dim cosine;
  * coverage = |reachable labelled pages ∩ pages(candidate set)| / |reachable labelled pages|.

⚠️ This is a CEILING, not a prediction. The pipeline's own observed pool (R@100 = 0.6048 at
N=1000) is BELOW the (N=1000, L=500) ceiling here, and the gap is what RRF + page dedup + MMR
cost. Both numbers are reported so the two stages are not confused.

Read-only: no LLM calls (queries go to the cluster embed endpoint), no writes to any store.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/rescore_cut_curve.py
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import numpy as np  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
OUT = "logs/p1/step10/rescore_cut_curve.json"
NEW_DOC = "7ba61432"
TYPES = ("factual", "multihop", "overview")
NS = (1000, 2000, 3489)                      # the MRL lane's prefetch limit
LS = (100, 200, 500, 1000, 2000, 3489)       # the full-dim re-score cut passed to fusion
PROD_N, PROD_L = 1000, 500                   # what production runs today


def content_filter(cfg) -> Filter:
    """The production filter, copied verbatim from `store.py` (the funnel's own filter)."""
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not, should=[
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cfg.global_tenant_id))]),
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value="global"))]),
    ])


def fetch_corpus(client, cfg, filt) -> tuple[np.ndarray, np.ndarray]:
    """Every in-window content chunk of the new document: (vectors (n,1024), pages (n,))."""
    vectors: list[list[float]] = []
    pages: list[int] = []
    offset = None
    dense_name = "dense_1024"
    while True:
        pts, offset = client.scroll(collection_name=cfg.qdrant_collection, scroll_filter=filt,
                                    limit=1000, offset=offset, with_payload=["page_number"],
                                    with_vectors=[dense_name])
        for p in pts:
            v = p.vector
            if isinstance(v, dict):
                v = v.get(dense_name)
            if v is None:
                continue
            pg = (p.payload or {}).get("page_number")
            if pg is None:
                continue
            vectors.append(v)
            pages.append(int(pg))
        if offset is None:
            break
    return (np.asarray(vectors, dtype=np.float32), np.asarray(pages, dtype=np.int64))


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None}
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(mean, 6), "sd": round(sd, 6),
            "ci95": [round(mean - half, 6), round(mean + half, 6)],
            "resolved": bool((mean - half) > 0 or (mean + half) < 0)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    raw = json.loads(Path(QUERIES).read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and q.get("answerable", True) and q.get("query_type") in TYPES
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if not queries:
        print("ABORT: no queries selected.", file=sys.stderr)
        return 3

    from src.core.database import get_qdrant
    client = get_qdrant(cfg)
    filt = content_filter(cfg)

    t0 = time.time()
    E, pages = fetch_corpus(client, cfg, filt)
    n_chunks = len(pages)
    print(f"corpus: {n_chunks} in-window content chunks, {len(set(pages.tolist()))} distinct pages "
          f"({time.time() - t0:.1f}s)")

    # SQLite reachability (the A/B's convention) — cross-checked against the collection's pages.
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine
    with Session(get_engine(cfg)) as session:
        rows = session.exec(select(Chunk).where(
            Chunk.document_id.like(f"{NEW_DOC}%"))).all()  # type: ignore[attr-defined]
    sqlite_pages = {int(c.page_number) for c in rows
                    if c.page_number is not None and c.is_content is not False
                    and cfg.min_content_page <= c.page_number <= cfg.max_content_page}
    coll_pages = set(int(p) for p in pages.tolist())
    print(f"reachable-page sets: SQLite {len(sqlite_pages)}  collection {len(coll_pages)}  "
          f"symmetric difference {len(sqlite_pages ^ coll_pages)}")

    embedder = get_cluster_embedder(cfg)
    t1 = time.time()
    Q = np.asarray([embedder.embed_query(q["query"]) for q in queries], dtype=np.float32)
    print(f"query vectors: {Q.shape} ({time.time() - t1:.1f}s)")

    # Exact brute-force scores. 64d = the MRL lane's own view, re-normalised (§I60).
    E64 = E[:, :cfg.dense_dim_low].copy()
    E64 /= np.linalg.norm(E64, axis=1, keepdims=True) + 1e-12
    Q64 = Q[:, :cfg.dense_dim_low].copy()
    Q64 /= np.linalg.norm(Q64, axis=1, keepdims=True) + 1e-12

    all_idx = np.arange(n_chunks)
    results: list[dict] = []
    t2 = time.time()
    for i, q in enumerate(queries):
        relevant = {int(p) for p in q["relevant_pages"]}
        reach = sorted(relevant & coll_pages)          # reachable = labelled ∩ present in the collection
        s64 = E64 @ Q64[i]
        s1024 = E @ Q[i]
        order64 = np.argsort(-s64, kind="stable")      # the MRL lane's exact output
        order_full = np.argsort(-s1024, kind="stable")  # the full-dim ranking of EVERYTHING
        # the rank of the query's best labelled chunk in that full-dim ordering — i.e. how deep the
        # re-score cut has to go before the query's first relevant chunk is even visible.
        rel_chunks = all_idx[np.isin(pages, np.fromiter(relevant, dtype=np.int64,
                                                        count=len(relevant)))]
        is_rel = np.isin(order_full, rel_chunks)
        best_full_rank = (int(np.argmax(is_rel)) + 1) if is_rel.any() else None
        rec = {"id": q["id"], "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "n_reachable": len(reach),
               "best_labelled_chunk_full_dim_rank": best_full_rank, "cells": {}}
        for N in NS:
            lane = order64[:N] if N < n_chunks else order64
            lane_scores = s1024[lane]
            within = np.argsort(-lane_scores, kind="stable")   # full-dim order WITHIN the lane
            for L in LS:
                keep = lane[within[:L]] if L < lane.size else lane[within]
                got = set(int(pages[j]) for j in keep)
                cov = (len(got & set(reach)) / len(reach)) if reach else None
                rec["cells"][f"N{N}_L{L}"] = (round(cov, 6) if cov is not None else None)
        results.append(rec)
        if (i + 1) % 40 == 0:
            print(f"  [{i + 1}/{len(queries)}] … {time.time() - t2:.0f}s", flush=True)

    # ── aggregate ─────────────────────────────────────────────────────────────
    def mean_cell(N: int, L: int, subset=None) -> float | None:
        sub = subset if subset is not None else results
        vals = [r["cells"][f"N{N}_L{L}"] for r in sub if r["cells"][f"N{N}_L{L}"] is not None]
        return round(statistics.mean(vals), 6) if vals else None

    grid = {str(N): {str(L): mean_cell(N, L) for L in LS} for N in NS}
    grid_exactN = {str(L): mean_cell(n_chunks, L) for L in LS}

    # the L-cut's own contribution: hold N at exact, vary L
    _prod_l = mean_cell(n_chunks, PROD_L)
    l_curve = {}
    for L in LS:
        _c = mean_cell(n_chunks, L)
        l_curve[str(L)] = {
            "coverage": _c,
            # guard the None: a cell with no reachable pages must not crash the aggregation
            "delta_vs_prod_L": (round(_c - _prod_l, 6)
                                if (_c is not None and _prod_l is not None) else None),
        }
    # paired per-query deltas, L vs the production 500, at N = exact
    paired_L = {str(L): paired_ci([(r["cells"][f"N{n_chunks}_L{L}"] or 0.0)
                                   - (r["cells"][f"N{n_chunks}_L{PROD_L}"] or 0.0)
                                   for r in results]) for L in LS}

    ranks = [r["best_labelled_chunk_full_dim_rank"] for r in results
             if r["best_labelled_chunk_full_dim_rank"] is not None]
    rank_hist = {f"<= {t}": sum(1 for x in ranks if x <= t) for t in (100, 200, 500, 1000, 2000, 3489)}

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/rescore_cut_curve.py",
            "what": ("the OUTER full-dim re-score cut: how deep must the ranking go before the "
                     "fusion lane stops losing reachable labelled pages?"),
            "qdrant_collection": cfg.qdrant_collection,
            "qdrant_host": cfg.qdrant_host or "(LOCAL EMBEDDED — WRONG STORE)",
            "document_id": NEW_DOC,
            "n_chunks_in_window": n_chunks,
            "n_pages_in_window": len(coll_pages),
            "n_queries": len(results),
            "ns": list(NS) + [n_chunks], "ls": list(LS),
            "production": {"N": PROD_N, "L": PROD_L},
            "dense_dim_low": cfg.dense_dim_low,
            "method": ("EXACT brute-force cosine at both dimensions — no ANN, no Qdrant scoring, "
                       "no RRF/dedup/MMR. The MRL lane's output is the exact 64d top-N; the "
                       "candidate set passed to fusion is the exact full-dim top-L within it."),
            "unit": "fraction of a query's REACHABLE labelled pages present in the candidate set",
            "no_llm_calls": True, "no_writes": True,
            "cross_check": {
                "sqlite_reachable_pages": len(sqlite_pages),
                "collection_pages": len(coll_pages),
                "symmetric_difference": len(sqlite_pages ^ coll_pages),
            },
        },
        "summary": {
            "grid_coverage": grid,
            "at_exact_prefetch_vary_L": l_curve,
            "paired_delta_vs_L500_at_exact_prefetch": paired_L,
            "best_labelled_chunk_full_dim_rank": {
                "n": len(ranks),
                "min": min(ranks) if ranks else None,
                "median": statistics.median(ranks) if ranks else None,
                "max": max(ranks) if ranks else None,
                "cumulative_queries_within": rank_hist,
            },
            "by_type": {t: {"N3489_L500": mean_cell(n_chunks, PROD_L, [r for r in results if r["query_type"] == t]),
                            "N3489_L2000": mean_cell(n_chunks, 2000, [r for r in results if r["query_type"] == t])}
                        for t in TYPES},
        },
        "queries": sorted(results, key=lambda r: r["id"]),
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== coverage: MRL lane limit N (rows) x full-dim re-score cut L (cols) ===")
    print("        " + "".join(f"  L={L:<6}" for L in LS))
    for N in NS:
        print(f"  N={N:<5}" + "".join(f"  {grid[str(N)][str(L)]:<8.4f}" for L in LS))
    print(f"  N=all ({n_chunks}) " + "".join(f"  {grid_exactN[str(L)]:<8.4f}" for L in LS))
    print("\n=== at exact prefetch, raising L vs the production L=500 ===")
    for L in LS:
        d = paired_L[str(L)]
        print(f"  L={L:<6} coverage {l_curve[str(L)]['coverage']:.4f}  "
              f"delta {d['mean']:+.4f}  CI95 [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}")
    print("\n=== depth needed: rank of the query's best labelled chunk, full-dim over all chunks ===")
    print("  " + "  ".join(f"{k}: {v}" for k, v in rank_hist.items()))
    print(f"  (n={len(ranks)}; median {statistics.median(ranks) if ranks else None}, "
          f"max {max(ranks) if ranks else None})")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
