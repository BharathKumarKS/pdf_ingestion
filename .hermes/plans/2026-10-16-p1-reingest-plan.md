# P1 — the re-ingest (E1/E2/E3/E5 + §D4 + §I1). Execution plan.

**Status:** planned 2026-10-16. **Steps 0–7 done** (P1-a config + `cluster_embedder`; E1 semantic
chunking; E2 parents; E3 late chunking; E5 `is_content`; §D4 page numbering; the schema + write
path) **plus Step 7b, the query-side dense-lane switch (§E6), done 2026-10-17** — the funnel and
the §D13 ablation can now read a rebuilt collection. **Next: Step 8 (the run).** Supersedes the
"Next: the re-ingest" line in `HANDOFF.md`.
**Scope owner decisions taken 2026-10-16** (all four settled — see §2).

> Read `ARCHITECTURE.md` §8 (invariants/traps) and `IMPROVEMENTS.md` §E before the first change.
> This plan is the *how*; `IMPROVEMENTS.md` §E1–§E5 stays the *why*.

---

## 1. Objective and definition of done

Rebuild the text index so that the three defects that currently swamp every metric are gone:

| Defect | Where | Removed by |
|---|---|---|
| Size-based sentence chunking cuts mid-thought | `chunker.py` (chonkie `SentenceChunker`) | **E1** semantic chunking |
| No parent/child hierarchy — heading structure parsed then discarded | `parser.py` → flat pages | **E2** Docling `HybridChunker` parents |
| Chunks lose their antecedent context ("This …", "these weights …") | `embedder.py` encodes each chunk in isolation | **E3** late chunking |
| Front/back matter retrievable; page bounds cannot split a mixed page | `min_content_page`/`max_content_page` | **E5** chunk-level `is_content` |
| `page_number` is chunk-start fuzz, off by 0/−1 on ~45% of pages | `chunker._page_for_offset` | **§D4** provenance-based per-page numbering |

**Definition of done:** a new Qdrant collection on the cluster holds the rebuilt index; `tests/` at the floor;
the funnel A/B and the §D13 reranker ablation re-run against it and recorded in `HANDOFF.md` + `IMPROVEMENTS.md`.

---

## 2. Settled decisions (evidence in parentheses)

| # | Decision | Value | Why |
|---|---|---|---|
| R1 | Rebuilt index lives on the **cluster**, in a **new collection**, old one kept | `10.0.10.65`, `knowledge_base_v2` | the eval reads the cluster; a new name is reversible and lets old-vs-new be compared |
| R2 | Dense embedder | `Qwen/Qwen3-Embedding-0.6B` (1024d) via `10.0.10.70:8123` | newest served model; MRL-capable (32–1024) → keeps the two-dim design |
| R3 | MRL truncation | client-side 1024 → 64, re-normalised | the endpoint **ignores** a `dimensions` param (verified: 64/256/512 all return 1024) |
| R4 | ColBERT | `lightonai/GTE-ModernColBERT-v1` (128d) | already served; §I1 upgrade; 128d drop-in |
| R5 | Sparse | `Qdrant/bm42-all-minilm-l6-v2-attentions` | §I1 upgrade; already served |
| R6 | E3 method | **late chunking** via cluster per-token embeddings | see §3 — it *is* available; no LLM calls |
| R7 | Code structure | mirror the class repo `Labs/Week_6/sv_rag_pipeline/src/svrag/` | explicit instruction; module-per-stage + orchestrator + `models.py` |

### 2.1 Correction recorded (do not re-derive)

An earlier reading concluded "the cluster cannot do late chunking". **That was wrong.**
`POST /embed-text/v1/embeddings` accepts `return_token_embeddings: true` and then returns
**per-token, native-dimension** vectors — verified live 2026-10-16:

```
jinaai/jina-embeddings-v2-base-en  ->  (1, 22, 768)
Qwen/Qwen3-Embedding-0.6B         ->  (1, 19, 1024)
```

Batching works; and a **local** jina tokenizer produced exactly 22 tokens for the same text as the
API returned 22 vectors, so local `offset_mapping` aligns 1:1 with the API's token vectors. That
alignment is the precondition late chunking needs. The class repo documents this exact path
(`Labs/Week_3/chunking_pipeline/docs/notebooks/02-contextual_and_late_chunking.ipynb`, cell 13).

