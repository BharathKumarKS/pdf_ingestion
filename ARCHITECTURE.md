# ARCHITECTURE.md — Synapse Learning Worlds / pdf_ingestion

> Machine-oriented map of how this system actually works. Read this **before**
> changing code. It answers "where does X live, what calls what, and what will
> break" without you having to grep for it.
>
> Companion files: `README.md` (setup + run), `conventions.md` (style),
> `CLAUDE.md` (agent behaviour rules).

---

## 1. What this is

A **hybrid retrieval-augmented generation platform for physics education**.
PDFs of textbooks are ingested, enriched with LLM-generated pedagogical
"cards" and hierarchical summaries, and served to students through a
Streamlit UI with intent-routed hybrid retrieval.

Three actors:

| Actor | Entry point |
|---|---|
| **Operator** (ingest / generate artifacts) | `scripts/*.py` CLI |
| **Student / teacher** | `src/frontend/streamlit_app.py` |
| **API client** | `src/main.py` (FastAPI) |

**The one thing to know:** the system is a **4-phase pipeline** where each
phase produces durable artifacts in external stores. Phases are *not*
recomputed on the fly — changing an embedding model, a collection schema, or
a chunker invalidates previously stored artifacts and requires **re-ingest**.
Almost every "bug" in this repo is a stale-artifact problem, not a logic bug.

---

## 2. Phase map

| Phase | Produces | Modules | Stores written |
|---|---|---|---|
| **1 — Ingest** | parsed pages → chunks → dense vectors | `parser.py`, `chunker.py`, `embedder.py` | Qdrant `knowledge_base`, SQLite `documents`/`chunks` |
| **2 — Enrich** | pedagogical cards + RAPTOR summary tree | `card_generator.py`, `raptor_tree.py` | SQLite `cards`/`raptor_nodes`, Qdrant `da_collection`, RAPTOR nodes in `knowledge_base` |
| **2b — Index DA** | cards/artifacts retrievable | `scripts/index_derivative_artifacts.py` | Qdrant `da_collection` |
| **3 — Visual + Graph** | page embeddings + concept graph | `colpali_embedder.py`, `image_store.py`, `graph_builder.py` | Qdrant `visual_knowledge_base` + `concept_embeddings`, Memgraph, PNG store |
| **4 — Query** | routed retrieval | `intent_router.py`, `splade_embedder.py`, `reranker.py`, `colbert_embedder.py` | *(read-only)* |

**Phase 2b is easy to forget.** Generating cards writes them to SQLite but
does *not* make them retrievable — `index_derivative_artifacts.py` is a
separate step. If card search returns nothing, check this first.

---

## 3. Module responsibilities

### `src/core/`

| Module | Responsibility | Notes |
|---|---|---|
| `config.py` | `Settings` (pydantic-settings) + `get_settings()` | Every env var lives here. Single source of truth. |
| `database.py` | SQLModel tables, SQLite engine, Qdrant/Memgraph bootstrap, `_ensure_*_collection()` | Also owns `_migrate_add_columns()`. |
| `llm.py` | `call_llm()` — shared LLM caller | Routes to Ollama or any OpenAI-compatible endpoint. Used by Phase 2 + 3 only. |
| `pipeline_config.py` | Loads `config.yaml`; `build_instructor_client()`, `count_tokens()` | Separate from `config.py`: env → Settings, YAML → pipeline stages. |
| `intent_router.py` | `IntentRouter.classify()` / `.route()` | Trained sklearn model from `INTENT_CLASSIFIER_PATH`; falls back to prototype cosine similarity. |
| `telemetry.py` | Arize Phoenix / OpenTelemetry spans | `span()`, `set_attr()`. Gated by `PHOENIX_ENABLED`. |

### `src/pdf_ingestion/`

