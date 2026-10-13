"""Calibrate the back-matter gate on the PDF text the judge actually sees.

Prints, for the front-matter/TOC region and the index region, the structural
signals so the thresholds are chosen from data, not guessed.
"""
import importlib.util, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec); spec.loader.exec_module(vec)

store = vec.PageStore(str(ROOT / "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"))
n = store.n_pages
ref = re.compile(r"\b(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}\b")
dots = re.compile(r"\.\s?\.\s?\.")

def stats(pg):
    t = store.text(pg)
    lines = [l for l in t.splitlines() if l.strip()]
    if not lines:
        return None
    rf = sum(1 for l in lines if ref.search(l)) / len(lines)
    df = sum(1 for l in lines if dots.search(l)) / len(lines)
    low = t.lower()
    head = [h for h in ("## index", "name index", "subject index", "## contents") if h in low]
    return rf, df, len(lines), head

def show(title, pages):
    print(f"\n== {title} ==")
    print(f"{'page':>5} {'ref_frac':>8} {'dot_frac':>8} {'lines':>5}  headings")
    for pg in pages:
        s = stats(pg)
        if s is None:
            print(f"{pg:5d}  (no text)")
            continue
        rf, df, ln, head = s
        flag = "  <-- GATED" if vec.is_back_matter_page(store.text(pg), pg, n) else ""
        print(f"{pg:5d} {rf:8.2f} {df:8.2f} {ln:5d}  {head}{flag}")

show("front matter / TOC", list(range(20, 34)))
show("index / back matter", list(range(934, 968)))
show("content controls", [100, 112, 134, 200, 300, 500, 599, 628, 652, 816, 930, 933, 935])

# How many pages book-wide would the dot-leader signal alone flag?
dl = [pg for pg in range(1, n + 1) if (stats(pg) and stats(pg)[1] >= 0.5)]
print(f"\npages with dot-leader fraction >= 0.5: {dl}")

store.close()
