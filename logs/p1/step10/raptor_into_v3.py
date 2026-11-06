#!/usr/bin/env python
"""Carry `knowledge_base_v2`'s 73 RAPTOR summary nodes into `knowledge_base_v3` (lane-plan S2/B1-B2).

WHY CARRIED, NOT REGENERATED. The RAPTOR summaries are LLM-generated and **v2 already holds them**.
Regenerating them for v3 would be an expensive, NON-DETERMINISTIC LLM pass and would break identity
with v2 — so the summaries are **carried**: the same point id and the same payload, with only the
DENSE VECTORS recomputed under v3's embedder (nomic-768 + its MRL 64 lane), because a dimension is
immutable and v2's are Qwen3-1024.

⚠️ Precedent: §I83 re-embedded only the concept NAMES into the 768d collection, keeping the graph
that was already valid. Same move, same reason.

The 73 summary nodes carry NO `colbert` and NO `sparse` vector (§I76: the points without a sparse
vector ARE the raptor_level-1 summary nodes), so only the two dense lanes are written.

Read-only w.r.t. v2. Writes ONLY `raptor_summary` points into v3.

Run:  unset PYTHONPATH; uv run python -u logs/p1/step10/raptor_into_v3.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from loguru import logger  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder, mrl_slice  # noqa: E402
from src.pdf_ingestion.store import _dense_name_from, _resolve_low_lane  # noqa: E402

SOURCE = "knowledge_base_v2"
DEST = "knowledge_base_v3"


def _scroll_raptor(client, collection: str) -> list:
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    flt = Filter(must=[FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))])
    out, offset = [], None
    while True:
        recs, offset = client.scroll(collection_name=collection, scroll_filter=flt, limit=256,
                                     offset=offset, with_payload=True, with_vectors=False)
        out.extend(recs)
        if offset is None:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    cfg = get_settings()
    if cfg.qdrant_collection != DEST:
        logger.error("QDRANT_COLLECTION is {!r}, not {!r} — refusing to write", cfg.qdrant_collection, DEST)
        return 2

    client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)

    # destination lane names/widths, resolved OFF THE COLLECTION (never from cfg)
    dst = client.get_collection(DEST).config.params.vectors
    dense_name = _dense_name_from(dst) or "dense_full"
    low_name, low_size = _resolve_low_lane(dst, cfg)

    src = _scroll_raptor(client, SOURCE)
    logger.info("v2 raptor nodes: {}", len(src))

    embedder = get_cluster_embedder(cfg)
    texts = [p.payload["text"] for p in src]
    full_vecs = embedder.embed_documents(texts)

    points = []
    for p, full in zip(src, full_vecs):
        full = __import__("numpy").asarray(full, dtype="float32")
        low = mrl_slice(full, low_size)
        payload = dict(p.payload)
        payload["embedding_version"] = cfg.dense_model
        points.append(PointStruct(id=p.id, vector={low_name: low.tolist(),
                                                   dense_name: full.tolist()}, payload=payload))

    logger.info("built {} points ({}+{})", len(points), dense_name, low_name)
    if args.dry_run:
        logger.info("DRY RUN — nothing written")
        return 0

    for i in range(0, len(points), 64):
        client.upsert(collection_name=DEST, points=points[i:i + 64])
    after = client.get_collection(DEST).points_count
    logger.info("upserted {} raptor points into {}; collection now {} points", len(points), DEST, after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
