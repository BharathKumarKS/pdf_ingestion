# Synapse Learning Worlds — Hybrid RAG Platform

An adaptive learning platform powered by Hybrid RAG (Retrieval-Augmented Generation).  
Pre-ingest a base textbook globally, let students upload their own PDFs, and answer questions from either source — or both.

> **Architecture:** Synapse Learning Worlds v4.0 · Author: Bharath Kumar

---

## Architecture Overview

```
Offline (admin, run once)              Online (runtime, per user)
──────────────────────────             ──────────────────────────
PDF → Docling → Chonkie               Student uploads PDF
    → Jina v3 (late chunking)             → same pipeline (Phase 1)
    → Qdrant (tenant_id=global)           → ColPali + graph async in background

Phase 2 artifacts (LLM via config.yaml):   Query flow (Phase 4):
  • 8 pedagogical cards/chunk              1. Jina v3 → Qdrant vector search
      summary, definition, example,        2. MMR diversity reranking on dense
      misconception, question, objective,  3. DA recall lane (definition /
      formula, factoid (COSTAR prompts)       formula / question / factoid cards)
  • RAPTOR L1/L2/L3 summaries             4. RAPTOR cluster summaries (overview)
  • Stored: SQLite + Qdrant               5. Memgraph concept graph (multi-hop)
                                           6. SPLADE sparse hybrid + RRF (GPU)
Phase 3 artifacts:                         7. Cross-encoder re-ranker (next)
  • ColPali patch vectors / page
  • Concept graph in Memgraph          Retrieval routes by query type:
  • Page images on local disk            vector  → factual / point queries
  • Stored: SQLite + Qdrant             raptor  → summaries / chapter overviews
            + Memgraph + disk            graphrag → multi-hop / prerequisite chains
                                         colpali → diagram / figure / table queries
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| PDF parsing | Docling (IBM) |
| Chunking | Chonkie `SentenceChunker` |
| Text embeddings | Jina v3 `jinaai/jina-embeddings-v3` (late chunking) |
| Sparse embeddings | SPLADE (GPU) — dense+sparse hybrid via Qdrant RRF |
| Visual embeddings | ColPali `vidore/colpali-v1.2` (multi-vector patch embeddings) |
| Vector store | Qdrant — `knowledge_base` + `derivative_artifacts` + `visual_knowledge_base` |
| Relational store | SQLite via SQLModel |
| Graph store | Memgraph (OpenCypher via neo4j Bolt driver) |
| Image store | Local disk (swappable to MinIO via `IMAGE_STORE_BACKEND=minio`) |
| LLM (cards + RAPTOR + synthesis) | Any OpenAI-compatible endpoint via `config.yaml` |
| Structured outputs | instructor + Pydantic schemas (guaranteed JSON conformance) |
| Intent routing | Embedding similarity against prototype queries |
| API | FastAPI |
| Frontend | Streamlit |
| Package manager | uv |

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 | Pinned via `.python-version` |
| [uv](https://docs.astral.sh/uv/) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| LLM endpoint | any | Configured in `config.yaml` — Ollama, vLLM, or OpenAI-compatible |
| Docker (optional) | latest | Required for Memgraph + MinIO (Phase 3 graph search) |

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/BharathKumarKS/pdf_ingestion.git
cd pdf_ingestion

# Install all dependencies (creates .venv automatically)
uv sync --extra dev
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if you want to change defaults (all defaults work out of the box)
```

Key settings in `.env`:

```env
EMBEDDING_MODEL=jinaai/jina-embeddings-v3   # downloads ~570 MB on first run
QDRANT_LOCAL_PATH=./data/qdrant             # local file-based persistence
```

### 3. Configure LLM endpoints

Edit `config.yaml` at the project root:

```yaml
card_generation:
  model: openai/gpt-oss-20b
  base_url: http://your-server:8000/v1   # any OpenAI-compatible endpoint

raptor_summarization:
  model: openai/gpt-oss-20b
  base_url: http://your-server:8000/v1
  summary_min_tokens: 150
  summary_max_tokens: 400
```