**Consequence:** late chunking and MRL compose. Mean is linear, so `mean(tok)[:64] == mean(tok[:64])`
— a 64d MRL view of a late-chunked vector is well-defined. R2+R3+R6 hold simultaneously.

---

## 3. Target pipeline (after)

```
PDF ──Docling DocumentConverter──> DoclingDocument
    ──Docling HybridChunker(max_tokens≈5000)──> ParentChunk[]   (E2: heading boundaries,
                                                                  + prov page_no per element)
        └─ per parent ──chonkie SemanticChunker──> ChildChunk[] (E1: topic-coherent,
                                                                  char span in parent text)
                       ──cluster per-token (return_token_embeddings)──> mean-pool per child span (E3)
                       ──slice 1024→64, renorm──> dense_64                          (R3)
    ──> Qdrant knowledge_base_v2 {dense_64, dense_1024, colbert, sparse} + SQLite chunks
```

Per child we store: `text`, `parent_id`, `parent_text`, `page_number` (provenance, §D4),
`is_content` (E5), `chunk_index`, `char_start/char_end` (relative to the parent).

---

## 4. Module map (class repo → this repo)

| Class repo (`src/svrag/`) | New/edited here | Notes |
|---|---|---|
| `document_converter.py` | **new** `src/pdf_ingestion/parent_chunker.py` | Docling `DocumentConverter` + `HybridChunker`; returns parents **with provenance** |
| `semantic_chunker.py` | **rewrite** `src/pdf_ingestion/chunker.py` | `SentenceChunker` → `SemanticChunker`; keep span tracking (ARCHITECTURE trap 4) |
| `late_chunk_embedder.py` | **new** `src/pdf_ingestion/late_chunk_embedder.py` | cluster per-token path + local tokenizer for offsets |
| — | **new** `src/pdf_ingestion/cluster_embedder.py` | dense cluster client: pooled **and** per-token, MRL slice. §6 pattern (Stub + Cluster + factory + `reset_*`) |
| `models.py` | **new** `src/pdf_ingestion/models.py` | `ParentChunk`, `ChildChunk`, `EnrichedChunk` |
| `chunking_pipeline.py` | **new** `src/pdf_ingestion/chunking_pipeline.py` | orchestrator `ChunkingPipeline.process_pdf/process_all_documents` |
| `chunking_main.py` | **edit** `scripts/ingest_base_textbook.py` | wire to the new pipeline; `--collection-name` |

`store.py` is edited **only** where the payload/schema changes (trap 10: do not refactor it).

---

## 5. Execution steps

Each step ends with: unit tests green (stubs, offline) → a small live probe → commit.

### Step 0 — scaffolding & config (no behaviour change) ✅ DONE
- `config.py`: add `sv_embed_url`, `dense_model`, `dense_dim` (1024), `dense_dim_low` (64),
  `sv_sparse_model`, `sv_colbert_model`, `late_chunk_enabled`, `parent_max_tokens`, `semantic_threshold`.
- **Do not** flip `embedding_dim` yet — the intent classifier is schema-checked against it (§6 risk R-a).
- Verify: `uv run pytest tests/ -q -m "not slow"` unchanged at the floor.

### Step 1 — `cluster_embedder.py` (foundation; everything depends on it) ✅ DONE
- `StubClusterEmbedder` (deterministic, no network) + `ClusterDenseEmbedder` (httpx, pooled + per-token).
- MRL slice helper, re-normalised.
- Factory `get_cluster_embedder` / `reset_cluster_embedder`; register in `tests/conftest.py`.
- Verify: `tests/test_cluster_embedder.py` (stub) + one live probe asserting the per-token shape and
  the local-tokenizer alignment from §2.1.

### Step 2 — E2 `parent_chunker.py` ✅ DONE 2026-10-17
- Wrap Docling; expose `convert(pdf) -> (DoclingDocument, ParentChunk[])` where each `ParentChunk`
  carries `text`, `headings`, and a **char→page map** built from `meta.doc_items[].prov[].charspan/page_no`.
