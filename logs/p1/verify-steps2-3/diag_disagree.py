"""Why do 114 sampled positions disagree? Hypothesis: multi-prov (page-spanning) elements.

The previous check gave each element a SINGLE page (min of its prov pages). But an element that
crosses a page break legitimately spans two pages, and _build_page_map splits it at the internal
charspan boundary. The correct oracle is per-character WITHIN the element.
"""
import json, sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, REPO)

from docling.document_converter import DocumentConverter     # noqa: E402
from docling.chunking import HybridChunker                   # noqa: E402
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer  # noqa: E402
from src.pdf_ingestion.parent_chunker import _item_texts, _build_page_map  # noqa: E402

doc = DocumentConverter().convert(source=f"{REPO}/data/base_textbooks/test_book.pdf").document
item_texts = _item_texts(doc)
tok = HuggingFaceTokenizer.from_pretrained(
    model_name="sentence-transformers/all-MiniLM-L6-v2", max_tokens=5000)
raw = list(HybridChunker(tokenizer=tok).chunk(doc))

multi_prov_inside = multi_prov_outside = other = total = 0
examples = []
for i, ck in enumerate(raw):
    pm = _build_page_map(ck, item_texts)
    spans = []
    cursor = 0
    for di in ck.meta.doc_items:
        t = item_texts.get(di.self_ref, "")
        pos = ck.text.find(t, cursor) if t else -1
        if pos < 0:
            continue
        spans.append((pos, pos + len(t), di))
        cursor = pos + len(t)
    for p in range(0, len(ck.text), 5):
        owner = None
        for a, b, di in spans:
            if a <= p < b:
                owner = (a, di)
                break
        if owner is None:
            continue
        a, di = owner
        d = p - a                                    # offset within the element's own text
        # TRUE page: the prov entry whose charspan contains d (Docling ground truth)
        true_page = None
        for pr in di.prov:
            if pr.charspan[0] <= d < pr.charspan[1]:
                true_page = pr.page_no
                break
        if true_page is None:
            continue
        claimed = None
        for start in sorted(pm):
            if start <= p:
                claimed = pm[start]
        total += 1
        if claimed != true_page:
            other += 1
            if len(examples) < 5:
                examples.append({"parent": i, "ref": di.self_ref, "pos": p,
                                 "claimed": claimed, "true": true_page})

print(json.dumps({
    "positions_checked": total,
    "disagreements_with_per_character_oracle": other,
    "examples": examples,
}, indent=2))
