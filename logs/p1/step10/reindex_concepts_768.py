#!/usr/bin/env python
"""Re-embed the Memgraph Concept names into `concept_embeddings` at the dense lane's width (768).

WHY THIS EXISTS, AND WHY IT IS *NOT* `run_phase3.py --graph-only`
`concept_embeddings` was dropped by `reset_derived_collections.py` (§I12/§I47) so it could be
recreated at `dense_dim`. Re-populating it needs only the Concept NAMES — they already live in
Memgraph — so this re-embeds them and upserts, **without touching the graph**. `run_phase3.py
--graph-only` would re-EXTRACT concepts from every chunk (an LLM pass over 3,533 chunks, ~1 h 6 m)
and, unless the graph is cleared first, double every `RELATES_TO` weight. None of that is needed:
the graph is valid (the preflight's graph↔Qdrant check passes), only the vectors changed width.

The id scheme and payload are `graph_builder._upsert_concepts_to_qdrant`'s, reproduced exactly:
    id      = uuid5(NAMESPACE_DNS, f"concept:{name}")   (deterministic, so upsert is idempotent)
    payload = {"name": name, "type": <Memgraph type or 'definition'>}
and the embedding is `embed_query(name)` — the graph builder embeds concept names with
`embed_query` on BOTH sides deliberately (§I12 note), so this must too or the lane's index and query
spaces diverge.

Run:
    unset PYTHONPATH
    export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3 \
           DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5 DENSE_DIM=768 DENSE_DIM_LOW=64 \
           QUERY_INSTRUCTION="search_query: " DOCUMENT_PREFIX="search_document: "
    uv run python -u logs/p1/step10/reindex_concepts_768.py
"""
from __future__ import annotations

import sys
import time
import uuid as _uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def main() -> int:
    from neo4j import GraphDatabase
    from qdrant_client.models import PointStruct

    from src.core.config import get_settings
    from src.core.database import get_qdrant
    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder

    cfg = get_settings()
    if cfg.qdrant_collection != "knowledge_base_v3":
        print(f"ABORT: QDRANT_COLLECTION is {cfg.qdrant_collection!r}; expected knowledge_base_v3",
              file=sys.stderr)
        return 3
    if cfg.dense_dim != 768:
        print(f"ABORT: dense_dim is {cfg.dense_dim}, expected 768", file=sys.stderr)
        return 3

    qdrant = get_qdrant(cfg)
    info = qdrant.get_collection(cfg.concept_collection)
    size = getattr(info.config.params.vectors, "size", None)
    print(f"target '{cfg.concept_collection}': {size}d, {info.points_count} points")
    if int(size) != 768:
        print(f"ABORT: {cfg.concept_collection} is {size}d, expected 768", file=sys.stderr)
        return 3

    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )
    with driver.session() as s:
        rows = s.run(
            "MATCH (k:Concept) RETURN k.name AS name, k.type AS type ORDER BY name"
        ).data()
    names = [(r["name"], r.get("type") or "definition") for r in rows if r.get("name")]
    print(f"Memgraph: {len(names)} Concept names to embed")

    # ⚠️ Build the embedder EXPLICITLY — `get_cluster_embedder` is a memoised singleton.
    embedder = ClusterDenseEmbedder(settings=cfg)

    points: list[PointStruct] = []
    upserted = 0
    started = time.time()
    window: list[float] = []
    for i, (name, ctype) in enumerate(names, 1):
        t0 = time.time()
        vec = embedder.embed_query(name)
        points.append(PointStruct(
            id=str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"concept:{name}")),
            vector=vec.tolist(),
            payload={"name": name, "type": ctype},
        ))
        window.append(time.time() - t0)
        if len(window) > 50:
            window.pop(0)
        if len(points) >= 256:
            qdrant.upsert(collection_name=cfg.concept_collection, points=points)
            upserted += len(points)
            points = []
            print(f"  [{i}/{len(names)}] upserted {upserted:,}  rolling {sum(window)/len(window):.3f}s/name")
    if points:
        qdrant.upsert(collection_name=cfg.concept_collection, points=points)
        upserted += len(points)

    final = qdrant.get_collection(cfg.concept_collection)
    print(f"\nupserted {upserted:,} concept points in {time.time()-started:.1f}s; "
          f"collection now {final.points_count:,} points at "
          f"{getattr(final.config.params.vectors,'size',None)}d")
    return 0 if final.points_count == len(names) else 2


if __name__ == "__main__":
    sys.exit(main())
