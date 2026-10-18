# P1 Step 7 — schema + write path (evidence + review record)

**Date:** 2026-10-17 · branch `feat/p0-9-gold-dataset-v2` · author model `deepseek/deepseek-v4.1-flash`

What landed, why, and what it deliberately did not close: `IMPROVEMENTS.md` §E6 (the register)
and the plan's §5 Step 7. This file is the **evidence and the review record**.

## What this step changes

| file | change |
|---|---|
| `src/pdf_ingestion/chunking_pipeline.py` | **new** — the single ingest path: `ParentChunker.convert` → `SemanticChunker.chunk_parents` → `LateChunkEmbedder.embed_children` → `DocumentStore.save_document` |
| `src/core/database.py` | created schema = `dense_64 + dense_1024 + colbert + sparse` (`dense_768` retired); `Chunk.parent_id` + migration |
| `src/pdf_ingestion/store.py` | write path (`dense_1024`, `parent_id`, `parent_text`, SQLite `parent_id`); the full-dim dense name is **resolved from the collection** on both write and read; `ingest_pdf` delegates to the pipeline |
| `src/pdf_ingestion/chunker.py` | the legacy flat path (`chunk_document` / `build_page_map` / `_page_for_offset`) **deleted** — Step 6's deferred half |
| `src/pdf_ingestion/cluster_embedder.py` | `StubTokenizer` (test-only) + `get_query_vector` (the one dense-lane query accessor) |
| `src/pdf_ingestion/late_chunk_embedder.py` | stub tokenizer when `use_stub_embedder` — no download in tests |
| `src/pdf_ingestion/raptor_tree.py` | summary embedder moved to the dense lane (forced: summaries share the collection's slot) |
| `scripts/ingest_base_textbook.py` | `--collection-name` (R1: write to a new collection, keep the deployed one) |

## The live probe (`probe_step7_pipeline.py` → `probe.json`)

Run against the **real** cluster dense lane and the **real** Qwen3 tokenizer, in-memory Qdrant
so nothing is written to the cluster's storage:

```
SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings \
  uv run python logs/p1/step7/probe_step7_pipeline.py
```

`test_book.pdf` (19 pages) → **42 parents → 66 children** — the same counts Step 2/3 recorded,
which is the point: the pipeline reproduces the per-stage measurements end to end.

| check | result |
|---|---|
| M1 collection carries exactly `colbert`, `dense_1024`, `dense_64` (`dense_768` absent) | PASS |
| M2 every point 1024d + 64d, both unit-norm | PASS |
| M3 Qdrant points == SQLite chunks == children == **66** | PASS |
| M4 every payload has `parent_id` / `parent_text` / `is_content` | PASS |
| M5 every child has an in-range page number | PASS |
| M6 `dense_64 == mrl_slice(dense_1024, 64)` within 1e-5 | PASS |

The endpoint's trailing special-token vector shows up in the logs (`182 tokens, 183 vectors`) —
the contract Step 4 pinned, confirmed again through the pipeline rather than in isolation.

## Test + lint state

| | before | after |
|---|---|---|
| fast suite (`-m "not slow"`) | 341 pass / 5 fail | **356 pass / 4 fail / 6 skip** |
| ruff (changed files) | 51 findings | 51 findings — **no new** |

The 4 failures are the pre-existing class (2 SPLADE fixtures, 2 zero-result searches) and fail on
the parent commit. The 6 skips are the live-E2E tests: the dense lane is the cluster now, so they
skip unless `SV_EMBED_URL` is set rather than silently testing a model the pipeline no longer uses.

## Independent review

Three reviewers, one diff each, `openai/gpt-oss-20b` (`delegation.model` — a different model
family from the author's), single-turn with the diff as DATA, fail-closed on anything they could
not resolve. Task 1 = `store.py`; Task 2 = `database.py` + `chunking_pipeline.py` + `chunker.py`;
Task 3 = `cluster_embedder.py` + `late_chunk_embedder.py` + `raptor_tree.py` +
`ingest_base_textbook.py` + `models.py` + `parent_chunker.py`.

| task | verdict |
|---|---|
| 1 (`store.py`) | `passed:false`, 4 logic_errors |
| 2 (schema + orchestrator + dead path) | **`passed:true`**, no findings |
| 3 (dense-lane switch) | `passed:false`, 1 logic_error |

### Adjudication — every reported "logic error" is checkable, and false

A diff-only reviewer cannot see code outside the hunks, so it reports library-API and
config-field doubts as logic errors. Each claim was checked against the repo; none survives.
**No claim was applied, because applying any of them would have introduced a defect.**

| # | claim | verdict | evidence |
|---|---|---|---|
| 1 | `store.py` is missing `import numpy as np` | **false** | the import is at `store.py:8`; `_dense_vectors(...)` was executed and returned `(768,)`/`(64,)` |
| 2 | `Settings` may lack `dense_dim_low` / `cfg.dense_dim` | **false** | `Settings.model_fields` → `dense_dim=1024`, `dense_dim_low=64` (both Step 0) |
| 3 | `EnrichedChunk` may lack `.chunk`; `EmbeddedChunk` may lack `.embedding_low` | **false** | both are dataclass fields (`EnrichedChunk`: chunk, dense_1024, dense_64, …; `EmbeddedChunk`: chunk, embedding, model_name, embedding_low) |
| 4 | "the correct attribute is `cfg.embedding_dim`, not `cfg.dense_dim`" | **false, and acting on it would reintroduce the bug** | `embedding_dim=768` is the *retired* Nomic dim; the RAPTOR summary must be 1024d to fit `dense_1024`. This is the 14-test failure the change fixes |
| 5 | residual hard-coded `dense_768` may cause runtime errors | **partly real — and already registered** | `store.py:35 _DENSE_VECTOR_NAMES` is the intentional R1 resolution; the real residual references are `scripts/why_colbert.py:64,88` and `scripts/funnel_boundary_recall.py:192,224`, which are named in the §E6 gap table as part of the query-side switch |

Two suggestions were verified rather than assumed: `--collection-name` does take effect
(assignment accepted; a collection is created under the configured name), and `numpy` is imported
in `cluster_embedder.py` (with `mrl_slice` executed to prove it).

**Consequence for the verdict vocabulary:** task 1 and 3 return `passed:false` while reporting
zero real defects. That is recorded as-is — a fail-closed verdict from a diff-only reviewer is
not a defect, but it is also **not** a `passed:true`, so Step 7 is not claimed as
independently approved. What *is* claimed: no reviewer finding survived adjudication, and task 2
— the schema, the orchestrator and the dead-path removal — was approved outright.

## What Step 7 does not close (⛔ before Step 10)

**The query side still embeds with the retired model.** The UI, `main.py`, `evaluate_rag`,
`funnel_boundary_recall`, `calibrate_eval_pages`, `why_colbert` and the intent router (prototypes
+ its `embedding_dim` schema check) call the local Nomic 768d embedder. Against
`knowledge_base_v2` that is a loud dimension error, and the deployed index is unaffected — so
nothing is silently wrong today — but **the funnel and the §D13 ablation cannot measure until it
is switched**, and the router needs its retrain (R-a). No re-ingest is required to fix it: a code
change plus one retrain run against the cluster. Full call-site table: `IMPROVEMENTS.md` §E6.

## Reproducing

```
uv run pytest tests/ -q -m "not slow"                    # 356 pass / 4 pre-existing fail / 6 skip
uv run pytest tests/test_chunking_pipeline.py -q          # the 19 new tests
SV_EMBED_URL=... uv run python logs/p1/step7/probe_step7_pipeline.py   # the live probe
```

`probe.db` (the throwaway SQLite, ~190 KB) is gitignored — re-derivable, and it would otherwise
change on every run. The probe, `probe.json` and this README are the evidence and are tracked.
