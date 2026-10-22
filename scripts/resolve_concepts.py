#!/usr/bin/env python
"""§G3 — apply entity resolution to one document's concept graph.

Near-duplicate `Concept` nodes ('orbit' / 'Orbit' / 'planetary orbit') are separate nodes, so a
query resolving to one spelling reaches only that spelling's chunks (§I2). This collapses each
normalisation group to one canonical node, re-pointing every edge and preserving the merged names
as aliases.

Dry-run by DEFAULT; `--yes` applies. Every merge is journaled with enough state to revert it
(`entity_resolution.revert_merges`) — a merge that is not reversible is one you cannot undo when
the by-eye review (V7) finds a bad one.

    uv run python scripts/resolve_concepts.py --doc-id <uuid>             # dry run
    uv run python scripts/resolve_concepts.py --doc-id <uuid> --yes       # apply

⚠️ Needs the cluster store unless MEMGRAPH_HOST/QDRANT_HOST are set; see IMPROVEMENTS.md §I49
Finding 1 (`.env` leaves QDRANT_HOST blank, so the default is the LOCAL store).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from src.pdf_ingestion.entity_resolution import (
    apply_merges,
    plan_merges,
    read_groups,
    sync_concept_embeddings,
)

DEFAULT_JOURNAL_DIR = Path("logs/p1/step10")


def _concept_count(session, doc_id: str) -> int:
    """Distinct Concept nodes this document's chunks mention — 0 means the doc is absent."""
    row = session.run(
        "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
        "RETURN count(DISTINCT k) AS n",
        doc=doc_id,
    ).single()
    return int(row["n"]) if row else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="§G3 — entity resolution on a document's concept graph")
    parser.add_argument("--doc-id", required=True, help="Document id to resolve")
    parser.add_argument("--yes", action="store_true", help="apply; the default is a dry run")
    parser.add_argument("--journal", type=Path, default=None,
                        help="journal path (default: logs/p1/step10/g3_merge_journal_<date>.jsonl)")
    args = parser.parse_args(argv)

    from src.core.config import get_settings
    from src.core.database import get_memgraph, get_qdrant

    cfg = get_settings()
    driver = get_memgraph(cfg)
    if driver is None:
        print("ERROR: Memgraph driver unavailable — check MEMGRAPH_HOST/PORT", file=sys.stderr)
        return 2

    with driver.session() as session:
        n_concepts = _concept_count(session, args.doc_id)
        if n_concepts == 0:
            print(
                f"ERROR: no Concept nodes for document {args.doc_id!r} — refusing "
                f"(a --doc-id that is not in the graph must not silently merge nothing)",
                file=sys.stderr,
            )
            return 2
        groups, skipped, counts = read_groups(session, args.doc_id)
        plans = plan_merges(groups, counts)
        if not plans:
            print(f"No merges required ({n_concepts} concepts, 0 merge groups).", file=sys.stdout)
            return 0
        journal = args.journal or DEFAULT_JOURNAL_DIR / (
            f"g3_merge_journal_{datetime.now():%Y-%m-%d}.jsonl"
        )
        result = apply_merges(
            session, plans, args.doc_id,
            dry_run=not args.yes,
            journal_path=str(journal) if args.yes else None,
        )

    sync = sync_concept_embeddings(
        get_qdrant(cfg), cfg.concept_collection, plans, dry_run=not args.yes
    )

    verb = "APPLIED" if args.yes else "DRY RUN"
    print(
        f"{verb}: {len(plans)} merge group(s), {result['aliases_merged']} alias(es) merged; "
        f"concept nodes {n_concepts} -> {n_concepts - result['aliases_merged']}; "
        f"names_skipped_empty_key={skipped}; "
        f"{len(sync['deleted_alias_points'])} concept_embeddings point(s) "
        f"{'deleted' if args.yes else 'would be deleted'}"
    )
    if sync["missing_canonical_points"]:
        print(
            f"WARNING: {len(sync['missing_canonical_points'])} canonical concept(s) have no "
            f"concept_embeddings point (V6) — the graph build may not have embedded them",
            file=sys.stderr,
        )
    if args.yes:
        print(f"journal (revert with entity_resolution.revert_merges): {journal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
