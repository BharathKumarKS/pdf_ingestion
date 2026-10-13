"""Measure the offset between the parser's payload page_number and the PDF page index.

Robust version: take each DB page's first chunk, and test whether its opening words
occur (as a substring) in the normalized text of PDF pages p-3..p+3. Count how many
PDF pages contain it; a unique hit gives the offset, zero/multiple hits are ambiguous.
"""
import importlib.util, sqlite3, collections, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec); spec.loader.exec_module(vec)
store = vec.PageStore(str(ROOT / "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"))
con = sqlite3.connect(ROOT / "data/synapse.db"); cur = con.cursor()


def norm(s):
    return " " + re.sub(r"[^a-z0-9 ]", " ", " ".join(s.split()).lower()) + " "


pdf_norm = {p: norm(store.text(p)) for p in range(1, store.n_pages + 1)}
db_pages = [r[0] for r in cur.execute("SELECT DISTINCT page_number FROM chunks ORDER BY page_number")]

offsets = collections.Counter()
ambiguous = unique = 0
samples = []
for p in db_pages:
    row = cur.execute("SELECT text FROM chunks WHERE page_number=? ORDER BY chunk_index LIMIT 1", (p,)).fetchone()
    if not row:
        continue
    needle = norm(row[0])[1:70].strip()
    if len(needle) < 30:
        continue
    hits = [off for off in range(-3, 4) if p + off >= 1 and needle in pdf_norm.get(p + off, "")]
    if len(hits) == 1:
        offsets[hits[0]] += 1
        unique += 1
    else:
        ambiguous += 1
        if len(samples) < 8:
            samples.append((p, hits))

print(f"DB pages compared: {unique + ambiguous}  unique-match: {unique}  ambiguous: {ambiguous}")
print("offset distribution (over unique matches):")
for off, n in sorted(offsets.items(), key=lambda x: -x[1]):
    print(f"  offset {off:+d}: {n:4d}  ({n/max(unique,1):.0%})")
print("\nambiguous samples (page -> matching offsets):")
for p, hits in samples:
    print(f"  p{p}: {hits}")
con.close(); store.close()
