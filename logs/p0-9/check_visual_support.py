"""Is there visual/figure content in the corpus for visual queries to retrieve?"""
import sqlite3, json
from pathlib import Path
from collections import Counter

con = sqlite3.connect(Path("data/synapse.db"))
cur = con.cursor()

print("== chunks mentioning figures ==")
for pat in ("figure", "fig.", "diagram", "shown in the"):
    n = cur.execute(
        "SELECT COUNT(DISTINCT page_number) FROM chunks WHERE lower(text) LIKE ?",
        (f"%{pat}%",),
    ).fetchone()[0]
    print(f"  pages with {pat!r}: {n}")

print("\n== chunk text with '<!-- image -->' markers ==")
n = cur.execute("SELECT COUNT(*) FROM chunks WHERE text LIKE '%<!-- image -->%'").fetchone()[0]
print(f"  chunks carrying an image marker: {n}")

print("\n== sample figure-caption text ==")
for (pg, t) in cur.execute(
    "SELECT page_number, text FROM chunks WHERE lower(text) LIKE '%figure%' LIMIT 5"
):
    print(f"  p{pg}: {' '.join(t.split())[:160]}")

print("\n== tables in the DB ==")
print(" ", [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")])

print("\n== v1 visual queries (D6 says regenerate, do not reuse) ==")
d = json.loads(Path("data/eval_queries.json").read_text())
for q in d:
    if q.get("query_type") == "visual":
        print(f"  {q['id']:10s} {q['query'][:80]}  pages={q.get('relevant_pages')}")
con.close()
