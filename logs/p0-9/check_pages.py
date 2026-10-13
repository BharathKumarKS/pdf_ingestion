"""Read the pages that mention 'magnetic moment' — is the electron's value given?"""
import sqlite3
from pathlib import Path

con = sqlite3.connect(Path("data/synapse.db"))
cur = con.cursor()

for page in (947, 948, 950, 962, 765, 107):
    rows = cur.execute(
        "SELECT chunk_index, text FROM chunks WHERE page_number = ? ORDER BY chunk_index",
        (page,),
    ).fetchall()
    print(f"\n{'='*70}\np{page}  ({len(rows)} chunks)")
    for ci, text in rows:
        t = " ".join(text.split())
        print(f"  [{ci}] {t[:600]}")
con.close()
