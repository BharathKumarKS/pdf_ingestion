"""Counter-evidence for the verifier's three logic_errors and its C2 refutation."""
import json, subprocess, sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, REPO)

from docling.document_converter import DocumentConverter     # noqa: E402
from docling.chunking import HybridChunker                   # noqa: E402
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer  # noqa: E402
from src.core.config import Settings                         # noqa: E402
from src.pdf_ingestion.parent_chunker import _item_texts, _build_page_map  # noqa: E402

PDF = f"{REPO}/data/base_textbooks/test_book.pdf"
out = {}
doc = DocumentConverter().convert(source=PDF).document
item_texts = _item_texts(doc)
item_page, item_owning_parent = {}, {}
tok = HuggingFaceTokenizer.from_pretrained(
    model_name="sentence-transformers/all-MiniLM-L6-v2", max_tokens=5000)
raw = list(HybridChunker(tokenizer=tok).chunk(doc))

# ---- (1) Were the 20 "mismatches" elements that are NOT in that parent? -----
global_scan_mismatches, not_member = [], 0
for i, ck in enumerate(raw):
    pm = _build_page_map(ck, item_texts)
    member = {d.self_ref for d in ck.meta.doc_items}
    for el, _ in doc.iterate_items():
        prov = getattr(el, "prov", None)
        t = getattr(el, "text", None)
        if not (prov and t) or t not in ck.text:
            continue
        pos = ck.text.find(t)
        claimed = None
        for start in sorted(pm):
            if start <= pos:
                claimed = pm[start]
        true_page = min(p.page_no for p in prov)
        if claimed != true_page:
            global_scan_mismatches.append({"parent": i, "ref": el.self_ref})
            if el.self_ref not in member:
                not_member += 1
out["1_global_scan_false_positives"] = {
    "mismatches_reported": len(global_scan_mismatches),
    "of_which_element_is_NOT_a_member_of_that_parent": not_member,
    "sample": global_scan_mismatches[:3],
}

# ---- (2) Character-level agreement: which element OWNS each sampled position? ----
disagree = total = 0
for i, ck in enumerate(raw):
    pm = _build_page_map(ck, item_texts)
    spans = []
    cursor = 0
    for di in ck.meta.doc_items:
        t = item_texts.get(di.self_ref, "")
        pos = ck.text.find(t, cursor) if t else -1
        if pos < 0:
            spans.append((cursor, cursor, min(p.page_no for p in di.prov)))
            continue
        spans.append((pos, pos + len(t), min(p.page_no for p in di.prov)))
        cursor = pos + len(t)
    for p in range(0, len(ck.text), 5):
        owner_page = None
        for a, b, pg in spans:
            if a <= p < b:
                owner_page = pg
                break
        if owner_page is None:
            continue
        claimed = None
        for start in sorted(pm):
            if start <= p:
                claimed = pm[start]
        total += 1
        if claimed != owner_page:
            disagree += 1
out["2_char_level_agreement"] = {"positions_sampled": total, "disagreements": disagree}

# ---- (3) Formula attribution: is a formula's page present in page_map? -------
formula_total = formula_present = 0
for i, ck in enumerate(raw):
    pm = _build_page_map(ck, item_texts)
    cursor = 0
    for di in ck.meta.doc_items:
        t = item_texts.get(di.self_ref, "")
        pos = ck.text.find(t, cursor) if t else -1
        if pos < 0:
            pos = cursor
        else:
            cursor = pos + len(t)
        if not t and di.prov:                      # a formula element
            formula_total += 1
            want = min(p.page_no for p in di.prov)
            if pm.get(pos) == want:
                formula_present += 1
out["3_formula_page_recorded"] = {"formula_elements": formula_total,
                                  "page_present_in_map_at_cursor": formula_present}

# ---- (4) Is _page_for_offset defined at module level? -----------------------
src = Path(REPO, "src/pdf_ingestion/chunker.py").read_text().splitlines()
out["4_page_for_offset_definition"] = [
    f"line {n}: {ln}" for n, ln in enumerate(src, 1) if ln.startswith("def _page_for_offset")
]

# ---- (5) Test counts --------------------------------------------------------
r = subprocess.run(["uv", "run", "pytest", "tests/test_parent_chunker.py",
                    "tests/test_semantic_chunker.py", "-q", "-m", "not slow"],
                   cwd=REPO, capture_output=True, text=True)
out["5_test_counts"] = r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-300:]

print(json.dumps(out, indent=2, default=str))