- Verify: on `test_book.pdf` — **42** parents, every parent has ≥1 page, page numbers in range.
  (`tests/test_parent_chunker.py`, 9 fast + 1 slow.) **The earlier "43" in this plan was measured with
  Docling's default `max_tokens=512`; at the configured `parent_max_tokens=5000` the count is 42**
  (Docling 2.117.0, 2026-10-17) — the figure, not the design, was stale.

### Step 3 — E1 `chunker.py` rewrite (SemanticChunker) ✅ DONE 2026-10-17
- chonkie `SemanticChunker(threshold=…)` over each parent's text; children keep `start_index/end_index`.
- Keep the micro-chunk merge behaviour and the `TextChunk` contract; add `parent_id`, `is_content`.
- Verify: children are contiguous and cover the parent; no child crosses a parent boundary.
  (`tests/test_semantic_chunker.py`, 8 fast + 1 slow — verified on `test_book.pdf`: 42 parents →
  **91 children** raw, **66** at the current `min_chunk_tokens=32`; spans tile each parent exactly.)
- **Decisions taken while building it:**
  1. **Segmentation model = chonkie's default** (`minishlab/potion-base-32M`, local + cached).
     It scores sentence-to-sentence similarity for *segmentation only*; the indexed vectors stay
     the cluster dense model (R2). Segmenting 968 pages through the cluster would be one HTTP
     call per sentence window. The plan did not specify this — recorded here as the answer.
  2. **`chunk_document` kept** as the flat full-text path for `store.py` until Step 7, now backed
     by the same semantic chunker (`parent_id`/`parent_text` stay `None`). `TextChunk` gained
     `parent_id`, `parent_text`, `is_content` — all defaulted, so the 5 existing call sites and
     their tests are untouched.
  3. **`page_number` now comes from the parent's provenance map** in the parent-aware path (Step
     6's change lands here because this is where children are created); `_page_for_offset` stays
     only for the legacy flat path. Step 6 therefore becomes verification + removing the dead path.
- **Registered:** the inherited `min_chunk_tokens=32` merges 91 → 66 children on `test_book.pdf`
  (−27%, avg 312 → 430 chars) — `IMPROVEMENTS.md` §E1. Threshold left at 32 pending the funnel
  candidate-count measurement.

### Step 4 — E3 `late_chunk_embedder.py` ✅ DONE 2026-10-17
- Local tokenizer (jina **or** Qwen3 — must match the model used for the token vectors) for offsets;
  cluster call with `return_token_embeddings=True`; mean-pool the tokens overlapping each child span.
- Guard: if a child span maps to zero tokens, fall back to the parent mean (class repo does this).
- Verify: a chunk containing "This" gets a vector that differs from its isolation-embedded twin, and
  `mean(tok)[:64] == mean(tok[:64])` numerically (the MRL/linearity claim in §2.1).
- **Landed as `src/pdf_ingestion/late_chunk_embedder.py`** (+ `EnrichedChunk`; `embed_isolated` is
  the E3 control and the `late_chunk_enabled=False` path). 12 fast tests (a mock transport carrying
  the real endpoint contract) + 1 slow test (real Qwen3 tokenizer + real cluster). Suite at the
  floor (327 pass / 5 pre-existing fail). Evidence: `logs/p1/step4/`, register: `IMPROVEMENTS.md`
  §E3b, review record: `logs/p1/step4/README.md`.

- **⛔ FIRST ACTION — ANSWERED: Qwen3 ALIGNS.** The probe ran live 2026-10-17
  (`logs/p1/step4/probe_qwen3_alignment.py` → `alignment.json`): the local Qwen3 tokenizer with
  `add_special_tokens=False` yields exactly the content tokens; the endpoint returns **exactly one
  extra TRAILING `<|endoftext|>` vector** (`matrix[:-1]` is the content matrix); offsets tile the
  text; appending text leaves every earlier vector bit-identical (max |Δ| 0.0); a one-word swap
  moves index *k* and later and leaves everything before *k* bit-identical; a 5,200-token input is
  not truncated. **→ proceed as planned, 1024d + 64d; the jina fallback is not needed.** The strip
  is behaviour-neutral for pooling (the extra vector is last and never enters an offset-derived
  index list) — its value is the **count assertion**, stated as such in the module and §E3b.
