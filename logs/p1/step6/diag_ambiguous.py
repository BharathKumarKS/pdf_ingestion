"""Why does the PyMuPDF oracle fail to locate some children? (Step 6 diagnosis)

Not part of the deliverable — a one-off to decide whether the ambiguous children are an oracle
extraction mismatch (Docling text vs PyMuPDF text differ) or evidence of a wrong page number.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.config import Settings            # noqa: E402
from src.pdf_ingestion.chunker import SemanticChunker       # noqa: E402
from src.pdf_ingestion.parent_chunker import ParentChunker  # noqa: E402

spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts" / "validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vec)

PDF = ROOT / "data" / "base_textbooks" / "test_book.pdf"
store = vec.PageStore(str(PDF))


def norm(s: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]", " ", " ".join(s.split()).lower()) + " "


pdf = {p: norm(store.text(p)) for p in range(1, store.n_pages + 1)}
cfg = Settings()
doc, parents = ParentChunker(cfg).convert(str(PDF))
children = SemanticChunker(cfg).chunk_parents("p", "global", parents)

for ci in (2, 5, 8, 17):
    ch = [c for c in children if c.chunk_index == ci][0]
    needle = norm(ch.text)[1:70].strip()
    found = [p for p in pdf if needle in pdf[p]]
    # Try the child's LAST 70 chars and a middle slice too — is any part locatable?
    tail = norm(ch.text).strip()[-70:]
    print(f"--- chunk {ci}  claimed_page={ch.page_number} ---")
    print("  child text :", repr(ch.text[:100]))
    print("  head needle:", repr(needle))
    print("  found head on pages:", found)
    print("  tail needle:", repr(tail), "-> pages:", [p for p in pdf if tail in pdf[p]])
    print("  PDF p", ch.page_number, ":", repr(store.text(ch.page_number)[:140]))
    print()

store.close()