| Module | Responsibility |
|---|---|
| `parser.py` | `PDFParser.parse()` — Docling `DocumentConverter`, memory-safe page iteration, GPU support |
| `chunker.py` | `SemanticChunker.chunk_document()` — Chonkie two-pass, **span tracking** so each chunk maps back to a PDF page |
| `embedder.py` | `NomicEmbedder` — `nomic-ai/nomic-embed-text-v1.5`, returns **both** 768d dense and 64d MRL slice |
| `colbert_embedder.py` | ColBERT v2.0 late-interaction multi-vector (3 impls: Stub / Cluster / fastembed ONNX) |
| `colpali_embedder.py` | ColPali page-image embeddings, `vidore/colpali-v1.2` (Phase 3) |
| `splade_embedder.py` | SPLADE sparse vectors, `SparseVector.to_qdrant()` (Phase 4) |
| `reranker.py` | Cross-encoder `BAAI/bge-reranker-v2-m3` via `cfg.reranker_model` (Stub / local / cluster). |
| `image_store.py` | Page PNGs → local dir or MinIO (`IMAGE_STORE_BACKEND`) |
| `graph_builder.py` | Memgraph concept graph via Bolt; `_extract_prerequisites()` derives PREREQUISITE_OF edges |
| `raptor_tree.py` | `RaptorBuilder.build_tree()` — recursive cluster → LLM summary tree |
| `card_generator.py` | 8 card types per chunk via LLM; `ResponseParser` handles per-type JSON shapes |
| `store.py` | **`DocumentStore` — the single facade over Qdrant + SQLite.** ~1350 LOC. Plus the three top-level orchestration functions (see §5). |

**`store.py` is the hub.** Nearly every phase touches it. If a change involves
persistence or retrieval, it lands here.

---

## 4. Storage schemas

### Qdrant collections (4)

| Collection | Vectors | Contents |
|---|---|---|
| `knowledge_base` | **4 named**: `dense_64`, `dense_768`, `colbert`, `sparse` | Chunks + RAPTOR summary nodes |
| `visual_knowledge_base` | ColPali multi-vector | Page images |
| `da_collection` | single dense (`embedding_dim`) | Derivative artifacts (cards) |
| `concept_embeddings` | single dense | Graph concepts for fast ANN lookup before Cypher |

`knowledge_base` named-vector layout:

| Vector | Dim | Role |
|---|---|---|
| `dense_64` | 64 | Nomic MRL truncation — fast first-stage ANN |
| `dense_768` | 768 | Full dense — rescore second stage |
| `colbert` | `colbert_dim` (128) | Late-interaction MaxSim — third stage |
| `sparse` | — | SPLADE lane; **only created when `SPLADE_ENABLED=true`** |

**Nested prefetch funnel** (inside `DocumentStore.search()`):

```
dense_64 (top-500) → dense_768 (top-250) → colbert MaxSim (top-100)
```

Payload indexes: `tenant_id`, `source_type`, `is_global_baseline`,
`document_id`, `raptor_level`.

### SQLite (SQLModel)

| Table | Meaning |
|---|---|
| `Document` | One ingested PDF — base textbook or user upload |
| `Chunk` | A Chonkie chunk, linked to its Qdrant point |
| `Card` | One pedagogical card per (chunk, card type) |
| `RaptorNode` | A RAPTOR summary node |
| `PageImage` | One rasterized page image per PDF page |

### Card types (8 defined in `CardType`)

`summary`, `definition`, `example`, `misconception`, `question`, `objective`,
`formula`, `factoid`

> `CLAUDE.md` and `database.py`'s `Card` docstring say "7 cards". The enum has
> **8**. Treat `CardType` as authoritative; the prose is stale.

### Intents (5)

`factual`, `overview`, `multihop`, `visual`, `mixed` — see `RouteConfig` for
which retrieval lanes each one activates.

---

## 5. Data flow

### Ingestion (Phase 1)

```
PDF ──parser.py──> ParsedDocument(pages)
    ──chunker.py──> TextChunk[] (+ char span → page map)
    ──embedder.py─> EmbeddedChunk[] (768d + 64d MRL)
    ──store.ingest_pdf()─> Qdrant knowledge_base + SQLite documents/chunks
```

### Enrichment (Phases 2/2b/3)

