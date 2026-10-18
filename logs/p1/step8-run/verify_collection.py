#!/usr/bin/env python3
"""Step 8 verification: does the written collection actually carry all four lanes?

Counts alone are not enough. `save_document` swallows SPLADE/ColBERT failures, so a
point can exist with `dense_64` + `dense_1024` only and the ingest still reports success.
This probe scrolls every point and reports, per named vector, how many points carry it.

Run:
  uv run python logs/p1/step8-run/verify_collection.py knowledge_base_v2
  uv run python logs/p1/step8-run/verify_collection.py knowledge_base_probe --sqlite data/step8_probe.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from qdrant_client import QdrantClient


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("collection")
    ap.add_argument("--host", default="10.0.10.65")
    ap.add_argument("--port", type=int, default=6333)
    ap.add_argument("--sqlite", default=None, help="SQLite file to cross-check chunk count")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    client = QdrantClient(host=args.host, port=args.port, timeout=60)
    info = client.get_collection(args.collection)
    vectors = info.config.params.vectors
    names = sorted(vectors.keys()) if isinstance(vectors, dict) else ["<unnamed>"]
    dims = {n: (vectors[n].size, vectors[n].distance) for n in names} if isinstance(vectors, dict) else {}

    # Sparse vectors live in a separate config slot.
    sparse_names: list[str] = []
    sp = getattr(info.config.params, "sparse_vectors", None)
    if sp:
        sparse_names = sorted(sp.keys())

    counts = {n: 0 for n in names}
    sparse_counts = {n: 0 for n in sparse_names}
    total = 0
    docs: dict[str, int] = {}
    is_content_true = 0
    with_parent = 0
    no_parent = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=args.collection,
            limit=512,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for p in points:
            total += 1
            vec = p.vector or {}
            for n in names:
                if n in vec:
                    counts[n] += 1
            for n in sparse_names:
                if n in vec:
                    sparse_counts[n] += 1
            payload = p.payload or {}
            did = payload.get("document_id")
            if did:
                docs[did] = docs.get(did, 0) + 1
            if payload.get("is_content") is True:
                is_content_true += 1
            if payload.get("parent_id"):
                with_parent += 1
            else:
                no_parent += 1
        if offset is None:
            break

    out = {
        "collection": args.collection,
        "points_count_reported": info.points_count,
        "points_scrolled": total,
        "named_vectors": names,
        "dims": dims,
        "sparse_vectors": sparse_names,
        "points_carrying": counts,
        "points_carrying_sparse": sparse_counts,
        "documents": docs,
        "is_content_true": is_content_true,
        "with_parent_id": with_parent,
        "without_parent_id": no_parent,
    }

    if args.sqlite:
        import sqlite3
        con = sqlite3.connect(args.sqlite)
        try:
            out["sqlite_chunks_total"] = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
            out["sqlite_chunks_by_doc"] = dict(
                con.execute("SELECT document_id, count(*) FROM chunks GROUP BY document_id").fetchall()
            )
            out["sqlite_documents"] = dict(
                con.execute("SELECT id, filename FROM documents").fetchall()
            )
        finally:
            con.close()

    # Verdict: every named + sparse vector must be present on EVERY point.
    missing = {n: total - c for n, c in {**counts, **sparse_counts}.items() if c != total}
    out["all_lanes_on_every_point"] = not missing
    out["missing"] = missing

    print(json.dumps(out, indent=2, default=str))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2, default=str) + "\n")
        print(f"\nwrote {args.out}")
    return 0 if out["all_lanes_on_every_point"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
