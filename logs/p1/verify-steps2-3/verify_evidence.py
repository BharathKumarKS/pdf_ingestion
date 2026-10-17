"""Consolidated evidence pack for the independent verifier of commits 9a788a2 (Step 2) + 7a776cb (Step 3).

Prints compact, raw evidence for each claim the verifier is asked to adjudicate. Run:
    uv run python /Users/bharathkumar/.hermes/cache/scratch/verify_evidence.py
"""
import json, sys
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, REPO)

from docling.document_converter import DocumentConverter            # noqa: E402
from src.core.config import Settings                                # noqa: E402
from src.pdf_ingestion.chunker import SemanticChunker               # noqa: E402
from src.pdf_ingestion.parent_chunker import ParentChunker          # noqa: E402

PDF = f"{REPO}/data/base_textbooks/test_book.pdf"
out = {}

# ── E1: is prov.charspan relative to the element's own text? ────────────────
doc = DocumentConverter().convert(source=PDF).document
rows = []
for el, _ in doc.iterate_items():
    prov = getattr(el, "prov", None)
    txt = getattr(el, "text", None)
    if prov and txt:
        rows.append({
            "ref": el.self_ref, "len_text": len(txt),
            "prov": [(p.page_no, tuple(p.charspan)) for p in prov],
            "last_charspan_end": max(p.charspan[1] for p in prov),
        })
        if len(rows) >= 4:
            break
out["E1_charspan_is_element_relative"] = rows

# ── E2: formula elements — text None but provenance present? ────────────────
formula = []
for el, _ in doc.iterate_items():
    if str(getattr(el, "label", "")) == "DocItemLabel.FORMULA":
        formula.append({
            "ref": el.self_ref,
            "text": getattr(el, "text", None),
            "n_prov": len(getattr(el, "prov", []) or []),
            "prov_pages": [p.page_no for p in (getattr(el, "prov", []) or [])],
        })
        if len(formula) >= 3:
            break
out["E2_formula_elements"] = formula

# ── E3: does page_for_offset agree with the element's own provenance? ───────
doc2, parents = ParentChunker(Settings()).convert(PDF)
item_page = {}
for el, _ in doc2.iterate_items():
    prov = getattr(el, "prov", None)
    if prov:
        item_page[el.self_ref] = min(p.page_no for p in prov)

mismatch, checked = [], 0
for parent in parents:
    for el, _ in doc2.iterate_items():
        if el.self_ref not in item_page:
            continue
        t = getattr(el, "text", None)
        if not t or t not in parent.text:
            continue
        pos = parent.text.find(t)
        claimed = parent.page_for_offset(pos)
        true_page = item_page[el.self_ref]
        checked += 1
        if claimed != true_page:
            mismatch.append({"parent": parent.parent_id, "ref": el.self_ref,
                             "claimed": claimed, "element_first_page": true_page})
out["E3_page_map_agreement"] = {
    "elements_checked": checked, "mismatches": len(mismatch), "examples": mismatch[:5],
}
out["E3_spanning_parent_example"] = {
    "parent_id": parents[0].parent_id, "pages": parents[0].page_numbers,
    "page_map": dict(list(sorted(parents[0].page_map.items()))[:6]),
}

# ── E4/E5: chonkie tiling, and no cross-parent merge ───────────────────────
cfg0 = Settings(min_chunk_tokens=0)
children = SemanticChunker(cfg0).chunk_parents("d", "global", parents)
bad_slice = bad_contig = bad_owner = 0
by_parent = {p.parent_id: p for p in parents}
for c in children:
    owner = by_parent[c.parent_id]
    if owner.text[c.char_start:c.char_end].strip() != c.text:
        bad_slice += 1
    if not (0 <= c.char_start < c.char_end <= len(owner.text)):
        bad_owner += 1
for p in parents:
    kids = [c for c in children if c.parent_id == p.parent_id]
    if kids and (kids[0].char_start != 0 or kids[-1].char_end != len(p.text)):
        bad_contig += 1
    for a, b in zip(kids, kids[1:]):
        if a.char_end != b.char_start:
            bad_contig += 1
merged = SemanticChunker(Settings(min_chunk_tokens=10_000)).chunk_parents("d", "global", parents)
out["E4_tiling"] = {"children": len(children), "bad_slice": bad_slice,
                    "bad_owner_span": bad_owner, "bad_contiguity_or_coverage": bad_contig}
out["E5_merge"] = {"parents": len(parents), "merged_children": len(merged),
                   "parents_with_!=1_child": sum(
                       1 for p in parents if len([c for c in merged if c.parent_id == p.parent_id]) != 1)}

# ── E6: legacy flat path ───────────────────────────────────────────────────
flat = SemanticChunker(cfg0).chunk_document("d", "global", parents[6].text)
out["E6_legacy_path"] = {
    "chunks": len(flat),
    "parent_fields_all_none": all(c.parent_id is None and c.parent_text is None for c in flat),
    "indices_sequential": [c.chunk_index for c in flat] == list(range(len(flat))),
    "first_starts_at_0": flat[0].char_start == 0,
    "slice_matches": all(parents[6].text[c.char_start:c.char_end].strip() == c.text for c in flat),
}

# ── E7: cluster tool-call protocol (why the first verifier attempt died) ───
import httpx
try:
    r = httpx.post("http://10.0.10.70:8000/v1/chat/completions", json={
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 16, "temperature": 0,
    }, timeout=60)
    out["E7_cluster_basic"] = {"status": r.status_code}
except Exception as exc:
    out["E7_cluster_basic"] = {"error": str(exc)}

print(json.dumps(out, indent=2, default=str))
