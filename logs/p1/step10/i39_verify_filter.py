#!/usr/bin/env python3
"""§I39 — verify the NEW content filter end-to-end on the real corpus, and print fixtures.

1. Re-classifies all 3,796 chunks of doc `7ba61432` with the updated `is_content` and reports the
   verdict per zone (TOC pages 22-34, index pages 937-968, front 2-21, body 35-936).
2. Prints verbatim index rows that the NEW signal catches, for use as test fixtures.

Read-only.

    uv run python logs/p1/step10/i39_verify_filter.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data/synapse.db"
DOC = "7ba61432-c5e0-416d-aecf-25a232523481"

TOC_PAGES = set(range(22, 35))
INDEX_PAGES = set(range(937, 969))
FRONT_PAGES = set(range(1, 22))


def main() -> int:
    from src.pdf_ingestion.content_filter import is_content, is_index_density, is_toc_layout

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT chunk_index, text, page_number FROM chunks "
        "WHERE document_id = ? ORDER BY chunk_index", (DOC,)).fetchall()
    con.close()

    def zone(p):
        return ("TOC" if p in TOC_PAGES else "INDEX" if p in INDEX_PAGES
                else "FRONT" if p in FRONT_PAGES else "BODY")

    print(f"doc {DOC[:8]}: {len(rows)} chunks — verdicts under the UPDATED is_content")
    print(f"    {'zone':6} {'chunks':>7} {'not content':>12} {'still content':>14}")
    tally = {}
    for r in rows:
        z = zone(r["page_number"])
        t = tally.setdefault(z, [0, 0, 0])
        t[0] += 1
        if is_content(r["text"] or ""):
            t[1] += 1
        else:
            t[2] += 1
    for z in ("TOC", "INDEX", "FRONT", "BODY"):
        if z in tally:
            n, content, dropped = tally[z]
            print(f"    {z:6} {n:>7} {dropped:>12} {content:>14}")

    # body chunks the new signals drop — must be the known, inspected set
    print("\nBODY chunks the new signals drop (pages 35-936):")
    hits = [(r["page_number"], r["chunk_index"], r["text"]) for r in rows
            if zone(r["page_number"]) == "BODY"
            and (is_toc_layout(r["text"] or "") or is_index_density(r["text"] or ""))]
    print(f"    total: {len(hits)}")
    for p, i, t in hits:
        print(f"    p{p} idx{i}: {t[:130]!r}")

    # fixtures: real index rows that the density signal catches but the layout signal does not
    print("\n[fixtures] index chunks caught by is_index_density, NOT is_index_layout:")
    n = 0
    for r in rows:
        if zone(r["page_number"]) != "INDEX":
            continue
        t = r["text"] or ""
        from src.pdf_ingestion.content_filter import is_index_layout
        if is_index_density(t) and not is_index_layout(t):
            print(f"    p{r['page_number']} idx{r['chunk_index']}: {t[:200]!r}")
            n += 1
            if n >= 3:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
