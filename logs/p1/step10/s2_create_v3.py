#!/usr/bin/env python
"""S2 — drop the gemma-shaped knowledge_base_v3 (must be EMPTY) and re-create it with the §2 schema.

Targeted: touches ONLY knowledge_base_v3. v2, the deployed knowledge_base, SQLite, and the derived
collections are NOT touched (that is why reset_for_reingest.py, which clears all of them, is wrong here).

Run:
    unset PYTHONPATH
    export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3 \
           DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5 DENSE_DIM=768 DENSE_DIM_LOW=64 \
           QUERY_INSTRUCTION="search_query: " DOCUMENT_PREFIX="search_document: "
    uv run python -u <this script>
"""
from __future__ import annotations

import sys

from qdrant_client import QdrantClient

from src.core.config import get_settings
from src.core.database import get_qdrant

TARGET = "knowledge_base_v3"


def main() -> int:
    cfg = get_settings()
    assert cfg.qdrant_collection == TARGET, (
        f"refusing: cfg.qdrant_collection={cfg.qdrant_collection!r}, expected {TARGET!r} "
        "(set QDRANT_COLLECTION)"
    )
    print(f"resolved: host={cfg.qdrant_host!r} collection={cfg.qdrant_collection!r} "
          f"model={cfg.dense_model!r} dim={cfg.dense_dim} dim_low={cfg.dense_dim_low} "
          f"doc_prefix={cfg.document_prefix!r}")

    client = QdrantClient(host=cfg.qdrant_host, port=getattr(cfg, "qdrant_port", 6333) or 6333)
    names = {c.name for c in client.get_collections().collections}

    if TARGET in names:
        info = client.get_collection(TARGET)
        if info.points_count != 0:
            print(f"REFUSING: {TARGET} holds {info.points_count} points — not dropping")
            return 2
        client.delete_collection(TARGET)
        print(f"dropped {TARGET} (was empty)")
    else:
        print(f"{TARGET} absent — nothing to drop")

    # Re-create through the project's own bootstrap, so the schema is the code's, not this script's.
    client2 = get_qdrant(cfg)
    info = client2.get_collection(TARGET)
    vecs = info.config.params.vectors
    sparse = getattr(info.config.params, "sparse_vectors", None) or {}
    lanes = {k: getattr(v, "size", None) for k, v in vecs.items()} if isinstance(vecs, dict) else vecs
    print(f"created {TARGET}: lanes={lanes} sparse={list(sparse.keys())} points={info.points_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
