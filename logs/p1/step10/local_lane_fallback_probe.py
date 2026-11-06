"""Local fallback for the TWO lanes that are down on the cluster: sparse (SPLADE) and rerank (CE).

Both are QUERY-TIME lanes: the collection already stores their vectors, produced by
`prithivida/Splade_PP_en_v1` (sparse) and `BAAI/bge-reranker-v2-m3` (rerank). Serving them locally
is therefore a drop-in — no re-ingest — PROVIDED the local model is the same one the index was built
with. The repo already carries both local paths; the only reason they never run is that `.env` sets
`SV_SPARSE_URL` / `SV_RERANK_URL` to the cluster, and the factories prefer the cluster when set.

This probe forces the LOCAL paths (`sv_sparse_url=""`, `sv_rerank_url=""`) and checks:

  A1  the local SPLADE loads (fastembed ONNX) and encodes a query to a sane sparse vector;
  A2  the local sparse lane QUERIES the real `knowledge_base_v3` index and returns hits
      (the drop-in claim: the stored sparse vectors are queryable with the local model);
  A3  the local cross-encoder loads and orders a RELEVANT passage above an irrelevant one;
  A4  the local cross-encoder reranks a REAL dense pool (dense_full) end to end.

Writes ``logs/p1/step10/local_lane_fallback_probe.json``. First run downloads ~532 MB (SPLADE) and
~2.3 GB (reranker) — CPU, no cluster.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.config import Settings  # noqa: E402
from src.pdf_ingestion.embedder import get_embedder  # noqa: E402
from src.pdf_ingestion.reranker import CrossEncoderReranker  # noqa: E402
from src.pdf_ingestion.splade_embedder import get_splade_embedder  # noqa: E402

OUT = ROOT / "logs" / "p1" / "step10" / "local_lane_fallback_probe.json"
QDRANT_HOST = "10.0.10.65"
COLLECTION = "knowledge_base_v3"

QUERY = "What is Newton's second law?"

RELEVANT = ("Newton's second law states that the net force on a body equals the rate of change of "
            "its momentum, which for constant mass reduces to force equals mass times acceleration.")
IRRELEVANT = "The cat sat quietly on the warm mat by the window."


def main() -> int:
    cfg = Settings(
        sv_sparse_url="",            # <- force the LOCAL SPLADE path
        sv_rerank_url="",            # <- force the LOCAL cross-encoder path
        splade_enabled=True, use_stub_splade=False,
        reranker_enabled=True, use_stub_reranker=False,
        dense_model="nomic-ai/nomic-embed-text-v1.5", dense_dim=768, dense_dim_low=64,
        qdrant_host=QDRANT_HOST, qdrant_collection=COLLECTION,
    )
    checks: dict = {}
    t0 = time.time()

    # ── A1 — the local SPLADE loads and encodes ──────────────────────────────
    t = time.time()
    sv = get_splade_embedder(cfg).encode_sparse(QUERY)
    checks["A1_splade_nnz"] = len(sv.indices)
    checks["A1_splade_load_s"] = round(time.time() - t, 1)
    checks["A1_ok"] = 0 < len(sv.indices) < 20000 and len(sv.indices) == len(sv.values)

    # ── A2 — the local sparse lane queries the REAL index ────────────────────
    from qdrant_client import QdrantClient
    from qdrant_client.models import SparseVector as QSparse
    client = QdrantClient(host=QDRANT_HOST, port=6333)
    hits = client.query_points(
        collection_name=COLLECTION,
        query=QSparse(indices=list(sv.indices), values=list(sv.values)),
        using="sparse", limit=5, with_payload=True,
    ).points
    checks["A2_n_hits"] = len(hits)
    checks["A2_top_score"] = round(float(hits[0].score), 4) if hits else None
    checks["A2_top_pages"] = [(h.payload or {}).get("page_number") for h in hits]
    checks["A2_ok"] = len(hits) > 0 and hits[0].score > 0

    # ── A3 — the local cross-encoder orders relevant > irrelevant ────────────
    t = time.time()
    reranker = CrossEncoderReranker(cfg.reranker_model)
    checks["A3_reranker_load_s"] = round(time.time() - t, 1)
    ordered = reranker.rerank(
        QUERY,
        [{"text": IRRELEVANT, "page_number": 1}, {"text": RELEVANT, "page_number": 2}],
        top_k=2,
    )
    checks["A3_order"] = [c["page_number"] for c in ordered]
    checks["A3_ok"] = checks["A3_order"][0] == 2      # the relevant passage must rank first

    # ── A4 — the local cross-encoder over a REAL dense pool ──────────────────
    vec = get_embedder(cfg).embed_query(QUERY)
    dense = client.query_points(
        collection_name=COLLECTION, query=[float(x) for x in vec],
        using="dense_full", limit=30, with_payload=True,
    ).points
    pool = [{"text": (p.payload or {}).get("text", ""),
             "page_number": (p.payload or {}).get("page_number")} for p in dense]
    t = time.time()
    top = reranker.rerank(QUERY, pool, top_k=5)
    checks["A4_pool"] = len(pool)
    checks["A4_top5_pages"] = [c["page_number"] for c in top]
    checks["A4_rerank_s"] = round(time.time() - t, 1)
    checks["A4_ok"] = len(top) == min(5, len(pool)) and all(
        c.get("ce_score") is not None for c in top)

    checks["wall_s"] = round(time.time() - t0, 1)
    result = {
        "note": "local fallback for the two DOWN lanes (sparse + rerank); query-time only, no re-ingest",
        "splade_model": cfg.splade_model, "reranker_model": cfg.reranker_model,
        "collection": COLLECTION, "checks": checks,
        "all_pass": all(v for k, v in checks.items() if k.endswith("_ok")),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
