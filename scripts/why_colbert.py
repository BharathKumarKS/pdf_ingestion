"""Why doesn't ColBERT's late interaction beat plain RRF at the merge?

Two hypotheses to test:
  (a) the 128-d token space is too coarse to separate physics passages, so ColBERT's
      scores cannot rank the candidate pool
  (b) the candidate pool is so uniform that NO reordering can help — in which case the
      merge choice is irrelevant and the pool itself is the problem

Method, per query, over the SAME 100-candidate union pool:
  - recall@20 under four orderings: RRF, ColBERT, dense_768, and RANDOM
    -> if random is close to the others, ordering carries almost no signal
  - ColBERT score separation between candidates that are on a labelled page vs not
    -> if the distributions overlap heavily, the representation cannot discriminate
  - the score spread (max-min) over the pool for each scorer
    -> a flat distribution means every candidate looks equally good
"""
from __future__ import annotations

import argparse, json, random, statistics, sys
from pathlib import Path

sys.path.insert(0, "/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion")

import numpy as np
from loguru import logger

TOP_K = 20


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default="data/eval_queries.json")
    ap.add_argument("--tenant", default="global")
    ap.add_argument("--n-random", type=int, default=50)
    args = ap.parse_args()

    from qdrant_client.models import Fusion, FusionQuery, Prefetch
    from src.core.config import get_settings
    from src.pdf_ingestion.embedder import get_embedder
    from src.pdf_ingestion.store import DocumentStore

    cfg = get_settings()
    store = DocumentStore(cfg)
    q, coll = store._qdrant, cfg.qdrant_collection
    embedder = get_embedder(cfg)
    random.seed(0)

    queries = [x for x in json.loads(Path(args.queries).read_text())
               if x.get("calibrated") and x.get("relevant_pages")]

    def pages(pts):
        return {p.payload.get("page_number") for p in pts if p.payload.get("page_number")}

    def recall_at(points, rel, k=TOP_K):
        return len(rel & pages(points[:k])) / len(rel)

    rows = []
    for item in queries:
        rel = set(item["relevant_pages"])
        vec = np.asarray(embedder.embed_query(item["query"]), dtype=np.float32)
        v64 = vec[: cfg.embedding_dim_low].copy(); v64 /= np.linalg.norm(v64) + 1e-9

        dp = Prefetch(prefetch=[Prefetch(query=v64.tolist(), using="dense_64", limit=1000)],
                      query=vec.tolist(), using="dense_768", limit=500)
        pre = [dp]
        from src.pdf_ingestion.splade_embedder import get_splade_embedder
        sv = get_splade_embedder(cfg).encode_sparse(item["query"])
        pre.append(Prefetch(query=sv.to_qdrant(), using="sparse", limit=250))

        filt = store._build_filter(cfg, args.tenant, None) \
            if hasattr(store, "_build_filter") else None
        if filt is None:
            from qdrant_client.models import FieldCondition, Filter, MatchValue
            filt = Filter(should=[
                Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=args.tenant))]),
                Filter(must=[FieldCondition(key="tenant_id",
                                            match=MatchValue(value=cfg.global_tenant_id))]),
            ])

        rrf = q.query_points(collection_name=coll, prefetch=pre, query=FusionQuery(fusion=Fusion.RRF),
                             query_filter=filt, limit=100, with_payload=True).points
        from src.pdf_ingestion.colbert_embedder import get_colbert_embedder
        cq = get_colbert_embedder(cfg).embed_query(item["query"])
        col = q.query_points(collection_name=coll, prefetch=pre, query=cq.tolist(),
                             using="colbert", query_filter=filt, limit=100,
                             with_payload=True).points
        dns = q.query_points(collection_name=coll, prefetch=[dp], query=vec.tolist(),
                             using="dense_768", query_filter=filt, limit=100,
                             with_payload=True).points

        rand = []
        for _ in range(args.n_random):
            sample = random.sample(rrf, min(TOP_K, len(rrf)))
            rand.append(recall_at(sample, rel))

        cs = [p.score for p in col]
        rel_scores = [p.score for p in col if p.payload.get("page_number") in rel]
        non_scores = [p.score for p in col if p.payload.get("page_number") not in rel]
        rs = [p.score for p in rrf]

        rows.append({
            "id": item["id"], "n_rel": len(rel), "pool": len(rrf),
            "rrf": recall_at(rrf, rel), "col": recall_at(col, rel),
            "dense": recall_at(dns, rel), "rand": statistics.mean(rand),
            "col_spread": max(cs) - min(cs) if cs else 0,
            "rrf_spread": max(rs) - min(rs) if rs else 0,
            "col_rel_mean": statistics.mean(rel_scores) if rel_scores else float("nan"),
            "col_non_mean": statistics.mean(non_scores) if non_scores else float("nan"),
            "n_rel_in_pool": len([p for p in col if p.payload.get("page_number") in rel]),
        })

    hdr = (f"{'query':11} {'|rel|':>5} {'pool':>5} | {'R@20 rrf':>9} {'colbert':>8} "
           f"{'dense':>7} {'RANDOM':>7} | {'col spread':>10} {'rel-vs-non':>10}")
    print("\n" + hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['id']:11} {r['n_rel']:>5} {r['pool']:>5} | {r['rrf']:>9.3f} {r['col']:>8.3f} "
              f"{r['dense']:>7.3f} {r['rand']:>7.3f} | {r['col_spread']:>10.2f} "
              f"{r['col_rel_mean'] - r['col_non_mean']:>+10.2f}")

    def mean(k):
        v = [r[k] for r in rows if isinstance(r[k], float) and r[k] == r[k]]
        return statistics.mean(v) if v else float("nan")

    print("-" * len(hdr))
    print(f"{'MEAN':11} {'':>5} {'':>5} | {mean('rrf'):>9.3f} {mean('col'):>8.3f} "
          f"{mean('dense'):>7.3f} {mean('rand'):>7.3f} | {mean('col_spread'):>10.2f} "
          f"{mean('col_rel_mean') - mean('col_non_mean'):>+10.2f}")

    print(f"""
  RRF {mean('rrf'):.3f}   ColBERT {mean('col'):.3f}   dense {mean('dense'):.3f}   RANDOM {mean('rand'):.3f}

  (a) 'is 128-d too coarse?'  -> look at rel-vs-non: the mean ColBERT score gap between
      candidates on a labelled page and the rest. Near zero = the representation cannot
      separate them, so its ordering is noise.
  (b) 'is the pool uniform?'  -> compare every ordering against RANDOM. If RRF and
      ColBERT both sit close to the random floor, no reordering of this pool can help
      and the pool itself is the constraint.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
