#!/usr/bin/env python3
"""§I43 — remove DUPLICATED RAPTOR points from a collection (read-only by default).

Why this exists
---------------
`save_raptor_tree` used to append: it deactivated the document's SQLite rows and then
upserted *fresh* Qdrant points without removing the previous generation's. Measured
2026-10-21 on `knowledge_base_v2`: 146 `source_type=raptor_summary` points against 73
active `raptor_nodes` rows. The code fix (store.py, same change) stops it recurring; this
script clears the duplication that already happened. The points are derived data — no
re-ingest is needed.

What it keeps, and why that is the right set
--------------------------------------------
A point SURVIVES iff its id is the `qdrant_point_id` of an **active** SQLite `raptor_nodes`
row for the same document. Everything else carrying `source_type=raptor_summary` for that
document is a superseded generation and is removed. The surviving set is exactly what
`search_raptor()` should see: one point per active node.

Usage
-----
    # dry run (default) — prints and records every point it WOULD delete
    QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2 \
      uv run python scripts/dedupe_raptor_points.py --document-id 7ba61432

    # apply
    ... uv run python scripts/dedupe_raptor_points.py --document-id 7ba61432 --yes

Exit codes: 0 = nothing to do or applied; 1 = refused / error; 2 = dry run found work.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"


def _qdrant_client(cfg, allow_local: bool):
    from qdrant_client import QdrantClient

    kind = "url" if cfg.qdrant_url else "host" if cfg.qdrant_host else "local"
    target = (cfg.qdrant_url or f"{cfg.qdrant_host}:{cfg.qdrant_port}"
              if cfg.qdrant_host else cfg.qdrant_local_path)
    if kind == "local" and not allow_local:
        raise SystemExit(
            f"REFUSING: resolved to the LOCAL embedded Qdrant ({target}).\n"
            "  The duplication is on the cluster. Set QDRANT_HOST (e.g. 10.0.10.65)\n"
            "  and QDRANT_COLLECTION, or pass --allow-local to inspect the local store.\n"
        )
    kwargs: dict = {"timeout": 120}
    if cfg.qdrant_url:
        kwargs.update(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
    else:
        kwargs.update(host=cfg.qdrant_host, port=cfg.qdrant_port)
    return QdrantClient(**kwargs), kind, target


def main() -> int:
    ap = argparse.ArgumentParser(description="§I43 — de-duplicate RAPTOR points")
    ap.add_argument("--document-id", required=True,
                    help="document to clean (full uuid, or an 8-char prefix)")
    ap.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--allow-local", action="store_true",
                    help="allow the LOCAL embedded Qdrant (never written by Phase 2 — §I40)")
    args = ap.parse_args()

    from qdrant_client.models import (FieldCondition, Filter, MatchValue, PointIdsList)

    from src.core.config import get_settings

    cfg = get_settings()
    qc, kind, target = _qdrant_client(cfg, args.allow_local)
    print(f"collection {cfg.qdrant_collection} @ {target}   [{kind}]")

    # ── resolve the document ─────────────────────────────────────────────────
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT qdrant_point_id, document_id, level, is_active, summary "
        "FROM raptor_nodes"
    ).fetchall()
    con.close()
    ids = {str(r["document_id"]) for r in rows}
    matches = [d for d in ids if d.startswith(args.document_id)]
    if len(matches) != 1:
        raise SystemExit(
            f"--document-id {args.document_id!r} matched {len(matches)} documents in "
            f"raptor_nodes ({sorted(d[:8] for d in ids)}); give a unique prefix or the full uuid"
        )
    doc = matches[0]

    active = {str(r["qdrant_point_id"]) for r in rows
              if r["document_id"] == doc and r["is_active"] == 1}
    print(f"document {doc[:8]} — active SQLite raptor_nodes: {len(active)}")

    # ── enumerate the document's RAPTOR points ───────────────────────────────
    flt = Filter(must=[
        FieldCondition(key="document_id", match=MatchValue(value=doc)),
        FieldCondition(key="source_type", match=MatchValue(value="raptor_summary")),
    ])
    points: dict[str, dict] = {}
    offset = None
    while True:
        pts, offset = qc.scroll(cfg.qdrant_collection, limit=512, offset=offset,
                                scroll_filter=flt, with_vectors=False,
                                with_payload=["raptor_level", "raptor_node_id", "text"])
        for p in pts:
            points[str(p.id)] = p.payload or {}
        if offset is None:
            break

    orphans = sorted(set(points) - active)
    missing = sorted(active - set(points))

    print(f"\nRAPTOR points in {cfg.qdrant_collection} for this document : {len(points)}")
    print(f"  survive (active SQLite qdrant_point_id) : {len(points) - len(orphans)}")
    print(f"  DELETE  (superseded generation)         : {len(orphans)}")
    print(f"  ⚠️ active nodes with NO point in Qdrant : {len(missing)}")

    if orphans:
        print("\n  points that WOULD be deleted:")
        for pid in orphans:
            pl = points[pid]
            preview = (pl.get("text") or "").strip().replace("\n", " ")[:58]
            print(f"    {pid}  L{pl.get('raptor_level')}  {preview!r}")
    if missing:
        print("\n  ⚠️ active SQLite nodes with no Qdrant point (their summaries are not "
              "retrievable; rebuild with --raptor-only if this should be 0):")
        for pid in missing[:10]:
            print(f"    {pid}")
        if len(missing) > 10:
            print(f"    … and {len(missing) - 10} more")

    artifact = {
        "document_id": doc, "collection": cfg.qdrant_collection, "target": target,
        "points_total": len(points), "survivors": len(points) - len(orphans),
        "orphans": orphans, "missing_point_for_active_node": missing,
        "by_level": dict(sorted(Counter(points[p].get("raptor_level")
                                        for p in orphans).items())),
        "applied": bool(args.yes and orphans),
    }

    if not orphans:
        print("\nnothing to do — one point per active node")
    elif not args.yes:
        print(f"\nDRY RUN — {len(orphans)} points would be deleted. Re-run with --yes to apply.")
    else:
        qc.delete(collection_name=cfg.qdrant_collection,
                  points_selector=PointIdsList(points=orphans))
        after = int(qc.count(cfg.qdrant_collection, count_filter=flt).count or 0)
        print(f"\nAPPLIED — deleted {len(orphans)} points.")
        print(f"  RAPTOR points for this document now: {after} "
              f"(expected {len(points) - len(orphans)})")
        if after != len(points) - len(orphans):
            print("  !! count does not match the expectation — investigate before re-running B5")
            artifact["applied"] = False
            artifact["post_count"] = after

    out = ROOT / "logs/p1/step10/i43_raptor_dedupe.json"
    out.write_text(json.dumps(artifact, indent=2))
    print(f"\nwrote {out.relative_to(ROOT)}")
    qc.close()
    if not orphans:
        return 0
    return 0 if args.yes else 2


if __name__ == "__main__":
    sys.exit(main())