```
store.generate_phase2_artifacts(document_id)
  ├─ card_generator.py ── call_llm() ──> cards (SQLite)
  └─ raptor_tree.py ──── call_llm() ──> RaptorNode tree
                                        └─> Qdrant knowledge_base (raptor_level payload)

scripts/index_derivative_artifacts.py ──> Qdrant da_collection

store.generate_phase3_artifacts(document_id, pdf_path)
  ├─ colpali_embedder.py ─> visual_knowledge_base
  ├─ image_store.py ─────> page PNGs
  └─ graph_builder.py ───> Memgraph (+ concept_embeddings)
```

### Query (Phase 4)

```
query
 ├─ embedder.embed_query() ──────────────────────┐
 ├─ intent_router.classify() ──> RouteConfig     │
 ├─ HyDE hypothesis (HYDE_ENABLED) ──────────────┤
 │                                               ▼
 │                          store.search() nested prefetch funnel
 │                                   │
 │                                   ├─ store.search_raptor()   (overview)
 │                                   ├─ graph_builder.graph_search() (multihop)
 │                                   └─ store.search_da()       (DA lane)
 │                                               ▼
 │                              reranker.rerank(query, chunks, top_k)
 └──────────────────────────────────────────────> cards + sources → Streamlit
```

`DocumentStore.search_with_das()` binds the DA lane into the main funnel
(DA joins the candidate pool **before** dedup + MMR — see commit `3a7e954`).

#### The funnel inside `store.search()` — merge changed 2026-10-06

The funnel runs server-side as **one nested Qdrant prefetch**. The `prefetch` entries are
the *voters* (their rankings get combined); the outer `query` is the *judge* (it produces
the final ordering). Which role ColBERT plays is what changed.

**BEFORE — ColBERT was the judge**, so it *replaced* the dense+sparse fusion:

```
corpus ─ dense_64 ──────────────► 1000 ─┐
                                        ├─► dense_768 ─────────► 500 ─┐
         sparse (SPLADE) ────────────────────────────────────► 250 ─┤
                                                                     ▼
                        ┌──────────────────────────────────────────────────┐
                        │ OUTER QUERY = ColBERT MaxSim                     │
                        │ (a single score REPLACES the two rankings above) │
                        └──────────────────────────────────────────────────┘
                                                                     ▼
                                                     100 ──► cross-encoder ──► 20
```

**AFTER — ColBERT is a third voter**, and RRF fuses all three rankings:

```
corpus ─ dense_64 ──────────────► 1000 ─┐
                                        ├─► dense_768 ─────────► 500 ─┐
         sparse (SPLADE) ────────────────────────────────────► 250 ─┤
         colbert (MaxSim) ───────────────────────────────────► 250 ─┤
                                                                     ▼
                        ┌──────────────────────────────────────────────────┐
                        │ OUTER QUERY = RRF over the three rankings        │
                        └──────────────────────────────────────────────────┘
                                                                     ▼
                                                     100 ──► cross-encoder ──► 20
```

Measured (23 queries, pinned HyDE) — the retriever's own top-20 recall:

| merge | retriever top-20 |
|---|---|
| ColBERT as outer query (**before**) | 0.598 |
| RRF over dense+sparse | 0.615 |
| **RRF over dense+sparse+ColBERT (after)** | **0.651** |

RRF wins because it combines *independent* rankings; a single MaxSim score cannot. ColBERT
is worth keeping — as a voter, not as the judge.

⚠️ **The cross-encoder then destroys that ordering**: 0.651 → 0.569, and its harm scales
with the quality of its input (+0.002 / −0.026 / −0.082 across the three merge modes).
**The merge change must therefore ship together with a reranker decision** — applied alone
it is a regression. See `IMPROVEMENTS.md` §F4 and
`data/eval_results/funnel-merge-ab_2026-10-06.md`.

Note also that the funnel boundaries are `1000 → 500 → 250(x2, x3) → 100 → 20`, and only
`@100` and `@20` were ever measured. Per-boundary recall lives in
`scripts/funnel_boundary_recall.py`; the first run is
`data/eval_results/funnel-boundary-recall_2026-10-06.md`.

#### Other architecture changes in the same session (2026-10-06)

