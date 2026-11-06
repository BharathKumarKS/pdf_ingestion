"""Live end-to-end dry run: drive the real Streamlit app headlessly with AppTest (ONE query per process).

Usage:  python logs/p1/step10/demo_dryrun.py "<query>"
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "src/frontend/streamlit_app.py"
q = sys.argv[1] if len(sys.argv) > 1 else "What is Newton's second law?"

t0 = time.time()
at = AppTest.from_file(APP, default_timeout=600)
at.run()
assert not at.exception, [e.value for e in at.exception]

at.text_area[0].set_value(q)
for b in at.button:
    if b.label.strip().lower().startswith("search"):
        b.click()
        break
at.run()
dt = time.time() - t0
print(f"[{dt:.0f}s] query={q!r}  exception={bool(at.exception)}")
for e in at.exception:
    print("  EXCEPTION:", e.value[:800])
for e in at.error:
    print("  ERROR banner:", e.value[:400])
for w in at.warning:
    print("  WARN banner:", w.value[:300])
md = [m.value for m in at.markdown if isinstance(m.value, str) and m.value.strip()]
print(f"  markdown blocks: {len(md)}")
# The answer is the longest markdown block; the citations/sources follow it.
md_sorted = sorted(md, key=len, reverse=True)
for i, blk in enumerate(md_sorted[:3]):
    print(f"\n--- markdown block #{i+1} (len {len(blk)}) ---")
    print(blk[:1400])