API key precedence: `api_key` in config.yaml → `OPENAI_API_KEY` env var → `API_KEY` env var → `"dummy"` (for endpoints that don't require auth).

### 4. (Optional) Start Memgraph for GraphRAG

Skip this step if you only want text search and visual search without the concept graph.

```bash
docker compose --profile phase3 up -d
```

This starts Memgraph on `bolt://localhost:7687`.

### 5. Ingest the base textbook (admin step — run once)

Place your textbook PDF in `data/base_textbooks/` then:

```bash
uv run python scripts/ingest_base_textbook.py \
  --pdf data/base_textbooks/your_textbook.pdf \
  --title "Your Textbook Title" \
  --subject "Physics" \
  --grade "Undergraduate"
```

> **First run** downloads the Jina v3 model (~570 MB) automatically.

### 6. Generate Phase 2 artifacts (cards + RAPTOR)

```bash
uv run python scripts/run_phase2.py --tenant global
```

Generates **8 pedagogical cards per chunk** (summary, definition, example, misconception, question, objective, formula, factoid) using COSTAR-format prompts via the configured LLM endpoint, plus **RAPTOR hierarchical summaries** (up to 3 levels).

### 7. Index derivative artifacts (DA retrieval lane)

```bash
uv run python scripts/index_derivative_artifacts.py --tenant global
```

Embeds definition, formula, question, and factoid cards into the `derivative_artifacts` Qdrant collection. Used by Phase 4 retrieval to expand recall beyond the main chunk search.

### 8. Generate Phase 3 artifacts (ColPali + Memgraph)

```bash
# Process all documents for a tenant
uv run python scripts/run_phase3.py --tenant global

# Target one specific document
uv run python scripts/run_phase3.py --doc-id <uuid>

# Re-run from scratch
uv run python scripts/run_phase3.py --tenant global --force
```

**What gets generated:**
- **ColPali patch vectors** — every PDF page rasterized and embedded as a matrix of patch vectors, stored in `visual_knowledge_base`. Enables image-level semantic search.
- **Concept graph in Memgraph** — Document → Chunk → Concept nodes with MENTIONS / RELATES_TO / PREREQUISITE_OF edges. Enables multi-hop GraphRAG retrieval.

**Smart resume** — re-running after a partial failure skips what's already done. Use `--force` to re-process from scratch.

### 9. Launch the app

```bash
uv run streamlit run src/frontend/streamlit_app.py
```

Open **http://localhost:8501**

---

## GPU VM Setup (Support Vectors)

Running the 990-page Feynman textbook on CPU takes 30+ hours.
On the Support Vectors GPU VM with the remote Qdrant cluster, the same job
completes in **2–3 hours**.

### Step 1 — Copy and edit `.env`

```bash
cp .env.example .env
nano .env
```

Fill in these values from your Support Vectors dashboard:

| Key | Where to get it | Example |
|---|---|---|
| `QDRANT_URL` | Support Vectors Qdrant dashboard → Cluster URL | `https://abc123.cloud.qdrant.io` |
| `QDRANT_API_KEY` | Support Vectors Qdrant dashboard → API Keys | `sv-xxxxxxxxxxxx` |
| `USE_GPU` | Set to `true` on the GPU VM | `true` |
| `EMBEDDING_BATCH_SIZE` | Increase for GPU | `32` |
| `CARD_GEN_WORKERS` | Parallel LLM threads for card generation | `8` |
| `SPLADE_ENABLED` | Enable sparse hybrid search (requires re-ingest) | `true` |

### Step 2 — Configure `config.yaml`

Point the LLM endpoints at your cluster-hosted models:

```yaml
card_generation:
  model: openai/gpt-oss-20b
  base_url: http://10.0.10.51:8000/v1

raptor_summarization:
  model: openai/gpt-oss-20b
  base_url: http://10.0.10.51:8000/v1
```

### Step 3 — Ingest and generate artifacts

```bash
# Phase 1: ingest
uv run python scripts/ingest_base_textbook.py \
  --pdf data/base_textbooks/feynman_physics_vol1.pdf \
  --title "The Feynman Lectures on Physics Vol. 1" \
  --subject "Physics" --grade "Undergraduate"

# Phase 2: cards + RAPTOR
uv run python scripts/run_phase2.py --tenant global

# Phase 2b: index DA cards into Qdrant
uv run python scripts/index_derivative_artifacts.py --tenant global

# Phase 3: ColPali + concept graph
uv run python scripts/run_phase3.py --tenant global
```

### Speed breakdown (990 pages, 5,047 chunks)

| Stage | CPU laptop | GPU VM (estimated) |
|---|---|---|
| Docling parsing | ~2 hours | ~20 min |
| Jina v3 embedding | ~2 hours | ~15 min |
| Card generation (8 types) | ~30 hours | ~3 hours (8 parallel workers) |
| RAPTOR tree | ~5 min | ~2 min |
| DA indexing | ~30 min | ~5 min |
| ColPali embedding (5k pages) | ~8 hours | ~45 min |
| Concept graph (Memgraph) | ~2 hours | ~30 min |
| **Total** | **~45 hours** | **~5 hours** |

---

## Portal Tabs

### Student view (default — http://localhost:8501)

| Tab | What it does |
|---|---|
| 📄 Upload PDF | Upload lecture notes / supplementary reading |
| 🔍 Ask a Question | Synthesized answer + Key Facts panel + source citations |
| 🃏 Study Cards | Flashcards by type (summary, definition, Q&A, formula, factoid, etc.) |

- Source toggle: **Textbook + My Notes** (default) / **My Notes only**
- Clean interface: no system internals (no scores, IDs, routing details, or metadata)
- Key Facts panel surfaces relevant definition and factoid cards from matched chunks
- After uploading a PDF, visual embeddings + concept graph are built in the background

### Admin / Teacher view (http://localhost:8501?admin=true)

All student tabs **plus**:

| Tab | What it does |
|---|---|
| 🌲 RAPTOR Tree | Hierarchical cluster summaries with full metadata |
| 🖼️ Visual Search | Upload an image to find matching pages (ColPali) |
| 🕸️ Concept Graph | Ask a multi-hop reasoning question (Memgraph GraphRAG) |
| 📊 Admin Status | Chunk / card / RAPTOR / visual page counts + ColPali status per document |

- Full similarity scores, source types, intent routing details, concept paths visible
- "Generate Phase 2 artifacts" button in sidebar
- Upload as base textbook or user upload

---

## Retrieval Routes (Phase 4)

Queries are classified by the intent router and routed across retrieval mechanisms:

| Query type | Best route | Example |
|---|---|---|
| Specific fact / formula | **Vector search + DA lane** | "What is the formula for kinetic energy?" |
| Chapter overview / synthesis | **RAPTOR** | "Summarize conservation laws across the textbook" |
| Multi-hop / prerequisite | **GraphRAG** | "Why does a satellite stay in orbit?" |
| Diagram / figure / table | **ColPali visual** | "Show me the double-slit experiment diagram" |

**DA (Derivative Artifact) retrieval lane** — definition, formula, question, and factoid cards are independently embedded and searched. DA hits that aren't already in the dense result set are appended to expand recall without hurting precision (DA acts as a recall-only expansion lane, not interleaved via RRF).

**MMR (Maximal Marginal Relevance)** — applied to dense results first (λ=0.7) to diversify retrieved chunks before DA expansion.

See `data/eval_queries.json` for curated evaluation queries across all four routes.

---

## Evaluation

```bash
# Run RAG evaluation against calibrated query set
uv run python scripts/evaluate_rag.py

# Calibrate page annotations after manual review
uv run python scripts/calibrate_eval_pages.py
```

Results are saved to `data/eval_results/`. Current metrics on Feynman corpus (Phase 4):

| Metric | Baseline | Phase A v2 |
|---|---|---|
| Recall@20 | 0.315 | 0.384 |
| MRR | 0.598 | 0.684 |
| Precision@6 | 0.360 | 0.404 |
| NDCG@6 | 0.429 | 0.505 |

---

## Run Tests

```bash
# Unit + integration tests (fast, stubs only — no model download, no LLM needed)
uv run pytest tests/ -q -m "not slow"

# All phase-specific tests
uv run pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase_a.py -v -m "not slow"

# Real Jina v3 integration test (downloads model on first run)
uv run pytest tests/test_integration_real.py -v -s
```

**125 tests pass** (stubs only — no model downloads, no Ollama, no Qdrant server needed).

---

## Project Structure

```
pdf_ingestion/
├── pyproject.toml                      # uv project — all deps + metadata
├── uv.lock                             # deterministic lockfile
├── config.yaml                         # LLM endpoint config per pipeline stage
├── .env.example                        # environment variable template
├── docker-compose.yml                  # Memgraph + MinIO (Phase 3)
├── data/
│   ├── eval_queries.json               # curated evaluation queries (vector/raptor/graph/colpali)
│   └── eval_results/                   # evaluation output JSONs (gitignored)
│
├── src/
│   ├── core/
│   │   ├── config.py                   # Pydantic settings (all env vars)
│   │   ├── database.py                 # SQLModel tables + Qdrant + Memgraph bootstrap
│   │   ├── intent_router.py            # query intent classification (Phase 4)
│   │   ├── llm.py                      # shared LLM caller (OpenAI-compatible)
│   │   └── pipeline_config.py          # config.yaml loader + instructor client factory
│   │
│   ├── pdf_ingestion/
│   │   ├── parser.py                   # Docling PDF parser (+ page rasterization)
│   │   ├── chunker.py                  # Chonkie semantic chunker
│   │   ├── embedder.py                 # Jina v3 late-chunking embedder
│   │   ├── splade_embedder.py          # SPLADE sparse embedder (GPU, Phase 4)
│   │   ├── store.py                    # Qdrant + SQLite storage facade (Phase 1–4)
│   │   ├── card_generator.py           # 8 card types, COSTAR prompts, instructor (Phase 2)
│   │   ├── raptor_tree.py              # GMM clustering + RAPTOR summaries (Phase 2)
│   │   ├── colpali_embedder.py         # ColPali multi-vector page embeddings (Phase 3)
│   │   ├── graph_builder.py            # Memgraph concept graph builder (Phase 3)
│   │   ├── image_store.py              # Page image storage abstraction (Phase 3)
│   │   └── prompts/                    # COSTAR-format prompt files (9 .md files)
│   │
│   └── frontend/
│       └── streamlit_app.py            # Student (3 tabs) + Admin (7 tabs) UI
│
├── scripts/
│   ├── ingest_base_textbook.py         # Admin: ingest global knowledge base
│   ├── run_phase2.py                   # Admin: generate cards + RAPTOR
│   ├── index_derivative_artifacts.py   # Admin: index DA cards into Qdrant
│   ├── run_phase3.py                   # Admin: generate ColPali + concept graph
│   ├── evaluate_rag.py                 # Evaluation: MRR / Recall / NDCG
│   ├── calibrate_eval_pages.py         # Evaluation: calibrate page annotations
│   ├── train_intent_classifier.py      # Training: intent router training pipeline
│   └── create_test_pdf.py              # Dev: create sample physics PDF
│
└── tests/
    ├── conftest.py                     # Shared fixtures (stubs, in-memory Qdrant)
    ├── test_phase1.py                  # Phase 1: ingestion pipeline
    ├── test_phase2.py                  # Phase 2: cards + RAPTOR
    ├── test_phase3.py                  # Phase 3: ColPali, image store, graph
    ├── test_phase_a.py                 # Phase A: DA retrieval, MMR, RRF
    └── test_integration_real.py        # Real Jina v3 integration tests
```

---

## Architecture Decisions

### Why Qdrant for concept embeddings (not Memgraph)?

Memgraph is a graph database optimised for traversal (Cypher queries, edge hops). It is not optimised for vector similarity search. Qdrant is purpose-built for ANN search using HNSW indexes (~5ms per lookup vs ~500ms over Bolt).

**Pattern used:** Qdrant finds concept names by embedding similarity → Memgraph traverses the concept graph from those names. Each system does what it is best at.

### Why a separate `derivative_artifacts` collection for DA retrieval?

Definition, formula, question, and factoid cards are denser and more targeted than source chunks. Searching them separately — and appending non-duplicate hits to the dense result set — expands recall for specific fact queries without disrupting the ranking of the top dense results. Interleaving via RRF was tested and degraded MRR by ~0.078; the recall-only append pattern recovered this without sacrificing MRR.

### Why MMR before DA expansion?

Maximal Marginal Relevance (λ=0.7) diversifies the dense candidate pool first so that the final top-K chunks cover different aspects of the query. DA expansion then fills remaining slots with additional relevant chunks that the dense search missed. Applying MMR after DA expansion would dilute the benefit of the dense ranking.

### Why RAPTOR? And when not to use it?

RAPTOR builds hierarchical cluster summaries at Phase 2 (once). At query time it is just a vector search — no summarisation happens live. It handles overview/synthesis queries that span many chunks. The intent router classifies queries and only invokes RAPTOR for overview-type questions.

### Why Memgraph over Neo4j?

Both use the same Bolt protocol and OpenCypher query language — the code is identical. Memgraph is in-memory first (faster for graph traversal), open-source, and free.

### Why ColPali multi-vector (not CLIP)?

CLIP produces a single embedding per image. ColPali produces a matrix of patch embeddings (~1000 patches per page) and uses MaxSim late-interaction scoring. This preserves spatial layout and local visual detail, making it significantly better at matching diagram/figure queries to specific page regions.

### Why embedding-based intent routing (not LLM or keyword-based)?

LLM classification adds 2–10s latency per query. Keyword-based routing is brittle. Embedding similarity against pre-embedded prototype queries uses the query vector already computed for dense search — zero extra model calls, zero extra latency.

### Why SPLADE over BM25 for sparse search?

BM25 matches exact terms only — "velocity" does not match "speed". SPLADE learns to activate related vocabulary tokens, capturing synonym matches that dense embeddings sometimes miss (especially for precise technical terminology).

### SPLADE per-environment guidance

SPLADE requires re-ingestion when first enabled (changes Qdrant collection schema to named vectors `dense` + `sparse`).

| Environment | `SPLADE_ENABLED` | Re-ingest needed? |
|---|---|---|
| GPU VM | `true` | Yes (once, fast on GPU) |
| Laptop, existing large corpus | `false` | No — dense search continues |
| Laptop, small PDF | `true` | Yes (seconds on CPU) |

### Why `config.yaml` for LLM endpoints?

Per-stage model configuration — card generation, RAPTOR summarisation, intent classification, evaluation — with different models and base URLs per stage. The instructor library wraps the OpenAI client to guarantee Pydantic-schema-conforming JSON outputs, eliminating fragile regex-based parsing.

### Why payload-based multi-tenancy (not separate collections)?

Payload filtering (`tenant_id`, `is_global_baseline`) keeps everything in one collection and allows cross-tenant baseline search with a single Qdrant call. The tradeoff is slightly slower searches at very high tenant counts (10,000+) — acceptable for an educational platform.

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Complete | Docling + Chonkie + Jina v3 + Qdrant + Streamlit |
| Phase 2 | ✅ Complete | 8-type card generation (COSTAR + instructor) + RAPTOR tree |
| Phase 3 | ✅ Complete | ColPali visual embeddings + Memgraph GraphRAG concept graph |
| Phase 4A | ✅ Complete | Intent router + SPLADE hybrid + DA retrieval lane + MMR |
| Phase 4B | 🔜 | Matryoshka two-stage (Jina MRL 64d fast filter → 768d rescore) |
| Phase 4C | 🔜 | Cross-encoder re-ranker (ColBERT MaxSim intermediate) |
| Phase 5 | 🔜 | DeBERTa guardrails + answer leakage guard |
| Phase 6 | 🔜 | Per-query observability (latency/route logging) + teacher dashboard |

---

## Multi-tenancy

Text data is stored in `knowledge_base`, DA cards in `derivative_artifacts`, and visual data in `visual_knowledge_base` — all with payload-based tenant isolation:

```json
{ "tenant_id": "global",      "source_type": "base_textbook", "is_global_baseline": true }
{ "tenant_id": "user_abc123", "source_type": "user_upload",   "is_global_baseline": false }
{ "tenant_id": "global",      "source_type": "raptor_summary" }
{ "tenant_id": "global",      "source_type": "page_image" }
```

The source toggle controls which filter is applied at query time — no separate collections per user needed.

---

## License

MIT