Not part of the funnel diagram, but they change what the system does:

| Change | Where | Effect |
|---|---|---|
| **Card embed text: question only** | `scripts/index_derivative_artifacts.py` | Was `question + "\n" + answer`. A student's query resembles a question, not an answer; the answer diluted the vector. The answer now rides in the payload as a new `answer` field (it was **not** there before — only concatenated into `text`), so it is still shown but no longer embedded. **Takes effect only on the next DA re-index.** |
| **Card value filter at generation** | `card_generator.py` (`ResponseParser.is_valuable`) | Rejects cards that refer to their source ("according to the passage") or are too short, so junk never reaches the DB. Backfilled: 95,213 → 82,164 cards. |
| **SQLite IDs realigned to the cluster** | `scripts/align_stores.py` | A migration, not an architecture change: the two stores had been ingested separately and shared **zero** IDs, so every retrieval→SQLite join failed. SQLite chunk/document IDs were renamed to the cluster's (99.9% by chunk text). |
| **Student panel** | `src/frontend/streamlit_app.py` | New "Find a Figure" tab (visual search + synthesis); Study Cards default to the passages of the last question asked; removed the inert "User ID", "Topic" and "Difficulty" controls. |

**Still stale, and known:** the `derivative_artifacts` collection predates the card-lane
changes — it holds 5 of the 8 card types and shares no card IDs with SQLite. Re-indexing it
is required for the card-lane changes to take effect. See `IMPROVEMENTS.md` §A2.

---

## 6. Backend abstraction pattern (follow this when adding a dependency)

Every external dependency has **three implementations** behind one factory:

1. `Stub*` — deterministic, no download, no network → used in tests
2. `Cluster*` — HTTP call to the SupportVectors GPU cluster
3. Local / fastembed — ONNX or sentence-transformers, CPU-friendly

Resolved by `get_<thing>(settings)` and reset by `reset_<thing>()`.

Existing factories: `get_embedder`, `get_colbert_embedder`,
`get_colpali_embedder`, `get_splade_embedder`, `get_reranker`,
`get_graph_builder`, `get_card_generator`, `get_image_store`,
`get_intent_router`, plus `get_engine` / `get_session` / `get_qdrant` /
`get_memgraph`.

**If you add a new model-backed component, add it this way.** It is what keeps
`pytest -m "not slow"` fast and offline.

### Stub flags (all default off in production, on in tests)

`USE_STUB_EMBEDDER`, `USE_STUB_LLM`, `USE_STUB_COLPALI`, `USE_STUB_GRAPH`,
`USE_STUB_SPLADE`, `QDRANT_IN_MEMORY`

Tests rely on the autouse `reset_db_singletons` fixture in `tests/conftest.py`.
**Any new module-level singleton must get a `reset_*()` and be registered
there**, or tests will leak state between cases.

---

## 7. Configuration surface

Two config files, deliberately separate:

| File | Owns | Consumed by |
|---|---|---|
| `.env` → `Settings` | endpoints, keys, paths, feature flags, flags for stubs | `src/core/config.py` |
| `config.yaml` | per-stage **model** + `base_url` (card gen, RAPTOR, intent, eval judge) | `src/core/pipeline_config.py` |

LLM backend switch (used only by Phase 2/3):

```env
LLM_BACKEND=ollama | openai
OPENAI_API_BASE=<openai-compatible base url>
OPENAI_MODEL=<served model id>
```

Feature flags that change storage schema (require re-ingest when flipped):
`SPLADE_ENABLED`, `COLBERT_ENABLED`, `EMBEDDING_DIM`, `EMBEDDING_MODEL`.

---

## 8. Invariants and traps

**Read this section before your first change.**

1. **Flipping `SPLADE_ENABLED` adds a named vector → full re-ingest required.**
   The collection is created once with a fixed vector set; Qdrant cannot add a
   named vector to an existing collection.
