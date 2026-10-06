#!/usr/bin/env python3
"""Remove visual (ColPali) vectors for documents no longer in the text index.

A re-ingest mints a NEW document id and nothing deletes the previous run's
``visual_knowledge_base`` points. Measured on the cluster: 2,923 visual vectors
across two document ids, where only one of them (1,033 points) matches
``knowledge_base``. The other 1,890 are a full duplicate copy of the same book
under a retired id, so **every visual search returned each page twice**.

Qdrant's ``knowledge_base`` is the source of truth: a visual point is stale when
its ``document_id`` appears in no text document.

Usage:
  # always report first (default is a dry run)
  uv run python scripts/clean_stale_visual.py --qdrant-host 10.0.10.65
  # then actually delete
  uv run python scripts/clean_stale_visual.py --qdrant-host 10.0.10.65 --apply

Exit codes:
  0  nothing stale (or a dry run that found work)
  1  deleted stale points (--apply)
  2  refused: no document id is shared with the text index — almost certainly the
     wrong Qdrant (e.g. the laptop's local store while the graph/cluster is the
     reference), and deleting would wipe a live document.
"""
from __future__ import annotations

import argparse
import sys

from loguru import logger

from src.core.config import get_settings
from src.pdf_ingestion.store import DocumentStore


def text_document_ids(store: DocumentStore) -> set[str]:
    from qdrant_client.models import Filter, IsEmptyCondition, PayloadField

    ids: set[str] = set()
    offset = None
    while True:
        points, offset = store._qdrant.scroll(
            collection_name=store._cfg.qdrant_collection,
            limit=1000,
            offset=offset,
            with_payload=["document_id"],
            with_vectors=False,
        )
        for p in points:
            did = (p.payload or {}).get("document_id")
            if did:
                ids.add(did)
        if offset is None:
            break
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qdrant-host", default=None, help="override QDRANT_HOST (point at the reference index)")
    ap.add_argument("--tenant", default="global")
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()

    cfg = get_settings()
    if args.qdrant_host:
        cfg.qdrant_host = args.qdrant_host

    store = DocumentStore(cfg)
    logger.info("Text collection : {} @ {}", cfg.qdrant_collection, cfg.qdrant_host or "(local)")
    logger.info("Visual collection: {}", cfg.colpali_collection)

    text_ids = text_document_ids(store)
    visual = store.visual_index_documents([args.tenant, cfg.global_tenant_id])

    logger.info("Text documents  : {}", sorted(d[:8] for d in text_ids) or "(none)")
    for did, n in sorted(visual.items(), key=lambda kv: -kv[1]):
        mark = "OK   " if did in text_ids else "STALE"
        logger.info("  {} {}  {} vectors", mark, did[:8], n)

    stale = {d: n for d, n in visual.items() if d not in text_ids}
    if not stale:
        logger.success("Nothing stale — visual index matches the text index.")
        return 0

    if not (set(visual) & text_ids):
        logger.error(
            "REFUSING: the visual index shares NO document id with {} — this is "
            "probably not the Qdrant the index was built against. Point --qdrant-host "
            "at the reference index.",
            cfg.qdrant_collection,
        )
        return 2

    total = sum(stale.values())
    if not args.apply:
        logger.warning("DRY RUN: would delete {} vectors across {} stale document(s). "
                       "Re-run with --apply.", total, len(stale))
        return 0

    from qdrant_client.models import FieldCondition, Filter, MatchValue
    for did, n in stale.items():
        store._qdrant.delete(
            collection_name=cfg.colpali_collection,
            points_selector=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=did))
            ]),
        )
        logger.success("Deleted {} visual vectors for stale doc {}", n, did[:8])

    logger.success("Done — removed {} stale visual vectors.", total)
    return 1


if __name__ == "__main__":
    sys.exit(main())