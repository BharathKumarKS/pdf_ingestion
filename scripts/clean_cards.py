#!/usr/bin/env python3
"""Remove duplicate and junk cards from SQLite ``cards`` AND Qdrant ``derivative_artifacts``.

A card lives in two places: the SQLite row (what the UI renders, e.g. "Key Facts") and
the Qdrant point (what the card retrieval lane searches). Deleting only one leaves the
two stores disagreeing — the lane keeps serving a card the UI no longer has. So every
deletion here is applied to both.

Two rules, both deliberately conservative — only unambiguous garbage:

  1. junk      : ``content`` is a placeholder ("n/a", "none", ...) or shorter than
                 ``--min-chars`` after stripping. Measured on the Feynman corpus: 36 rows.
  2. duplicate : same ``(document_id, card_type)`` with identical content after
                 case/punctuation/whitespace normalisation; the lowest ``id`` is kept
                 (ids are UUID4 strings, so "lowest" is arbitrary but *stable*).
                 Measured: 258 rows. Note this is 0.3% of 95,213 cards — duplication is
                 NOT what makes the card set unusable; volume is (95k cards for one book).

This script does NOT re-embed anything. If the ``derivative_artifacts`` collection was
built from an older card generation (compare ``payload.card_id`` against ``cards.id`` —
they share no ids at all when it is stale), re-index with::

    uv run python scripts/index_derivative_artifacts.py --clear

Usage:
  # always report first (default is a dry run)
  uv run python scripts/clean_cards.py
  uv run python scripts/clean_cards.py --min-chars 25
  # then actually delete (both stores)
  uv run python scripts/clean_cards.py --apply

Exit codes:
  0  nothing to remove (or a dry run that found work)
  1  removed cards (--apply)
  2  refused: the Qdrant card ids do not intersect the SQLite ids at all, so a delete
     keyed on ``card_id`` would match nothing (the index is stale — see above).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

PLACEHOLDERS = {"n/a", "na", "none", "null", "not applicable", "unknown", ""}


def normalise(text: str) -> str:
    """Case/punctuation/whitespace-insensitive form used to detect duplicates."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify(rows: list[tuple], min_chars: int) -> tuple[list[tuple], list[tuple]]:
    """Return (junk_rows, duplicate_rows). Each row is (id, card_type, content)."""
    junk = [
        r for r in rows
        if (r[2] or "").strip().lower() in PLACEHOLDERS
        or len((r[2] or "").strip()) < min_chars
    ]
    junk_ids = {r[0] for r in junk}

    seen: dict[tuple, str] = {}
    duplicates: list[tuple] = []
    for cid, card_type, content, doc_id in rows:
        if cid in junk_ids:
            continue  # already going; do not double-report
        key = (doc_id, card_type, normalise(content))
        if key in seen:
            duplicates.append((cid, card_type, content))
        else:
            seen[key] = cid
    return junk, duplicates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--min-chars", type=int, default=15,
                    help="content shorter than this (after strip) counts as junk (default 15)")
    ap.add_argument("--qdrant-host", default=None, help="override QDRANT_HOST")
    args = ap.parse_args()

    from src.core.config import get_settings
    from src.pdf_ingestion.store import DocumentStore

    cfg = get_settings()
    if args.qdrant_host:
        cfg.qdrant_host = args.qdrant_host
    store = DocumentStore(cfg)

    rows = store.list_cards_for_cleanup()          # (id, card_type, content, document_id)
    logger.info(f"loaded {len(rows):,} cards from SQLite")

    junk, duplicates = classify(rows, args.min_chars)
    targets = junk + duplicates

    print(f"\n  cards in SQLite        : {len(rows):,}")
    print(f"  junk (placeholder/short): {len(junk):,}")
    print(f"  duplicates (same content): {len(duplicates):,}")
    print(f"  → to remove            : {len(targets):,}")
    if junk:
        print(f"    junk by type   : {dict(Counter(r[1] for r in junk))}")
    if duplicates:
        print(f"    dupes by type  : {dict(Counter(r[1] for r in duplicates))}")
    print(f"  → would remain         : {len(rows) - len(targets):,}\n")

    if not targets:
        logger.info("nothing to remove")
        return 0

    target_ids = [r[0] for r in targets]

    # Cross-store check: if not a single target id exists in Qdrant, the collection was
    # built from a different card generation and a card_id-keyed delete is meaningless.
    present = store.card_ids_present_in_qdrant(target_ids)
    print(f"  target ids found in Qdrant: {len(present):,} / {len(target_ids):,}")
    if not present:
        logger.error(
            "no target card id exists in derivative_artifacts — the collection is a "
            "different card generation (stale). Re-index with "
            "`scripts/index_derivative_artifacts.py --clear` before cleaning."
        )
        return 2

    if not args.apply:
        logger.warning("dry run — re-run with --apply to delete from BOTH stores")
        return 0

    deleted_qdrant = store.delete_cards_by_id(target_ids)
    deleted_sqlite = store.delete_cards_by_id_sqlite(target_ids)
    logger.success(
        f"removed {deleted_sqlite:,} SQLite rows and {deleted_qdrant:,} Qdrant points"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())