2. **`EMBEDDING_MODEL` / `EMBEDDING_DIM` must match the embedder.**
   `src/pdf_ingestion/embedder.py` implements **Nomic** `nomic-embed-text-v1.5`
   (768d + 64d MRL); `config.py` and `.env.example` now agree (768/64).
   Verify the real `.env` before trusting it — mismatched dims fail at
   Qdrant upsert time, not at import time. Pinned by
   `tests/test_config_invariants.py`.
3. **`transformers` is pinned `<5.0`** in `pyproject.toml`. The stated reason
   is Jina v3's custom LoRA code. Since the active embedder is now Nomic, the
   pin may be legacy — **do not bump it without checking who still depends on
   it.** A model that "helpfully" upgrades this will break the venv.
4. **Chunk → page mapping depends on `chunker.py` span tracking.** Anything
   that re-chunks text without producing spans will silently break page-level
   citations (`get_chunks_by_pages`) and ColPali alignment.
5. **`dense_64` and `dense_768` must stay consistent.** The 64d vector is an
   MRL slice of the 768d one, re-normalised. Changing the truncation logic
   invalidates every stored point.
6. **Cards live in two places and drift.** SQLite `cards` is the source of
   truth; `da_collection` is the retrievable index. Regenerating cards without
   re-running `scripts/index_derivative_artifacts.py` leaves retrieval stale.
7. **`tenant_id` is on every payload.** Every search must filter by tenant;
   `is_global_baseline` marks shared textbook content. Missing a tenant filter
   is a data-leak, not just a correctness bug.
8. **LaTeX rendering is fragile.** `streamlit_app.py` has
   `_convert_braces_to_math()` / `render_math()` and there is a run of `fix:`
   commits around brace conversion and `st.latex()`. Formula cards are the
   highest-risk UI surface.
9. **Optional infrastructure is behind flags** — Memgraph, MinIO, Phoenix,
   ColPali. A code path that assumes one is present will pass locally and fail
   on the GPU VM (or vice versa). Check the flag before assuming.
10. **`store.py` is 1350 LOC and pre-existing.** Per `CLAUDE.md` §3
    (Surgical Changes), do not refactor it as a side effect of another task.

---

## 9. Where to make a change

| I want to… | Touch | Watch out for |
|---|---|---|
| Add a card type | `card_generator.CardType`, `ResponseParser`, prompts, `streamlit_app.CARD_LABELS` | 4 places; re-index DA afterwards |
| Add a retrieval lane | `store.search*()`, `intent_router.RouteConfig`, `streamlit_app` | Must add a payload index in `database._ensure_*` |
| Swap an embedding model | `embedder.py`, `config.py`, `.env`, `database._ensure_collection` | Full re-ingest; dim change breaks all collections |
| Add a new external model | New module following §6 (Stub + real + factory + `reset_*`) | Register in `conftest.py` |
| Change chunking | `chunker.py` | Spans must survive (see trap 4) |
| Add an API endpoint | `src/main.py` | Reuse `DocumentStore`, don't bypass it |
| Change graph semantics | `graph_builder.py`, `_extract_prerequisites()` | Memgraph schema in `ensure_schema()` |

---

## 10. Commands

```bash
uv sync                                                              # install
uv run pytest tests/ -q -m "not slow"                                # fast, offline
uv run streamlit run src/frontend/streamlit_app.py                   # UI

uv run python scripts/ingest_base_textbook.py --pdf <p> --title <t> --subject <s> --grade <g>
uv run python scripts/run_phase2.py --tenant global
uv run python scripts/index_derivative_artifacts.py                  # Phase 2b — don't skip
uv run python scripts/run_phase3.py --tenant global
uv run python scripts/run_phase3.py --doc-id <uuid> --graph-only
uv run python scripts/evaluate_rag.py                                # eval against data/eval_queries.json
```

Tests: 141 test functions across 10 files. `test_phase1/2/3` map to the phases;
`test_integration_real.py` and anything `@pytest.mark.slow` need real models.

---

## 11. Environment-specific notes