- **Also measured before committing:** per-token output is ~160× the pooled payload and ~55× the
  wall time → **~48 min and ~13.6 GB of JSON** for 968 pages (`probe_late_chunk_cost.py` →
  `cost.json`); acceptable as the Step 8 background job, and the reason only *parents* get a
  per-token call. The `min_chunk_tokens=32` unit question: **6 of 66 children (9%) sit below the
  threshold** and the merge never re-checks the grown child's size (`probe_child_units.py`) — a
  measurement to settle at Step 10, not a code change now (§E1).
- **Independent verification is part of this step** (see `HANDOFF.md` → Session hygiene): run the
  verifier single-turn with evidence embedded — `openai/gpt-oss-20b` cannot sustain a multi-turn
  tool session on the cluster (harmony control tokens leak; measured 2026-10-17). **Done: round 1
  found a real defect** (a call to the non-existent `self._embed_isolated` on the zero-token-parent
  branch), fixed with a regression test; round 2 → `passed: true`.

### Step 5 — E5 `is_content`
- Reuse the `_NON_CHAPTER` list already in `store.py:1362`, promoted to a shared helper.
- Tag each child; write the flag into the Qdrant payload + SQLite; filter retrieval on it.
- Verify: `tests/test_backmatter_gate.py` extended; the known mixed page (DB 936) splits correctly.
- **IMPLEMENTED 2026-10-17** — `src/pdf_ingestion/content_filter.py`; chunker tags children;
  payload + SQLite + retrieval filter wired. Evidence `logs/p1/step5/` (probe → `evidence.json`),
  register `IMPROVEMENTS.md` §E5 "outcome". Suite 341 pass / 5 pre-existing fail. **Deviation from
  the plan, forced by measurement:** the `_NON_CHAPTER` keyword list alone does **not** catch the
  page-936 index rows (they carry no keyword), so two structural signals — an exact index heading
  and an index-table layout — were added; without them the plan's own acceptance test fails. The
  page bounds are left in place (the rule's front-matter recall gap is registered in §E5). SQLite
  `chunks.is_content` was done here although Step 7 also lists it; Step 7 now only needs
  `parent_id` + the new collection schema. Independent review (single-turn, evidence embedded,
  `openai/gpt-oss-20b`): **`passed: true`, C1–C5 confirmed, no findings**.

### Step 6 — §D4 per-PDF-page numbering
- `page_number` comes from the parent's provenance char→page map (Step 2), not `_page_for_offset`.
- Verify: re-run the §D4 measurement (first/last chunk page vs PDF page) — the 0/−1 spread should collapse.
- **VERIFIED 2026-10-17 — no source change.** The code landed in Step 3 (children take
  `page_number` from `parent.page_for_offset`), so Step 6 is the measurement only. Measured with
  `logs/p1/step6/probe_page_numbering.py` against an **independent extractor** (PyMuPDF page text
  via `PageStore`; the page numbers came from Docling provenance), head-only — the claim is that
  `page_number` is the page of the chunk's **start**. **Both paths on the same unit** (an
  independent reviewer refuted the first version for comparing "first chunk per page" against
  "every child"), on the 968-page book:

  | path | sampling | n | offset 0 | offset −1 | other |
  |---|---|---|---|---|---|
  | old (deployed DB) | all chunks | 5047 | 1888 (**71.5%**) | 333 (12.6%) | +1: 322, +2: 73, +3: 20, −2: 3 |
  | old (deployed DB) | first per page | 756 | 230 (54.4%) | 192 (45.4%) | +1: 1 |
  | **new (parent-aware)** | **all children** | 3796 | **2150 (99.95%)** | **1 (0.05%)** | — |
  | new (parent-aware) | first per page | 933 | 547 (**100%**) | 0 | — |

  The offset collapses to 0 on both units; **0** children without a page. The reviewer's fix also
  showed the old path's "45% at −1" was a first-chunk-per-page artifact — over all its chunks the
  old path spreads both ways. The 1,645 children whose head the oracle cannot locate (Docling vs
  PyMuPDF serialisation) are reported separately; their mid/tail fallback shows **one** −1, so they
  hide no wrong-page cluster. Evidence + method: `logs/p1/step6/README.md`, `realbook.json`,
  `children.json`, `testbook.json`.
