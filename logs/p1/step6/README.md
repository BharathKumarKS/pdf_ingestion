# Step 6 evidence — §D4 per-PDF-page numbering

**Claim:** the parent-aware path (E2/E1) collapses the §D4 page-number offset. The old ingest path
inferred a chunk's `page_number` from its **start offset** (`chunker._page_for_offset`), which is
off by ±1 where the chunker merged across page boundaries. The new path reads `page_number` from
Docling's per-element provenance.

**Method.** `probe_page_numbering.py` locates each chunk in the PDF using an **independent
extractor** — PyMuPDF page text via `PageStore` — which never sees the page numbers under test.
The claim is precise: `page_number` is the page of the chunk's **start**, so the probe tests the
chunk's **head** (opening words). A head the PyMuPDF text cannot locate (Docling serialises bullet
outlines/formulas differently) is recorded separately as `head_not_locatable` — an oracle artifact,
not evidence about the page number — with a mid/tail fallback so nothing is hidden.

**Both paths on the same unit.** An independent reviewer flagged the first version: it compared the
old tool's *first-chunk-per-page* sampling against the new path's *every-child* sampling, which is
not apples-to-apples. The probe now measures **both** samplings for **both** paths.

## Result

| path | sampling | n | offset 0 | offset −1 | other |
|---|---|---|---|---|---|
| old (deployed DB) | all chunks | 5047 | 1888 (**71.5%**) | 333 (12.6%) | +1: 322, +2: 73, +3: 20, −2: 3 |
| old (deployed DB) | first per page | 756 | 230 (54.4%) | 192 (45.4%) | +1: 1 |
| **new (parent-aware)** | **all children** | 3796 | **2150 (99.95%)** | **1 (0.05%)** | — |
| new (parent-aware) | first per page | 933 | 547 (**100%**) | 0 | — |

The offset collapses to 0 on **both** units. Note what the reviewer's fix revealed: the old path's
"45% at −1" was an artifact of the first-chunk-per-page sampling — the first chunk of a page is
exactly the one that straddled the boundary. Over **all** its chunks the old path spreads **both**
ways (71.5% at 0, 12.6% at −1, 12.2% at +1, tail to ±3); the new path collapses all of it to 0.

**Robustness on the unlocatable heads.** For the 1645 new-path heads the oracle cannot locate, the
mid/tail fallback is +0: 785, +1: 148, +2: 1, −1: 1 — page-0 or a page-break span, with **one** −1.
So that subset hides no wrong-page cluster. `children_without_page_number = 0` — every child has a
page.

Artifacts: `realbook.json` (both paths, both samplings), `children.json` (cached parse — re-run
without re-parsing), `testbook.json`, `diag_ambiguous.py`, `probe_page_numbering.py`.

**Scope note:** this verifies the parent-aware path in isolation. It is not yet the deployed
ingest — `store.ingest_document` still calls the legacy `chunk_document` / `build_page_map`, which
Step 7 rewires. So Step 6 changes **no source**; the "remove the dead path" half of the plan's
Step 3 note moves to Step 7 with the rewire.
