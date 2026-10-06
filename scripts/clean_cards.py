#!/usr/bin/env python3
"""Remove duplicate and junk cards from SQLite ``cards`` AND Qdrant ``derivative_artifacts``.

A card lives in two places: the SQLite row (what the UI renders, e.g. "Key Facts") and
the Qdrant point (what the card retrieval lane searches). Deleting only one leaves the
two stores disagreeing — the lane keeps serving a card the UI no longer has. So every
deletion here is applied to both.

Two rules, both deliberately conservative — only unambiguous garbage:

  1. junk      : the card does not stand on its own — it refers to its source
                 ("according to the passage", "the text states") or is shorter than
                 ``--min-chars``. This is the SAME filter the generator applies
                 (``ResponseParser.is_valuable``), so the corpus matches what extraction
                 would produce today. Measured on the Feynman corpus: 9,829 rows, 8,864
                 of them question cards.
  2. duplicate : same ``(document_id, card_type)`` with identical content after
                 case/punctuation/whitespace normalisation; the first ``id`` is kept.
                 Measured: 245 rows. Note this is 0.3% of 95,213 cards — duplication is
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


def normalise(text: str) -> str:
    """Case/punctuation/whitespace-insensitive form used to detect duplicates."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify(rows: list[tuple], min_chars: int) -> tuple[list[tuple], list[tuple]]:
    """Return (junk_rows, duplicate_rows). Rows are
    (id, card_type, content, answer, title, document_id).

    The junk rule is the SAME filter the generator now applies
    (``ResponseParser.is_valuable``), so the backfilled corpus matches what extraction
    would produce today rather than drifting from it. Duplicates are identical content
    within one (document, card_type) after case/punctuation normalisation; first id wins.
    """
    from src.pdf_ingestion.card_generator import ResponseParser

    junk: list[tuple] = []
    junk_ids: set[str] = set()
    for cid, card_type, content, answer, title, _doc in rows:
        floor = 1 if card_type == "formula" else min_chars
        if not ResponseParser.is_valuable(content, answer, title, min_chars=floor):
            junk.append((cid, card_type, content))
            junk_ids.add(cid)

    seen: dict[tuple, str] = {}
    duplicates: list[tuple] = []
    for cid, card_type, content, _answer, _title, doc_id in rows:
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
    ap.add_argument("--min-chars", type=int, default=20,
                    help="content shorter than this (after strip) counts as junk (default 20, "
                         "matching the generator's own floor)")
    ap.add_argument("--sqlite-only", action="store_true",
                    help="delete only the SQLite rows. Use when derivative_artifacts is a "
                         "different card generation (a stale index that will be rebuilt from "
                         "SQLite) — a card_id-keyed Qdrant delete would match nothing.")
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

    print(f"\n  cards in SQLite              : {len(rows):,}")
    print(f"  junk (not self-contained/short): {len(junk):,}")
    print(f"  duplicates (same content)     : {len(duplicates):,}")
    print(f"  → to remove                   : {len(targets):,}")
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
        if not args.sqlite_only:
            logger.error(
                "no target card id exists in derivative_artifacts — the collection is a "
                "different card generation (stale). Re-index with "
                "`scripts/index_derivative_artifacts.py --clear`, or pass --sqlite-only to "
                "clean SQLite now and rebuild the collection from it afterwards."
            )
            return 2
        logger.warning(
            "derivative_artifacts is a stale generation (no id overlap) — deleting SQLite "
            "rows only; rebuild the collection from SQLite afterwards with "
            "`scripts/index_derivative_artifacts.py --clear`."
        )

    if not args.apply:
        logger.warning("dry run — re-run with --apply to delete")
        return 0

    deleted_qdrant = store.delete_cards_by_id(target_ids) if present else 0
    deleted_sqlite = store.delete_cards_by_id_sqlite(target_ids)
    logger.success(
        f"removed {deleted_sqlite:,} SQLite rows and {deleted_qdrant:,} Qdrant points"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())