#!/usr/bin/env python
"""Verifier for lane-plan S2 — the RAPTOR carry-over into `knowledge_base_v3`.

Checks (each must be able to FAIL):
  V1  v3 holds exactly the number of raptor nodes v2 holds
  V2  the raptor POINT IDS are identical between v2 and v3 (set equality) — the same summaries
  V3  the payloads are identical EXCEPT `embedding_version` (which MUST have changed to nomic);
      a per-point payload hash comparison over the shared keys
  V4  the v3 CHUNK count is unchanged (3,796) — the carry added summaries, it did not touch chunks
  V5  every v3 raptor point carries BOTH dense lanes at the collection's declared widths
  V6  v2 is untouched (still the same raptor count)
  V7  a LIVE `search_raptor` returns results on an overview query (not a count — a query)

Run:  unset PYTHONPATH; uv run python -u logs/p1/step10/raptor_v3_verify.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from loguru import logger  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402
from src.core.config import get_settings  # noqa: E402

V2, V3 = "knowledge_base_v2", "knowledge_base_v3"
EXPECT_CHUNKS_V3 = 3796
EXPECT_RAPTOR = 73
SHARED_KEYS = ["child_chunk_count", "cluster_id", "document_id", "is_global_baseline",
               "raptor_level", "raptor_node_id", "source_type", "tenant_id", "text"]

checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def _scroll(client, coll):
    flt = Filter(must=[FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))])
    out, offset = [], None
    while True:
        recs, offset = client.scroll(collection_name=coll, scroll_filter=flt, limit=256,
                                     offset=offset, with_payload=True, with_vectors=True)
        out.extend(recs)
        if offset is None:
            break
    return out


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps({k: payload.get(k) for k in SHARED_KEYS},
                                     sort_keys=True).encode()).hexdigest()


def main(client=None) -> int:
    import numpy as np
    from qdrant_client import QdrantClient

    cfg = get_settings()
    if client is None:
        client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)

    v2 = _scroll(client, V2)
    v3 = _scroll(client, V3)
    v2_by = {str(p.id): p for p in v2}
    v3_by = {str(p.id): p for p in v3}

    check("V1 v3 raptor count == v2 raptor count",
          len(v3) == len(v2) and len(v3) > 0, f"v2={len(v2)} v3={len(v3)}")
    check("V2 raptor point ids identical (set equality)",
          set(v2_by) == set(v3_by),
          f"missing in v3: {len(set(v2_by) - set(v3_by))}; extra: {len(set(v3_by) - set(v2_by))}")

    diff = [pid for pid in v2_by if pid in v3_by
            and _payload_hash(v2_by[pid].payload) != _payload_hash(v3_by[pid].payload)]
    check("V3 payloads identical except embedding_version", not diff,
          f"{len(diff)} payload mismatches" + (f" e.g. {diff[:3]}" if diff else ""))

    ev = {str(v3_by[pid].payload.get("embedding_version")) for pid in v3_by}
    check("V3b every v3 raptor payload records the nomic model",
          ev == {cfg.dense_model}, f"embedding_version values: {ev}")

    chunk_filter = Filter(must_not=[FieldCondition(
        key="source_type", match=MatchValue(value="raptor_summary"))])
    n_chunks = client.count(collection_name=V3, count_filter=chunk_filter).count
    check("V4 v3 chunk count unchanged", n_chunks == EXPECT_CHUNKS_V3,
          f"chunks={n_chunks} expected {EXPECT_CHUNKS_V3}")

    dst_vecs = client.get_collection(V3).config.params.vectors
    widths = {k: getattr(v, "size", None) for k, v in dst_vecs.items()}
    lane_bad = []
    for p in v3:
        v = p.vector or {}
        for name in ("dense_full", "dense_64"):
            if name not in v or len(v[name]) != widths.get(name):
                lane_bad.append((str(p.id)[:8], name))
    check("V5 every raptor point carries both dense lanes at the declared widths",
          not lane_bad, f"widths={widths}; bad={lane_bad[:3]} ({len(lane_bad)})")

    check("V6 v2 raptor count unchanged", len(v2) == EXPECT_RAPTOR,
          f"v2 raptor={len(v2)} expected {EXPECT_RAPTOR}")

    # V7 — LIVE: the lane answers an overview query through the product's own search_raptor
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(cfg)
    emb = get_cluster_embedder(cfg)
    qv = emb.embed_query("summarise the chapter on energy and momentum")
    hits = store.search_raptor(qv, tenant_id="global", limit=2)
    check("V7 live search_raptor returns results on an overview query", len(hits) > 0,
          f"{len(hits)} hits; top raptor_node_id="
          f"{str(hits[0].get('raptor_node_id'))[:8] if hits else None}")

    ok = True
    print("=== RAPTOR carry-over verifier ===")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and passed
    print(f"\n{len(checks)} checks, {sum(1 for _, p, _ in checks if p)} passed")
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
