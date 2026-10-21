#!/usr/bin/env python3
"""§I39 — name the chunks the two chosen signals would drop OUTSIDE the TOC/index bands."""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data/synapse.db"
DOC = "7ba61432-c5e0-416d-aecf-25a232523481"

TOC_PAGES = set(range(22, 35))
INDEX_PAGES = set(range(937, 969))
DOT_RUN = re.compile(r"(?:\.\s?){4,}")
COMMA_PAGEREF = re.compile(r",\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT chunk_index, text, page_number, is_content FROM chunks "
    "WHERE document_id = ? ORDER BY chunk_index", (DOC,)).fetchall()
con.close()

hits = []
for r in rows:
    p = r["page_number"]
    if p in TOC_PAGES or p in INDEX_PAGES:
        continue
    text = r["text"] or ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    density = (sum(1 for ln in lines if COMMA_PAGEREF.search(ln)) / len(lines)) if lines else 0.0
    dot = any(DOT_RUN.search(ln) for ln in lines)
    if dot or density >= 0.34:
        hits.append((p, r["chunk_index"], "dot-run" if dot else f"pageref-density={density:.2f}", text))

print(f"chunks dropped outside pages 22-34 / 937-968: {len(hits)}")
for p, idx, why, text in hits:
    print(f"\n  p{p} idx{idx}  [{why}]")
    print(f"    {text[:400]!r}")