- **The plan's Step 3 note ("removing the dead path") moves to Step 7.** The legacy flat path is
  **not** dead: `store.ingest_document` (`store.py:1315`) still calls `build_page_map` +
  `chunk_document`, so `_page_for_offset` and `chunk_document` can only be removed when Step 7
  rewires the ingest to the parent-aware path. Removing them here would break the live ingest.

### Step 7 — schema + write path
- `database._ensure_*`: new collection with `dense_64` + `dense_1024` + `colbert` + `sparse`
  (`dense_768` is retired; **keep the `dense_*` naming** — see §7 open question 1).
- `store.save_document`: write `dense_1024`, `is_content`, `parent_id`, `parent_text`.
- SQLite `_migrate_add_columns`: `chunks.parent_id`, `chunks.is_content`.
- Verify: `tests/test_config_invariants.py` + `test_phase1.py` updated; collection created with the 4 named vectors.
- **IMPLEMENTED 2026-10-17** — new `src/pdf_ingestion/chunking_pipeline.py` (the single ingest
  path) + `store.ingest_pdf` rewired to it; `dense_768` retired in the created schema with the
  vector name **resolved from the collection** (`store._dense_name_from`) so the deployed
  `knowledge_base` stays writable and queryable (R1); payload + SQLite carry
  `parent_id`/`parent_text`; the legacy flat path (`chunk_document` / `build_page_map` /
  `_page_for_offset`) is **deleted** — this is Step 6's deferred half. `--collection-name` added
  to `scripts/ingest_base_textbook.py`. Evidence `logs/p1/step7/` (live probe: real cluster
  dense lane + real Qwen3 tokenizer, 42 parents → 66 children, 4 named vectors, counts agree,
  `dense_64 == mrl_slice(dense_1024, 64)`); suite 356 pass / 4 pre-existing fail / 6 skip.
  Register `IMPROVEMENTS.md` §E6.
- **Two things Step 7 does NOT close** (both in §E6, both needed before Step 10):
  1. **the query side** — the UI, `main.py`, `evaluate_rag`, `funnel_boundary_recall`,
     `calibrate_eval_pages`, `why_colbert` and the intent router still embed with the retired
     local Nomic 768d model. Loud (a dimension error), not silent, and the deployed index is
     unaffected — but the funnel/ablation cannot run against `knowledge_base_v2` until it is
     switched, and the router needs its retrain (R-a).
  2. **Phase 2's other KB writers** — `raptor_tree._embed` moved to the dense lane here because
     summaries share the collection's slot (without it, 14 tests fail); `save_raptor_tree` and
     `reembed_chunks.py` are named in §E6 as the remaining 768d writers.
- **Deviation:** `process_all_documents` was not written (no caller in a single-textbook repo).

### Step 7b — the query-side dense-lane switch ✅ DONE 2026-10-17

Closes item 1 above; the prerequisite for Step 8's measurement. No re-ingest needed.
- Every §E6 call site moved to the cluster dense lane (`get_cluster_embedder` /
  `get_query_vector` — the same `embed_query` signature, so a drop-in). The three scripts that
  query Qdrant directly (`funnel_boundary_recall`, `why_colbert`, `calibrate_eval_pages`) also
  had their hard-coded `using="dense_768"` replaced by the collection-resolved name — a second,
  independent reason the funnel could not read v2.
- **R-a discharged:** the router's schema check now compares `n_features_in_` against
  `dense_dim`, prototypes come from the dense lane, and the classifier was **retrained at 1024d**
  (`--train-only`, 1,158 queries, 96.6 % held-out accuracy). The retired 768d model is recoverable
  via `git show 161e01b:data/models/intent_classifier.pkl` (the local `.bak` is gitignored).
- **Deliberately partial:** the concept-graph lane keeps the retired 768d embedder because
  `concept_embeddings` is still 768d — registered as §I12, released by Step 9. `reembed_chunks.py`
  and `validate_embedders.py` likewise — §I13.
- **Found and fixed on the way:** the endpoint returns **unnormalised** pooled vectors; the index
  side normalised, the query side (and `embed_documents`, hence RAPTOR summaries) did not. No
  retrieval number moved (Qdrant normalises for COSINE), but any dot-product consumer was off by
  ~6,000×. Pooled paths now normalise client-side.
- **Evidence:** `logs/p1/step8/` (probe + `evidence.json` + `evidence_pre_retrain.json`, suite log).
  Register: `IMPROVEMENTS.md` §E6 "SWITCHED 2026-10-17".
