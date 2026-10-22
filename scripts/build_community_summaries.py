#!/usr/bin/env python
"""§G2 — build Leiden community summaries for one document.

Reads the concept graph from Memgraph, runs the Leiden ladder, and summarises each leaf community
from the FULL passages behind it, merging upward into parent-community summaries. Retrieved by
map-reduce for the global-sensemaking query only.

Dry-run by DEFAULT — it computes the hierarchy and the prompt sizes and makes **no** LLM calls, so
the spend is visible before it happens (V4). `--yes` actually summarises.

⚠️ The modularity gate (`logs/p1/step10/g2_leiden_gate.py`) must pass BEFORE this is run against
the live graph — §G2 is not built on communities that are salt-and-pepper.

    uv run python scripts/build_community_summaries.py --doc-id <uuid>           # dry run
    uv run python scripts/build_community_summaries.py --doc-id <uuid> --yes --out out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.pdf_ingestion.community_summaries import (
    build_hierarchy,
    read_concept_chunks,
    read_concept_graph,
    summarize_communities,
)

DEFAULT_OUT_DIR = Path("logs/p1/step10")


def _full_chunk_texts(cfg, chunk_ids: list[str]) -> list[str]:
    """FULL chunk text from SQLite — never the graph's 500-char `Chunk.chunk_text` stub (V6)."""
    if not chunk_ids:
        return []
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine

    with Session(get_engine(cfg)) as session:
        rows = session.exec(select(Chunk).where(Chunk.id.in_(chunk_ids))).all()  # type: ignore[attr-defined]
    by_id = {c.id: c.text for c in rows}
    return [by_id[i] for i in chunk_ids if i in by_id]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="§G2 — Leiden community summaries")
    parser.add_argument("--doc-id", required=True, help="Document id in Memgraph")
    parser.add_argument("--yes", action="store_true", help="summarise; the default is a dry run")
    parser.add_argument("--out", type=Path, default=None, help="artifact path for the summaries")
    parser.add_argument("--max-chunks", type=int, default=None,
                        help="cap chunks per leaf community (cost control)")
    args = parser.parse_args(argv)

    from src.core.config import get_settings
    from src.core.database import get_memgraph

    cfg = get_settings()
    driver = get_memgraph(cfg)
    if driver is None:
        print("ERROR: Memgraph driver unavailable — check MEMGRAPH_HOST/PORT", file=sys.stderr)
        return 2

    with driver.session() as session:
        g = read_concept_graph(session, args.doc_id)
        concept_chunks = read_concept_chunks(session, args.doc_id)

    if g.number_of_nodes() == 0:
        print(f"ERROR: no Concept nodes for document {args.doc_id!r} — refusing", file=sys.stderr)
        return 2

    hierarchy = build_hierarchy(g)
    print(
        f"concepts={g.number_of_nodes()} edges={g.number_of_edges()} "
        f"levels={[lvl.resolution for lvl in hierarchy.levels]} "
        f"q={[round(lvl.q, 4) for lvl in hierarchy.levels]} "
        f"nesting={hierarchy.nesting}",
        file=sys.stdout,
    )
    for level, lvl in enumerate(hierarchy.levels):
        if not lvl.connectivity["all_connected"]:
            print(
                f"WARNING: level {level} (res {lvl.resolution}) has disconnected communities "
                f"(V2): {lvl.connectivity['disconnected'][:3]}",
                file=sys.stderr,
            )

    if args.yes:
        get_texts = lambda ids: _full_chunk_texts(cfg, ids)          # noqa: E731
    else:
        get_texts = lambda ids: []                                   # dry run: no source read

    out = summarize_communities(
        hierarchy, concept_chunks, get_texts, dry_run=not args.yes,
        max_chunks_per_community=args.max_chunks,
    )

    verb = "SUMMARISED" if args.yes else "DRY RUN"
    print(
        f"{verb}: {out['total_calls']} LLM call(s) "
        f"(by level {out['calls_by_level']}); "
        f"prompt chars by level {out['prompt_chars_by_level']}; "
        f"skipped (no source) {out['skipped_empty']}"
    )

    artifact = {
        "document": args.doc_id,
        "resolutions": [lvl.resolution for lvl in hierarchy.levels],
        "modularity": [lvl.q for lvl in hierarchy.levels],
        "nesting": hierarchy.nesting,
        "cost": {
            "total_calls": out["total_calls"],
            "calls_by_level": out["calls_by_level"],
            "prompt_chars_by_level": out["prompt_chars_by_level"],
        },
        "summaries": {f"{lvl}-{cid}": text for (lvl, cid), text in out["summaries"].items()},
    }
    dest = args.out or DEFAULT_OUT_DIR / f"g2_summaries_{datetime.now():%Y-%m-%d_%H%M}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"artifact: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
