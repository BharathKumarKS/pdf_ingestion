#!/usr/bin/env python3
"""§I43 read-only probe — measure the RAPTOR point duplication in the live collection.

Nothing is written or deleted. Prints, for the target document:
  - Qdrant total points, raptor_summary points, chunk points
  - the raptor point ids grouped by document and level
  - SQLite raptor_nodes rows (active vs deactivated)
  - the orphan set (in Qdrant, not an ACTIVE SQLite qdrant_point_id)

    QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2 \
      uv run python logs/p1/step10/i43_raptor_dup_probe.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"


def main() -> int:
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from src.core.config import get_settings

    cfg = get_settings()
    kind = "url" if cfg.qdrant_url else "host" if cfg.qdrant_host else "local"
    target = cfg.qdrant_url or (f"{cfg.qdrant_host}:{cfg.qdrant_port}" if cfg.qdrant_host
                                else cfg.qdrant_local_path)
    print(f"collection {cfg.qdrant_collection} @ {target} [{kind}]")
    if kind == "local":
        print("REFUSING: resolved to the local embedded store; §I40 — pass QDRANT_HOST")
        return 2

    kwargs = {"timeout": 120}
    if cfg.qdrant_url:
        kwargs.update(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
    else:
        kwargs.update(host=cfg.qdrant_host, port=cfg.qdrant_port)
    qc = QdrantClient(**kwargs)

    total = int(qc.get_collection(cfg.qdrant_collection).points_count or 0)
    rap_filter = Filter(must=[FieldCondition(key="source_type",
                                             match=MatchValue(value="raptor_summary"))])
    n_rap = int(qc.count(cfg.qdrant_collection, count_filter=rap_filter).count or 0)
    print(f"\nQdrant total points      : {total}")
    print(f"  source_type=raptor_summary : {n_rap}")
    print(f"  chunk points               : {total - n_rap}")

    rap_ids: dict[str, dict] = {}
    offset = None
    while True:
        pts, offset = qc.scroll(cfg.qdrant_collection, limit=512, offset=offset,
                                scroll_filter=rap_filter, with_vectors=False,
                                with_payload=["document_id", "raptor_node_id", "raptor_level"])
        for p in pts:
            rap_ids[str(p.id)] = p.payload or {}
        if offset is None:
            break
    print(f"\nraptor point ids scrolled: {len(rap_ids)}")
    print("  by document_id :",
          dict(Counter(str(p.get("document_id"))[:8] for p in rap_ids.values())))
    print("  by raptor_level:",
          dict(sorted(Counter(p.get("raptor_level") for p in rap_ids.values()).items())))

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT qdrant_point_id, document_id, level, is_active FROM raptor_nodes"
    ).fetchall()
    con.close()
    active = {str(r[0]) for r in rows if r[3] == 1}
    inactive = {str(r[0]) for r in rows if r[3] != 1}
    qd = set(rap_ids)
    print(f"\nSQLite raptor_nodes: {len(rows)} rows "
          f"({len(active)} active, {len(inactive)} deactivated)")
    print(f"  active SQLite point_ids            : {len(active)}")
    print(f"  ORPHANS (in Qdrant, not active)    : {len(qd - active)}")
    print(f"  MISSING (active SQLite, not Qdrant): {len(active - qd)}")

    out = {
        "collection": cfg.qdrant_collection, "target": target,
        "qdrant_total": total, "qdrant_raptor_summary": n_rap,
        "qdrant_chunk_points": total - n_rap,
        "sqlite_rows": len(rows), "sqlite_active": len(active),
        "sqlite_deactivated": len(inactive),
        "orphan_count": len(qd - active), "missing_count": len(active - qd),
        "orphan_ids": sorted(qd - active), "missing_ids": sorted(active - qd),
        "by_document": dict(Counter(str(p.get("document_id")) for p in rap_ids.values())),
        "by_level": {str(k): v for k, v in Counter(
            p.get("raptor_level") for p in rap_ids.values()).items()},
    }
    p = ROOT / "logs/p1/step10/i43_raptor_dup_probe.json"
    p.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {p.relative_to(ROOT)}")
    qc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