- **GPU VM**: `SPLADE_ENABLED=true` → re-ingest needed.
- **Laptop with existing Feynman data**: `SPLADE_ENABLED=false` → no re-ingest.
- **Laptop, small PDF**: `SPLADE_ENABLED=true` → re-ingest takes seconds.
- Pipeline stages point at `http://10.0.10.70:8000/v1` (`config.yaml` and the
  `OPENAI_MODEL`/`OPENAI_API_BASE` vars in `.env`) with `openai/gpt-oss-20b`.
  Changing this restages Phase 2/3 output quality but not the schema.
- **`.70` fronts two backends and only one is up** (observed 2026-10-04). Models with
  `owned_by: vllm` — `gpt-oss-20b`, `DeepSeek-R1-Distill-Qwen-7B`, `Qwen3-VL-8B-Instruct`
  — answer. Models with `owned_by: inference` — `gpt-oss-120b`, `Qwen-Image`,
  `Wan2.2-T2V-A14B` — list on `/v1/models` but return **HTTP 502 "Backend inference
  unreachable after 3 attempts"** on every `chat/completions` call. A liveness probe
  against `/v1/models` therefore reports all-clear on a pipeline that cannot generate a
  single token; `scripts/preflight.py` issues a real completion instead.
- **The gateway returns HTTP 500 for an empty `Authorization: Bearer` header.** Any
  client that sends the header with no key breaks — this is why the eval judge scored
  nothing until it was given a non-empty key.

---

## 12. Guardrails (planned — P2 spec)

**Status: not built.** Recorded here so the P2 work is a decision rather than an
improvisation. Referenced by `README.md` Phase 5 ("DeBERTa guardrails + answer leakage
guard") and HANDOFF P2. Nothing in `src/` enforces any of this today: the synthesis system
prompt's "if the passages are irrelevant, say so" is an *instruction the model may ignore*,
not a guardrail.

### Why this is gated on P0-9

Abstention cannot be **measured** without negatives. Every query in the current eval set is
answerable, so there is nothing to score a refusal against. The gold-set rebuild (P0-9)
must include unanswerable / out-of-scope queries (~15–20%) before any abstention guardrail
can be evaluated — otherwise it ships unmeasurable.

### Input guardrails (before retrieval)

| Check | Failure it prevents | Cheap signal |
|---|---|---|
| Prompt injection / jailbreak | User text steering the system prompt or tool use | Pattern + classifier; query text is never executed as instructions |
| Off-topic / non-physics | Confident answers to questions the corpus cannot address | The intent router already classifies; extend it with an `out_of_scope` class |
| PII in the query | User PII persisted into traces and the SQLite log | Regex + NER pass before persisting |
| Oversized / degenerate input | Cost blowups, empty or 100k-char queries | Length caps (partly handled in the UI already) |

### Output guardrails (after synthesis)

| Check | Failure it prevents | Cheap signal |
|---|---|---|
| Grounding / faithfulness | Ungrounded claims reaching a student | The judge lane already computes claim-level faithfulness (0.70, a floor). Caveat or block below a threshold. |
| Answer leakage | Revealing eval-set answers or hidden keys | Scan the answer against the held-out eval answers and secret patterns |
| Citation validity | Citing pages that were not retrieved | `compute_citation_accuracy` already does exactly this (1.000 today, because the generator only cites retrieved pages) |
| Unsafe / harmful content | Domain policy breach | Classifier — a DeBERTa head is the stated plan |
| PII in the answer | Echoing user PII back | Same pass as input |

### Design constraints

- **Fail-open vs fail-closed is an explicit per-guardrail decision.** Failing open turns an
  outage into silently low-quality answers; failing closed turns it into a hard stop.
  Neither default is safe by accident — choose per check and record the choice.
- **Latency budget.** A guardrail that adds a full LLM call per query doubles cost. Prefer a
  small classifier (the DeBERTa plan) or reuse an existing signal (faithfulness, citation
  accuracy) before adding a call.
- **The guardrail itself needs precision/recall numbers**, measured on a labelled sample. A
  guardrail nobody measured is indistinguishable from a broken one — the same failure mode
  as the silent fallbacks in §8.
- **Record the decision in the artifact.** "Blocked" vs "not blocked" must be counted, or
  the guardrail's effect on the metrics is invisible.
