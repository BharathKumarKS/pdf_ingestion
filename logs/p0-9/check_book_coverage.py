"""Does Feynman Vol 1 actually contain the near_miss answers? Search the chunk store."""
import sqlite3, re
from pathlib import Path

db = Path("data/synapse.db")
con = sqlite3.connect(db)
cur = con.cursor()
cols = [r[1] for r in cur.execute("PRAGMA table_info(chunks)")]
print("chunks columns:", cols)
n = cur.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
print("rows:", n)

terms = {
    "electron magnetic moment": ["magnetic moment of the electron", "magnetic moment"],
    "laser invented": ["laser"],
    "top quark": ["top quark"],
    "carbon-14": ["carbon-14", "carbon 14", "radiocarbon"],
    "cosmological constant": ["cosmological constant"],
    "speed of sound in seawater": ["speed of sound"],
    "melting point of tungsten": ["tungsten"],
    "moons of Jupiter": ["Jupiter"],
}
for label, pats in terms.items():
    hits = {}
    for pat in pats:
        for page, text in cur.execute(
            "SELECT page_number, text FROM chunks WHERE lower(text) LIKE ?", (f"%{pat.lower()}%",)
        ):
            hits.setdefault(pat, set()).add(page)
    summ = {p: sorted(v) for p, v in hits.items()}
    print(f"\n{label}:")
    for p, pages in summ.items():
        print(f"   {p!r}: {len(pages)} pages -> {pages[:12]}{' ...' if len(pages) > 12 else ''}")
con.close()
