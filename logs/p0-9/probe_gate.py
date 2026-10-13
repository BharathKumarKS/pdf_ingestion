"""Live probe: does the back-matter gate flag the index and only the index?

Imports the real gate from scripts/validate_eval_calibration.py and runs it over
pages we know the answer for. Read-only; no judge calls.
"""
import importlib.util, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec); spec.loader.exec_module(vec)

PDF = str(ROOT / "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf")
store = vec.PageStore(PDF)
n = store.n_pages
start = vec.back_matter_start(store)

# The Feynman Vol 1 index occupies PDF pages 937-967 (verified against the text).
EXPECT_GATED = list(range(937, 968))
EXPECT_CONTENT = [11, 20, 22, 30, 33, 100, 112, 134, 200, 300, 500, 599, 628, 652,
                  816, 904, 910, 930, 933, 935, 936]

print(f"PDF has {n} pages; back_matter_start = {start}\n")
bad = 0
print("index pages (must be gated):")
for pg in EXPECT_GATED:
    got = pg >= start
    if not got:
        bad += 1
        print(f"  p{pg:4d}  NOT gated  <-- MISS")
print(f"  ... {len(EXPECT_GATED)} pages, all gated" if bad == 0 else "")
print("\ncontent/front pages (must NOT be gated):")
for pg in EXPECT_CONTENT:
    got = pg >= start
    if got:
        bad += 1
        print(f"  p{pg:4d}  GATED  <-- FALSE POSITIVE  | {' '.join(store.text(pg).split())[:60]}")
print(f"  ... {len(EXPECT_CONTENT)} pages, none gated" if bad == 0 else "")

# End-to-end: the gate must cap the p944 index YES at PARTIAL, and leave content alone
v944, _ = vec.apply_page_gate(944, store.text(944), "YES", "index mentions Schrodinger", store)
v200, _ = vec.apply_page_gate(200, store.text(200), "YES", "answers it", store)
print(f"\napply_page_gate(p944, YES) -> {v944}   (index: must be PARTIAL)")
print(f"apply_page_gate(p200, YES) -> {v200}   (content: must stay YES)")

store.close()
ok = bad == 0 and v944 == "PARTIAL" and v200 == "YES"
print(f"\n{'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
