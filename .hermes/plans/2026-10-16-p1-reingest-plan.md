# P1 — the re-ingest (E1/E2/E3/E5 + §D4 + §I1). Execution plan.

**Status:** planned 2026-10-16. **Steps 0–3 done** (P1-a + E1). Next: Step 4 (E3 late
chunking). Supersedes the "Next: the re-ingest" line in `HANDOFF.md`.
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

### Step 4 — E3 `late_chunk_embedder.py`
- Local tokenizer (jina **or** Qwen3 — must match the model used for the token vectors) for offsets;
  cluster call with `return_token_embeddings=True`; mean-pool the tokens overlapping each child span.
- Guard: if a child span maps to zero tokens, fall back to the parent mean (class repo does this).
- Verify: a chunk containing "This" gets a vector that differs from its isolation-embedded twin, and
  `mean(tok)[:64] == mean(tok[:64])` numerically (the MRL/linearity claim in §2.1).

### Step 5 — E5 `is_content`
- Reuse the `_NON_CHAPTER` list already in `store.py:1362`, promoted to a shared helper.
- Tag each child; write the flag into the Qdrant payload + SQLite; filter retrieval on it.
- Verify: `tests/test_backmatter_gate.py` extended; the known mixed page (DB 936) splits correctly.

### Step 6 — §D4 per-PDF-page numbering
- `page_number` comes from the parent's provenance char→page map (Step 2), not `_page_for_offset`.
- Verify: re-run the §D4 measurement (first/last chunk page vs PDF page) — the 0/−1 spread should collapse.

### Step 7 — schema + write path
- `database._ensure_*`: new collection with `dense_64` + `dense_1024` + `colbert` + `sparse`
  (`dense_768` is retired; **keep the `dense_*` naming** — see §7 open question 1).
- `store.save_document`: write `dense_1024`, `is_content`, `parent_id`, `parent_text`.
- SQLite `_migrate_add_columns`: `chunks.parent_id`, `chunks.is_content`.
- Verify: `tests/test_config_invariants.py` + `test_phase1.py` updated; collection created with the 4 named vectors.

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
