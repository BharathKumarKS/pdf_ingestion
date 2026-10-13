"""Confirm the two flagged pages are real content pages."""
import sqlite3
from pathlib import Path

con = sqlite3.connect(Path("data/synapse.db"))
cur = con.cursor()
for page in (107, 944, 946):
    rows = cur.execute(
        "SELECT chunk_index, text FROM chunks WHERE page_number=? ORDER BY chunk_index", (page,)
    ).fetchall()
    print(f"\n{'='*70}\np{page}  ({len(rows)} chunks)")
    for ci, text in rows:
        print(f"  [{ci}] {' '.join(text.split())[:700]}")
con.close()
