#!/usr/bin/env python
"""LIVE check of lane-plan S3's wiring: does the RAPTOR lane actually fire on the real v3 index?

The unit tests prove the selector with stubs; this proves the WIRING end-to-end against the cluster
and the index that S2 wrote. One overview query, two arms (control = lanes=None, treatment =
lanes=("raptor",)), no LLM (HYDE_ENABLED=false so the probe needs no cache), read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("/Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from evaluate_rag import run_retrieval  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

cfg = get_settings()
assert cfg.qdrant_collection == "knowledge_base_v3", cfg.qdrant_collection

store = DocumentStore(cfg)
embedder = get_cluster_embedder(cfg)
reranker = get_reranker(cfg)

QUERY = "summarise the chapter on energy and momentum conservation"
QID = "ovw-001-live-probe"

out: dict = {"collection": cfg.qdrant_collection, "query": QUERY, "hyde": "OFF (probe)",
             "arms": {}}
for arm, lanes in (("F0_control", None), ("F3_raptor", ("raptor",))):
    before = store.raptor_dropouts
    r = run_retrieval(QUERY, store, embedder, reranker, cfg, "global", 0.0,
                      query_type="overview", lanes=lanes)
    ids = [h.get("chunk_id") for h in r["hits"]]
    raptor_ids = [i for i in ids if i is None]          # raptor nodes carry no chunk_id
    pages = [h.get("page_number") for h in r["hits"]]
    out["arms"][arm] = {
        "lanes": lanes,
        "pool_size": len(r["hits"]),
        "pool_pages": len([p for p in pages if p is not None]),
        "candidates_without_page_number": len([p for p in pages if p is None]),
        "candidates_with_rrf_score": sum(1 for h in r["hits"] if "rrf_score" in h),
        "raptor_candidates_in_pool": len(raptor_ids),
        "raptor_dropouts_delta": store.raptor_dropouts - before,
        "endpoint_pages_top20": len({h.get("page_number") for h in r["reranked"]
                                     if h.get("page_number") is not None}),
    }

print(json.dumps(out, indent=2, sort_keys=True))
Path("/Users/bharathkumar/.hermes/cache/scratch/s3_live_probe.json").write_text(
    json.dumps(out, indent=2, sort_keys=True))

f0, f3 = out["arms"]["F0_control"], out["arms"]["F3_raptor"]
print("\n=== S3 live wiring check ===")
print(f"  [{'PASS' if f0['raptor_candidates_in_pool'] == 0 else 'FAIL'}] "
      f"the control has NO RAPTOR candidate (got {f0['raptor_candidates_in_pool']})")
print(f"  [{'PASS' if f3['raptor_candidates_in_pool'] > 0 else 'FAIL'}] "
      f"the fused arm HAS a RAPTOR candidate (got {f3['raptor_candidates_in_pool']})")
print(f"  [{'PASS' if f3['candidates_with_rrf_score'] == f3['pool_size'] else 'FAIL'}] "
      f"every fused candidate carries an rrf_score "
      f"({f3['candidates_with_rrf_score']}/{f3['pool_size']})")
print(f"  [{'PASS' if f3['raptor_dropouts_delta'] == 0 else 'FAIL'}] "
      f"the RAPTOR lane dropped out 0 times")
# ⚠️ NOT asserted: that the fused pool is a superset of the CONTROL's. F3's lane set is
# ("raptor",) — the vector lanes plus RAPTOR — so it EXCLUDES the DA lane that today's wiring
# appends, and its pool is legitimately SMALLER. The superset property holds against a
# vector-only fused control, which is why the harness needs that arm (see the pre-registration).
print(f"  [info] pool sizes — control {f0['pool_size']}, F3 {f3['pool_size']}; "
      f"the difference is the DA lane the control appends and F3's lane set excludes")
ok = (f0["raptor_candidates_in_pool"] == 0 and f3["raptor_candidates_in_pool"] > 0
      and f3["candidates_with_rrf_score"] == f3["pool_size"]
      and f3["raptor_dropouts_delta"] == 0)
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 2)
