#!/usr/bin/env python
"""§G3 V7 — print the merge groups for the by-eye read. Read-only. 2026-10-22.

The §G3 plan's V7 is a HUMAN check: read ~10 merges and confirm none joins two genuinely
distinct concepts (the course's "read the artifacts" rule). Trap T1 is the specific risk —
`['velocity','Velocity','Velocity = √(g h)']` normalises to one key, and merging a formula
into a spelling group is a defect even though every count improves.

Prints, from the LIVE graph (no writes, no LLM):
  1. the top merge groups by chunk-union gain (the ones that carry the measured lever);
  2. every group EXCLUDED by T1 (formula-bearing) — the flag that must fire;
  3. a deterministic sample of 10 mergeable groups for the by-eye read.

Run:
    unset PYTHONPATH && uv run python <this file>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.pdf_ingestion.entity_resolution import (  # noqa: E402
    build_groups,
    choose_canonical,
    flagged_groups,
    mergeable_groups,
)

URI = f"bolt://{os.environ.get('MEMGRAPH_HOST', 'localhost')}:{os.environ.get('MEMGRAPH_PORT', '7687')}"
DOC = sys.argv[1] if len(sys.argv) > 1 else "7ba61432-c5e0-416d-aecf-25a232523481"


def main() -> int:
    from src.core.config import get_settings
    from src.core.database import get_memgraph

    cfg = get_settings()
    driver = get_memgraph(cfg)
    if driver is None:
        print("Memgraph driver unavailable", file=sys.stderr)
        return 2
    with driver.session() as s:
        rows = s.run(
            "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
            "RETURN k.name AS name, collect(DISTINCT c.id) AS chunks",
            doc=DOC,
        ).data()

    names = [r["name"] for r in rows]
    counts = {r["name"]: len(r["chunks"]) for r in rows}
    groups, skipped = build_groups(names)
    mergeable = mergeable_groups(groups)
    flagged = flagged_groups(groups)

    print(f"document {DOC}")
    print(f"distinct concept names        : {len(names)}")
    print(f"names skipped (empty key)     : {skipped}")
    print(f"mergeable groups (T1 applied) : {len(mergeable)}")
    print(f"concepts inside those groups  : {sum(len(g.members) for g in mergeable)}")
    print(f"FLAGGED by T1 (formula member): {len(flagged)} groups, "
          f"{sum(len(g.formula_members) for g in flagged)} formula members")

    print("\n=== 1. TOP 25 MERGE GROUPS by chunk-union gain ===")
    ranked = []
    for g in mergeable:
        union = set()
        for m in g.members:
            union |= {c for c in next(r["chunks"] for r in rows if r["name"] == m)}
        best = max(counts.get(m, 0) for m in g.members)
        ranked.append((len(union) - best, len(union), best, g))
    ranked.sort(key=lambda t: (-t[0], t[3].key))
    for gain, union, best, g in ranked[:25]:
        canon = choose_canonical(g.members, counts)
        aliases = [m for m in g.members if m != canon]
        print(f"  +{gain:>4} chunks  union={union:>4} best={best:>4}  "
              f"'{canon}'  <- {aliases}")

    print("\n=== 2. EVERY GROUP EXCLUDED BY T1 (formula-bearing) ===")
    for g in flagged:
        print(f"  key='{g.key}'  spellings={g.members}  FORMULA={g.formula_members}")

    print("\n=== 3. BY-EYE SAMPLE — 10 mergeable groups (deterministic, every Nth) ===")
    step = max(1, len(mergeable) // 10)
    for g in mergeable[::step][:10]:
        canon = choose_canonical(g.members, counts)
        print(f"  key='{g.key}'  canonical='{canon}'  aliases="
              f"{[m for m in g.members if m != canon]}")

    print("\n" + json.dumps({
        "distinct_names": len(names),
        "skipped_empty_key": skipped,
        "mergeable_groups": len(mergeable),
        "concepts_in_merge_groups": sum(len(g.members) for g in mergeable),
        "flagged_formula_groups": len(flagged),
        "flagged_formula_members": sum(len(g.formula_members) for g in flagged),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
