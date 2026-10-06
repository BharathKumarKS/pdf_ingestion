#!/usr/bin/env python3
"""Align SQLite's chunk/document IDs to the Qdrant cluster (the source of truth).

The app retrieves from Qdrant but renders cards from SQLite. The two were ingested
separately, so they share no IDs at all:

    Qdrant knowledge_base : document 6d55c52b, 5,135 points
    SQLite chunks         : document 5fcc9006, 5,048 rows
    KB point ids ∩ SQLite chunk ids : 0

Every join from a retrieval result back to SQLite therefore fails, which is why
"Key Facts" and question-scoped "Study Cards" were always empty: the cards exist, but
the chunk ids they hang off do not match what retrieval returns.

Rather than rebuild either side (re-embedding 95k cards, or losing the three card types
the stale DA collection never had), this **renames SQLite's IDs to the cluster's**,
matched by chunk text. Measured on the Feynman corpus: 4,964 of 5,048 chunks (98.3%)
match exactly; the remainder are matched by ``chunk_index``, which covers all 5,048.
Nothing is dropped and no embedding is recomputed.

What it rewrites (all in one transaction):
    cards.chunk_id        -> cluster chunk id
    chunks.id             -> cluster point id  (qdrant_point_id too)
    documents.id          -> cluster document id
    raptor_nodes.document_id, page_images.document_id -> cluster document id

Usage:
  # report the mapping first (default is a dry run; writes nothing)
  uv run python scripts/align_stores.py --qdrant-host 10.0.10.65
  # then apply (backs up data/synapse.db first)
  uv run python scripts/align_stores.py --qdrant-host 10.0.10.65 --apply

Exit codes:
  0  dry run (or already aligned)
  1  applied
  2  refused: the mapping covers too little of the corpus to be safe
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

# Refuse to rewrite IDs if we cannot confidently map at least this share of chunks.
MIN_COVERAGE = 0.90


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def scroll_points(host: str, collection: str, keys: list[str]) -> list[dict]:
    import json
    import urllib.request

    out: list[dict] = []
    offset = None
    while True:
        body: dict = {"limit": 1000, "with_payload": keys, "with_vector": False}
        if offset:
            body["offset"] = offset
        req = urllib.request.Request(
            f"http://{host}:6333/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        res = json.load(urllib.request.urlopen(req, timeout=90))["result"]
        out += res["points"]
        offset = res.get("next_page_offset")
        if not offset:
            break
    return out


def build_mapping(kb: list[dict], chunks: list[tuple]) -> tuple[dict, dict]:
    """Return (old_chunk_id -> new_chunk_id, stats).

    The mapping MUST be injective: two source chunks pointing at one cluster point
    would collide on ``chunks.id``'s UNIQUE constraint. On the Feynman corpus 4
    targets are claimed twice (two chunks sharing identical text), so each cluster
    point is assigned at most once and the losers stay on their old ids — they are
    still reachable through their twin, which carries the same text.
    """
    by_text: dict[str, list[str]] = {}
    by_index: dict[int, list[str]] = {}
    for p in kb:
        pl = p["payload"]
        by_text.setdefault(norm(pl.get("text")), []).append(p["id"])
        idx = pl.get("chunk_index")
        if idx is not None:
            by_index.setdefault(idx, []).append(p["id"])

    mapping: dict[str, str] = {}
    taken: set[str] = set()
    stats = {"by_text": 0, "by_index": 0, "ambiguous_text": 0, "unmapped": 0}

    for old_id, text, idx in chunks:
        target = None
        kind = "by_text"
        cands = by_text.get(norm(text), [])
        if len(cands) > 1:
            stats["ambiguous_text"] += 1
        free = [c for c in cands if c not in taken]
        if len(cands) == 1 and free:
            target, kind = free[0], "by_text"
        else:
            ifree = [c for c in by_index.get(idx, []) if c not in taken]
            if len(ifree) == 1:
                target, kind = ifree[0], "by_index"
        if target is None:
            stats["unmapped"] += 1
            continue
        mapping[old_id] = target
        taken.add(target)
        stats[kind] += 1
    return mapping, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--qdrant-host", default="10.0.10.65")
    ap.add_argument("--db", default="data/synapse.db")
    args = ap.parse_args()

    import sqlite3

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    chunks = [(r["id"], r["text"], r["chunk_index"]) for r in db.execute(
        "SELECT id, text, chunk_index FROM chunks")]
    kb = scroll_points(args.qdrant_host, "knowledge_base",
                       ["text", "chunk_index", "document_id", "page_number"])
    logger.info(f"SQLite chunks {len(chunks):,}   KB points {len(kb):,}")

    mapping, stats = build_mapping(kb, chunks)
    coverage = len(mapping) / max(len(chunks), 1)

    print(f"\n  chunks mapped by exact text : {stats['by_text']:,}")
    print(f"  chunks mapped by chunk_index: {stats['by_index']:,}")
    print(f"  ambiguous text (fell back)  : {stats['ambiguous_text']:,}")
    print(f"  UNMAPPED                    : {stats['unmapped']:,}")
    print(f"  → coverage                  : {coverage:.1%}\n")

    if coverage < MIN_COVERAGE:
        logger.error(
            f"coverage {coverage:.1%} is below the {MIN_COVERAGE:.0%} floor — refusing to "
            f"rewrite IDs. Check that --qdrant-host points at the cluster the app queries."
        )
        return 2

    # A non-injective mapping collides on chunks.id's UNIQUE constraint mid-write.
    if len(set(mapping.values())) != len(mapping):
        logger.error("mapping is not injective — two chunks would take the same id; refusing")
        return 2

    # Old document id -> cluster document id (the cluster is single-document here).
    doc_ids = {(p["payload"] or {}).get("document_id") for p in kb}
    doc_ids.discard(None)
    old_docs = {r["id"] for r in db.execute("SELECT id FROM documents")}
    if len(doc_ids) != 1:
        logger.error(f"expected exactly one document id in the cluster, got {doc_ids}")
        return 2
    new_doc = doc_ids.pop()

    print(f"  document id  : {sorted(old_docs)} → {new_doc}")

    # Cards whose chunk is unmapped would keep pointing at a dead chunk id.
    orphan_cards = db.execute(
        "SELECT COUNT(*) FROM cards c LEFT JOIN chunks ch ON c.chunk_id = ch.id "
        "WHERE ch.id IS NULL"
    ).fetchone()[0]
    print(f"  cards whose chunk is unmapped: {orphan_cards:,}\n")

    if not args.apply:
        logger.warning("dry run — re-run with --apply to rewrite the IDs")
        return 0

    backup = f"{args.db}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(args.db, backup)
    logger.info(f"backed up to {backup}")

    cur = db.cursor()
    cur.execute("PRAGMA foreign_keys = OFF")
    # Order matters: children first, then the parent rows we re-key.
    n_cards = 0
    for old_id, new_id in mapping.items():
        cur.execute("UPDATE cards SET chunk_id = ? WHERE chunk_id = ?", (new_id, old_id))
        n_cards += cur.rowcount
    for old_id, new_id in mapping.items():
        cur.execute("UPDATE chunks SET id = ?, qdrant_point_id = ? WHERE id = ?",
                    (new_id, new_id, old_id))
    for old_doc in old_docs:
        for table in ("chunks", "cards", "raptor_nodes", "page_images"):
            cur.execute(f"UPDATE {table} SET document_id = ? WHERE document_id = ?",
                        (new_doc, old_doc))
        cur.execute("UPDATE documents SET id = ? WHERE id = ?", (new_doc, old_doc))
    db.commit()

    logger.success(
        f"rewrote {len(mapping):,} chunk ids, {n_cards:,} card rows, "
        f"{len(old_docs)} document id(s)"
    )

    # Verify against the cluster the way a consumer would.
    sql_ids = {r[0] for r in db.execute("SELECT id FROM chunks")}
    kb_ids = {p["id"] for p in kb}
    print(f"\n  verify: chunk ids ∩ cluster = {len(sql_ids & kb_ids):,} / {len(sql_ids):,}")
    card_join = db.execute(
        "SELECT COUNT(*) FROM cards c JOIN chunks ch ON c.chunk_id = ch.id").fetchone()[0]
    print(f"  verify: cards joining to chunks = {card_join:,} / "
          f"{db.execute('SELECT COUNT(*) FROM cards').fetchone()[0]:,}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())