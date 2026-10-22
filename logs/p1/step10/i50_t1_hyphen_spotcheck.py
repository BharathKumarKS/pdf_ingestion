#!/usr/bin/env python
"""Spot-check of the reviewer's C2: after removing '-' from _FORMULA_CHARS, is any GENUINE
formula left unflagged? Read-only, no LLM. 2026-10-22.

The reviewer's answer was "no hyphen-only formula exists in the corpus" — asserted, not shown.
This shows it: every concept name that contains a hyphen but NO digit and NO operator, i.e. every
name whose only 'formula-like' signal was the hyphen. If one of these is a formula rather than a
hyphenated compound, the fix was wrong.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_memgraph  # noqa: E402
from src.pdf_ingestion.entity_resolution import _FORMULA_CHARS, is_formula_like  # noqa: E402

DOC = sys.argv[1] if len(sys.argv) > 1 else "7ba61432-c5e0-416d-aecf-25a232523481"


def main() -> int:
    cfg = get_settings()
    driver = get_memgraph(cfg)
    with driver.session() as s:
        names = [
            r["name"] for r in s.run(
                "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
                "RETURN DISTINCT k.name AS name",
                doc=DOC,
            ).data() if r.get("name")
        ]

    hyphen_only = [
        n for n in names
        if "-" in n and not any(ch.isdigit() for ch in n)
        and not any(ch in _FORMULA_CHARS for ch in n)
    ]
    print(f"concept names: {len(names):,}")
    print(f"names containing '-' with NO digit and NO operator: {len(hyphen_only):,}")
    print("(these are the names whose ONLY formula signal was the hyphen — the fix unflagged them)")
    print()
    for n in sorted(hyphen_only):
        print(f"  {'FORMULA?' if is_formula_like(n) else 'compound '}  {n!r}")

    print()
    print("A name reading FORMULA? here means the fix is wrong; all 'compound' means C2 holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
