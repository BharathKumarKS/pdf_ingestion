# P0-9 Session 3c — pre-registration (overview path)

> **Rule (D1): targets are fixed *before* generating.** This file is written and
> committed before any generation or scan call, so the numbers below cannot be
> tuned after the fact. Anything changed later must be changed *here* with a date.

Written: 2026-10-13 · branch `feat/p0-9-gold-dataset-v2`

---

## Scope of 3c

The sessions file split P0-9 into a chain. **3c is now split in two**, because the
visual lane turned out to need a model/endpoint change of its own (verified
2026-10-13 — see §"Why visual moved to 3d"):

| Session | Scope | Status |
|---|---|---|
| **3c** | **Overview generation path** (topic → exhaustive book-wide scan) | this file |
| **3d** | Visual lane: ColQwen3 text+image query path (§B4) + visual generation + labels + judge variant + metric | deferred — see `p0-9-SESSIONS.md` |

Rationale for the split: 3c is *generation + a scan*; 3d is *a model swap, a
re-embed, a new embedder client, and a metric* — different cost class, different
failure modes, and it is currently blocked on the cluster (below).

---

## Pre-registered targets (per type)

Type mix is currently **emergent**, not designed: 55 factual / 40 multihop /
8 overview, because the multipage prompt asks for *connection* questions and the
post-hoc classifier (`classify_question()`) therefore labels them `multihop`.