- **Consequence to remember at Step 10:** the query path can no longer address the old
  `dense_768` collection, so R1's old-vs-new comparison rests on the recorded artifacts
  (`logs/p0-9/v2_*.json`) rather than on re-querying the deployed index.

### Step 8 — the run (background job)
- `scripts/ingest_base_textbook.py --pdf …feynman… --collection-name knowledge_base_v2`
  with `QDRANT_HOST=10.0.10.65`, `SV_EMBED_URL=http://10.0.10.70:8123`.
- Expect the Docling parse to dominate (968 pages, CPU — estimate tens of minutes; measure on `test_book.pdf` first).
- **Verify the counts, don't assume:** collection points == SQLite chunks; `dense_64`/`dense_1024` dims correct.

### Step 9 — downstream phases (scope-gated, see §7 open question 2)
- Phase 2 cards + RAPTOR (~5k chunks × 8 types ≈ 40k LLM calls — the expensive part).
- Phase 2b DA re-index (§A2 + §F1).
- Phase 3 visual + graph; then **`clean_stale_visual.py`** (ARCHITECTURE trap 16) and the §B4b duplicate check.

### Step 10 — re-measure
- Funnel A/B + §D13 reranker ablation on `knowledge_base_v2`; §D9 ceiling-normalised.
- Re-derive the gold labels' page numbers (§D4 now resolved → labels become unambiguous).
- Record in `HANDOFF.md` (Current focus) and `IMPROVEMENTS.md` (new §E6 entry + close §D4/§E1/§E2/§E3/§E5).

---

## 6. Risks and rollback

| # | Risk | Mitigation |
|---|---|---|
| R-a | **Intent classifier invalidated** by 768→1024 | retrain (`scripts/train_intent_classifier.py`) as part of Step 7; until then the router logs and falls back to prototype cosine. Prototype embeddings also change → both are re-derived in the same step. |
| R-b | Docling parse is slow on 968 pages | time `test_book.pdf` first; run Step 8 as `terminal(background=true, notify=true)` |
| R-c | `store.py` is 1350 LOC and shared | edit only the payload/schema lines; no refactor (CLAUDE.md §3, ARCHITECTURE trap 10) |
| R-d | Cluster outage mid-run | the run is resumable only at document granularity — write to a fresh collection so a failed run leaves the old index intact (R1) |
| R-e | Larger chunks/child counts change funnel candidate counts | re-check boundary counts after the run (E1's own caveat) |
| Rollback | — | the old `knowledge_base` is untouched; revert = point `QDRANT_COLLECTION` back |

---

## 7. Decisions closed 2026-10-16

1. **Named-vector names → keep `dense_64` / `dense_1024`.** This repo's established convention wins;
   the class-repo *package* (`svrag/qdrant_storage.py`) uses a single unnamed vector, so there is no
   package-level convention to follow, and renaming would churn `store.search`,
   `funnel_boundary_recall.py`, `evaluate_rag.py` and their tests for no gain.
2. **Scope of the run → minimal first.** Phase 1 only (the new chunking + index), then re-measure the
   text funnel + the §D13 reranker ablation. Cards / visual / graph are deferred — the ablation lives
   entirely in the text lane, so none of them gate it.
3. **Query-side instruction → yes.** Qwen3 is instruction-aware; a client-side query instruction is
   prepended and applied **everywhere** (`store.search`, `evaluate_rag`, `funnel_boundary_recall`) so
   the query path always matches the index. Documents are embedded raw (per the model card).
4. **`parent_text` in the payload → yes.** It is what makes the hierarchy usable at retrieval time.


---

## 8. Session split

Per `p0-9-SESSIONS.md` (one session per commit boundary; a long session costs turns²):

| Session | Steps | Heavy? |
|---|---|---|
| P1-a | 0–1 (config + `cluster_embedder.py` + tests) | no |
| P1-b | 2–4 (parents, semantic children, late chunking) | no (small live probes) |
| P1-c | 5–7 (E5, §D4, schema + write path + intent retrain) | no |
| P1-d | 8 (**the run**) | **yes — background job** |
| P1-e | 9–10 (downstream phases, re-measure) | yes |
