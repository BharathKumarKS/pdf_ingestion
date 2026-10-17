"""Diagnose E3 properly: restrict the check to each parent's OWN doc_items."""
import json, sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, REPO)

from docling.document_converter import DocumentConverter      # noqa: E402
from docling.chunking import HybridChunker                    # noqa: E402
from docling_core.transforms.chunker.tokenizer.huggingface import (   # noqa: E402
    HuggingFaceTokenizer,
)
from src.core.config import Settings                          # noqa: E402
from src.pdf_ingestion.parent_chunker import _item_texts, _build_page_map  # noqa: E402

PDF = f"{REPO}/data/base_textbooks/test_book.pdf"
doc = DocumentConverter().convert(source=PDF).document
item_texts = _item_texts(doc)
item_page = {}
for el, _ in doc.iterate_items():
    prov = getattr(el, "prov", None)
    if prov:
        item_page[el.self_ref] = min(p.page_no for p in prov)

tok = HuggingFaceTokenizer.from_pretrained(
    model_name="sentence-transformers/all-MiniLM-L6-v2", max_tokens=5000
)
raw = list(HybridChunker(tokenizer=tok).chunk(doc))

bad, checked, skipped = [], 0, 0
for i, ck in enumerate(raw):
    pm = _build_page_map(ck, item_texts)
    cursor = 0
    for di in ck.meta.doc_items:
        t = item_texts.get(di.self_ref, "")
        if not t:
            skipped += 1
            continue
        pos = ck.text.find(t, cursor)
        if pos < 0:
            bad.append({"parent": i, "ref": di.self_ref, "why": "not located"})
            continue
        cursor = pos + len(t)
        claimed = None
        for start in sorted(pm):
            if start <= pos:
                claimed = pm[start]
        true_page = item_page.get(di.self_ref)
        checked += 1
        if claimed != true_page:
            bad.append({"parent": i, "ref": di.self_ref, "pos": pos,
                        "claimed": claimed, "true": true_page,
                        "n_prov": len(di.prov),
                        "prov": [(p.page_no, tuple(p.charspan)) for p in di.prov],
                        "text": t[:60]})
print(json.dumps({"elements_checked": checked, "formula_skipped": skipped,
                  "mismatches": len(bad), "examples": bad[:8]}, indent=2))
