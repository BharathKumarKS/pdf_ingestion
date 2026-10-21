#!/usr/bin/env python3
"""§I43 follow-up — break the 230 raptor_nodes rows down by document, level and state."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
con = sqlite3.connect(ROOT / "data/synapse.db")
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT rowid, id, qdrant_point_id, document_id, level, is_active "
    "FROM raptor_nodes ORDER BY rowid"
).fetchall()
print(f"total rows: {len(rows)}")
print("\nby (document_id, is_active):")
for k, v in sorted(Counter((str(r["document_id"])[:8], r["is_active"]) for r in rows).items()):
    print(f"   {k}: {v}")
print("\nby (document_id, is_active, level):")
for k, v in sorted(Counter((str(r["document_id"])[:8], r["is_active"], r["level"]) for r in rows).items()):
    print(f"   {k}: {v}")
print("\nrowid ranges per (document_id, is_active):")
groups: dict = {}
for r in rows:
    groups.setdefault((str(r["document_id"])[:8], r["is_active"]), []).append(r["rowid"])
for k, v in sorted(groups.items()):
    print(f"   {k}: n={len(v)} rowid {min(v)}..{max(v)}")
print("\ndocuments in table:", sorted({str(r['document_id']) for r in rows}))
con.close()