| query_type | current | **target after 3c** | source |
|---|---|---|---|
| factual | 55 | 55 (unchanged) | single-page generator |
| multihop | 40 | 40 (unchanged) | distant-triple generator |
| **overview** | 8 | **40** | **new: topic → book-wide scan (3c)** |
| visual | 0 (v1's 7 are unlabelled) | 35 | deferred to **3d** |
| **answerable total** | 103 | **135 after 3c** (170 after 3d) | |

Overview target **40** is chosen to *match multihop* (the sessions file's words:
"targeting ~40, matching multihop"), so the per-type comparison in Session 4 has a
balanced design rather than an 8-vs-40 one.

## Pre-registered negatives

Negatives are the only source of the abstention metric. The schema test
(`tests/test_gold_schema.py`) requires **≥15%**.

| | count | note |
|---|---|---|
| current | 23 | 17 clean, 6 flagged `needs_review` (Session 3b) |
| **target after 3c** | **32–36** | +9–13, to hold ≥15% as the set grows |

The seed list (`scripts/generate_negatives.py::_SEEDS`) is extended 8 → **12 seeds
per tier**. The generator accepts `per_tier = n // 3`, so `--n 36` yields **up to 36**
scan-verified negatives. Rejections are expected and correct (a `near_miss` the book
*does* answer must be rejected), so **32 is the floor to aim for, 36 the cap**.

Arithmetic (at 36): answerable 135 + 36 = 171 → 36/171 = **21.1%** after 3c.
When 3d adds ~35 visual queries (answerable 170): 36/206 = **17.5%**, still ≥15%.
The binding rule is therefore **"negatives ≥15% of the assembled v2, recomputed at
Session 4"**, not a frozen count.

---

## Overview method (settled: the plan's §D approach)

> §D: "pick a *topic*, then an exhaustive book-wide scan for all pages on it."

**Why not the alternatives:**
- Generating from a single page is what the existing single-page path does — it
  structurally cannot produce a book-spanning question.
- The distant-triple multipage path asks for *connection* questions; that is the
  multihop lane, and it is the reason the classifier says `multihop`. Reusing it
  would just relabel.
- Sourcing from RAPTOR summaries is attractive ("the kind the RAPTOR summary nodes
  answer") but **the RAPTOR tree's leaf links are stale**: `raptor_nodes.child_ids_json`
  resolves L2→L1 and L3→L2 as node ids, but L1's 5,048 leaf refs match only **4**
  rows in `chunks.id`. So the tree cannot supply page labels, and the labels must
  come from the scan anyway. Topics are therefore taken from the book itself.

**Topic source (grounded, not invented):** the chunk text carries markdown section
headings (`## 4-1 What is energy?`, `## Conservation of Energy`, …). 3c extracts
these, dedupes them, and has the generator LLM propose **40 book-spanning topics**
(concepts that recur across chapters) from that list — one LLM call — then writes
**one overview question per topic** — 40 calls. No topic is invented from outside
the book.

**Labels (exhaustive book-wide scan):** each overview question is scanned with
`scan_query()` in an overview mode:
- coarse pass at a **smaller stride** (`--overview-stride`, default **4**) so
  nearly every page is judged, not every 15th;
- a **term-bearing sweep** — every page whose text contains the question's key
  terms (the Session 3b trick that recovered the negatives), which guarantees the
  topic's own pages are covered even if the coarse stride misses them;
- the usual dense pass (±`--scan-window`) around all hot pages.

`relevant_pages` = the union of YES pages found (via `expand_gold_labels.py`).

**Judge criterion (overview variant):** the standard prompt asks "is this page
genuinely useful for answering the question", which is wrong for a question no
single page answers. Overview queries use a variant asking whether the page
**substantively discusses the topic / contributes to the book's treatment of it**
(YES) versus mentions it in passing (PARTIAL) or is unrelated (NO). The verdict
cache is keyed on a prompt hash, so the variant cannot be served a standard verdict.

---

## Artifacts 3c must produce

| Artifact | Content |
|---|---|
| `data/eval_queries_gold_overview.json` | 40 overview entries, `query_type=overview`, `expected_route=raptor`, ids `ovw-NNN` |
| `data/eval_queries_gold_overview_expanded.json` | the same 40 with `relevant_pages` filled by the book-wide scan |
| `data/eval_negatives.json` | grown 23 → 32 |

Kept **separate** from `eval_queries_gold.json` so the already-scanned 103 are not
regenerated; Session 4 merges overview + visual + the existing set into
`data/eval_queries_v2.json`.

## Definition of done (3c)

1. Targets above pre-registered **before** generating. ✅ (this file)
2. Overview questions generated (40) and **every one scan-labelled**.
3. Negatives at ≥15% of the assembled set.
4. `uv run pytest tests/ -q -m "not slow"` at the regression floor (221 pass / 5 pre-existing fail).
5. Commit + HANDOFF refresh + `/new`.

---

## Why visual moved to 3d (verified 2026-10-13)

`GET http://10.0.10.70:8000/routes` advertises:

```
colpali_models  : ["TomoroAI/tomoro-colqwen3-embed-4b"]
colpali_endpoint: http://ansatz:8123/embed-image/v1/multivector-embeddings
```

so ColQwen3 is the router's registered visual model. **But the endpoint is down:**
every request shape returns HTTP 500 in ~3.2 s — text with `input_type=auto`, with
`input_type=text`, with `is_query=true`, plain `input`, and a real base64 page image.
The `colbert` endpoint on the same router returns 200, so the router is up and the
colpali upstream is the failure.

Two facts that make visual its own session, not a sub-task:

1. **§B4 is blocked on the cluster**, not on our code — no text→visual query path
   exists (`colpali_embedder` exposes only `embed_query_image`).
2. **ColQwen3 ≠ colpali-v1.2 embedding space**, so using ColQwen3 for queries means
   re-embedding all 945 page images (a visual re-ingest, `IMPROVEMENTS.md` §I1).
   The no-re-ingest alternative is to add a *text-query* path to the existing local
   `colpali-v1.2` (`colpali_engine` supports `process_queries` for text, same space
   as the stored vectors). That fork is 3d's first decision.

**Do not** use `sv_ray_cluster_access` / `embed_colpali` — `IMPROVEMENTS.md` §I8:
SupportVectors IP, "reference only, keep gitignored… not importable here (needs
`svlearn`)". The repo's pattern is a direct HTTP client (`colbert_embedder.ClusterColBERTEmbedder`).
