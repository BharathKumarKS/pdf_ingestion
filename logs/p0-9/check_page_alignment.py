"""Do the parser's payload page_number and the PDF page index agree?

Retrieval filters on the Qdrant payload `page_number` (from the parser); the judge
gate classifies PDF pages via PageStore. If the two numberings are offset, the
front/back page bounds and the gate disagree. Compare the two for the boundary
regions.
"""
import importlib.util, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec); spec.loader.exec_module(vec)
store = vec.PageStore(str(ROOT / "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"))
con = sqlite3.connect(ROOT / "data/synapse.db"); cur = con.cursor()


def db_head(pg, n=70):
    rows = cur.execute("SELECT text FROM chunks WHERE page_number=? ORDER BY chunk_index LIMIT 1", (pg,)).fetchall()
    return " ".join(rows[0][0].split())[:n] if rows else "(no chunk)"


def pdf_head(pg, n=70):
    return " ".join(store.text(pg).split())[:n]


for label, rng in [("front/TOC", range(28, 40)), ("content/index boundary", range(933, 940))]:
    print(f"\n=== {label} ===")
    for pg in rng:
        print(f"  p{pg:4d}  DB : {db_head(pg)}")
        print(f"        PDF: {pdf_head(pg)}")

con.close(); store.close()
