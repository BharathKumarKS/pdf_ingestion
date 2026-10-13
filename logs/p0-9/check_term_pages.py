"""Did the judge see the term-bearing pages, and what did it say?"""
import json, sqlite3
from pathlib import Path

# term-bearing pages from the coverage search
targets = {
    "neg-nea-003 (laser year)":   {"term_pages": [103, 562, 763, 765, 898, 947]},
    "neg-nea-004 (carbon-14)":    {"term_pages": [107]},
    "neg-nea-007 (tungsten)":     {"term_pages": [600, 660, 754]},
    "neg-nea-001 (electron mm)":  {"term_pages": [948, 950, 962]},
}

cache = Path("data/eval_results/.scan_verdict_cache.jsonl")
verdicts = {}   # (qid, page) -> verdict
for line in cache.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        continue
    qid, page, *_ = (r.get("k") or "").split("|")
    verdicts[(qid, int(page))] = r.get("verdict")

con = sqlite3.connect(Path("data/synapse.db"))
cur = con.cursor()
for label, info in targets.items():
    qid = label.split()[0]
    print(f"\n{label}")
    for p in info["term_pages"]:
        v = verdicts.get((qid, p))
        # what does the page actually contain?
        row = cur.execute(
            "SELECT text FROM chunks WHERE page_number = ? LIMIT 1", (p,)
        ).fetchone()
        snippet = " ".join((row[0] if row else "").split())[:110]
        print(f"   p{p:4d}  judged={str(v):8s}  | {snippet}")
con.close()
