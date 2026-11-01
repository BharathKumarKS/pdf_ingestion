"""Read-only determinism probe for the 4A run (§I103).

**Why it exists.** The first 4A run's G3 (registered as "the three arms' input lane lists are
IDENTICAL, asserted on a lane digest") failed on 5 of 133 queries — yet every arm's per-lane
`min`/`max`/`n` was identical. This probe establishes the MECHANISM and its INERTNESS:

  * the store's vector-lane query is **nondeterministic in its low-ranked tail** — the SAME query,
    the SAME arm, called N times, returns **different lane digests**; but
  * it is **INERT** — the fused POOL and the endpoint pages are **reproducible** across the same N
    calls.

So the arms differ only in the merge (the property G3 exists to protect), measured rather than
assumed. Read-only: no writes, no re-ingest.

    python logs/p1/step10/score_fusion_determinism_probe.py [--n 3] [--sample 15]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score_fusion import (  # noqa: E402
    ARM_SPEC, QUERIES, _install_colbert_watch, _install_lane_capture, _load_queries, _pages_of,
    _retry, _CAP,
)
from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

sys.path.insert(0, str(HERE.parents[2] / "scripts"))
from evaluate_rag import run_retrieval  # noqa: E402


def _sha(pages) -> str:
    return hashlib.sha256(",".join(map(str, pages)).encode()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="repeats per query")
    ap.add_argument("--sample", type=int, default=15)
    ap.add_argument("--ids", default="", help="comma-separated query ids (overrides --sample)")
    ap.add_argument("--arm", default="S0")
    ap.add_argument("--out", default=str(HERE / "score_fusion_determinism_probe.json"))
    args = ap.parse_args()

    cfg = get_settings()
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    _install_colbert_watch()
    _install_lane_capture()

    allq = _load_queries()
    if args.ids:
        want = {s.strip() for s in args.ids.split(",") if s.strip()}
        queries = [q for q in allq if q["id"] in want]
    else:
        queries = allq[:: max(1, len(allq) // args.sample)][: args.sample]
    cache = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map = {prompt_for(q["query"]): cache.get(q["id"]) for q in queries
                  if q.get("query_type") in ("factual", "overview")}
    import src.core.llm as llm_mod
    _real = llm_mod.call_llm
    llm_mod.call_llm = lambda prompt=None, system=None, settings=None, **kw: (
        prompt_map[prompt] if prompt in prompt_map
        else (_ for _ in ()).throw(RuntimeError("HyDE cache miss")))

    fusion = ARM_SPEC[args.arm]["fusion"]
    rows = []
    try:
        for q in queries:
            digests, pool_shas, page_lists = [], [], []
            for _ in range(args.n):
                _CAP["qid"], _CAP["arm"] = q["id"], args.arm
                try:
                    ret = _retry(run_retrieval, q["query"], store, embedder, reranker, cfg,
                                 "global", 0.0, query_type=q.get("query_type", "factual"),
                                 lanes=None, fusion=fusion)
                finally:
                    _CAP["qid"] = None
                digests.append(_CAP["by_arm"].get(q["id"], {}).get(args.arm, {}).get("digest"))
                pool_shas.append(_sha(_pages_of(ret["hits"])))
                page_lists.append(_pages_of(ret["reranked"]))
            rows.append({
                "id": q["id"], "query_type": q.get("query_type", "factual"),
                "n_calls": args.n,
                "n_distinct_lane_digests": len(set(digests)),
                "lane_digests": digests,
                "n_distinct_pool_shas": len(set(pool_shas)),
                "pool_shas": pool_shas,
                "endpoint_pages_reproducible": all(p == page_lists[0] for p in page_lists),
            })
            print(f"  {q['id']:10s} distinct_digests={len(set(digests))}/{args.n}  "
                  f"distinct_pool_sha={len(set(pool_shas))}/{args.n}  "
                  f"pages_stable={rows[-1]['endpoint_pages_reproducible']}")
    finally:
        llm_mod.call_llm = _real

    flipped = [r for r in rows if r["n_distinct_lane_digests"] > 1]
    res = {
        "meta": {
            "what": "the store's vector-lane query is nondeterministic in its tail; the pool is not",
            "arm": args.arm, "fusion": fusion, "n_calls_per_query": args.n,
            "n_queries": len(rows), "read_only": True,
            "collection": cfg.qdrant_collection, "qdrant_host": cfg.qdrant_host,
        },
        "summary": {
            "queries_with_a_lane_digest_flip": len(flipped),
            "queries_with_a_pool_sha_flip": sum(1 for r in rows if r["n_distinct_pool_shas"] > 1),
            "queries_with_unstable_endpoint_pages": sum(
                1 for r in rows if not r["endpoint_pages_reproducible"]),
        },
        "per_query": rows,
    }
    Path(args.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(f"\nwrote {args.out}")
    print(f"lane-digest flipped on {len(flipped)}/{len(rows)} queries; "
          f"pool flipped on {res['summary']['queries_with_a_pool_sha_flip']}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
