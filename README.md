# Synapse Learning Worlds — Hybrid RAG Platform

An adaptive learning platform powered by Hybrid RAG (Retrieval-Augmented Generation).  
Pre-ingest a base textbook globally, let students upload their own PDFs, and answer questions from either source — or both.

> **Architecture:** Synapse Learning Worlds v3.1 · Author: Bharath Kumar

---

## Architecture Overview

```
Offline (admin, run once)              Online (runtime, per user)
──────────────────────────             ──────────────────────────
PDF → Docling → Chonkie               Student uploads PDF
    → Jina v3 (late chunking)             → same pipeline (Phase 1)
    → Qdrant (tenant_id=global)           → ColPali + graph async in background

Phase 2 artifacts (Llama 3.2):        Query flow:
  • 7 pedagogical cards/chunk            1. Jina v3 → Qdrant vector search
  • RAPTOR L1/L2/L3 summaries           2. RAPTOR cluster summaries
  • Stored: SQLite + Qdrant             3. Memgraph concept graph (GraphRAG)
                                         4. ColPali visual search (image query)
Phase 3 artifacts:
  • ColPali patch vectors / page       Retrieval routes by query type:
  • Concept graph in Memgraph            vector  → factual / point queries
  • Page images on local disk            raptor  → summaries / chapter overviews
  • Stored: SQLite + Qdrant             graphrag → multi-hop / prerequisite chains
            + Memgraph + disk            colpali → diagram / figure / table queries
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| PDF parsing | Docling (IBM) |
| Chunking | Chonkie `SentenceChunker` |
| Text embeddings | Jina v3 `jinaai/jina-embeddings-v3` (late chunking) |
| Visual embeddings | ColPali `vidore/colpali-v1.2` (multi-vector patch embeddings) |
| Vector store | Qdrant — text collection + visual collection (MaxSim) |
| Relational store | SQLite via SQLModel |
| Graph store | Memgraph (OpenCypher via neo4j Bolt driver) |
| Image store | Local disk (swappable to MinIO via `IMAGE_STORE_BACKEND=minio`) |
| LLM (cards + RAPTOR + concepts) | Llama 3.2 via Ollama |
| API | FastAPI |
| Frontend | Streamlit |
| Package manager | uv |

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 | Pinned via `.python-version` |
| [uv](https://docs.astral.sh/uv/) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Ollama](https://ollama.com) | latest | Required for Phase 2 + Phase 3 concept extraction |
| Llama 3.2 model | — | `ollama pull llama3.2` |
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
OLLAMA_HOST=http://localhost:11434           # Ollama must be running for Phase 2+3
OLLAMA_MODEL=llama3.2
```

### 3. Start Ollama (required for Phase 2 + Phase 3)

```bash
ollama serve          # start the Ollama server
ollama pull llama3.2  # download the model (~2 GB, one-time)
```

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

This parses the PDF with Docling, chunks it with Chonkie, embeds with Jina v3, and stores everything in Qdrant and SQLite.

> **First run** downloads the Jina v3 model (~570 MB) automatically.

### 6. Generate Phase 2 artifacts (cards + RAPTOR)

```bash
uv run python scripts/run_phase2.py --tenant global
```

Generates: **7 pedagogical cards per chunk** (summary, definition, example, misconception, question, objective, formula) + **RAPTOR hierarchical summaries** (up to 3 levels).

### 7. Generate Phase 3 artifacts (ColPali + Memgraph)

```bash
# Process all documents for a tenant (PDF path auto-detected from ingest record)
uv run python scripts/run_phase3.py --tenant global

# Or target one specific document by its ID
uv run python scripts/run_phase3.py --doc-id <uuid>

# Override the PDF path explicitly (useful if the file was moved)
uv run python scripts/run_phase3.py --tenant global \
  --pdf data/base_textbooks/your_textbook.pdf

# Re-run from scratch even if already processed (e.g. after clearing Memgraph)
uv run python scripts/run_phase3.py --tenant global --force
```

**What gets generated:**
- **ColPali patch vectors** — every PDF page rasterized and embedded as a matrix of patch vectors, stored in the `visual_knowledge_base` Qdrant collection. Enables image-level semantic search.
- **Concept graph in Memgraph** — Document → Chunk → Concept nodes with MENTIONS / RELATES_TO / PREREQUISITE_OF edges. Enables multi-hop GraphRAG retrieval.

**Smart resume** — if you re-run after a partial failure, Phase 3 automatically skips what's already done:
- ColPali is skipped if `PageImage` records already exist for the document in SQLite.
- Memgraph is skipped if the `Document` node already exists in the graph.
- Use `--force` to re-process everything from scratch.

**Tuning for local machines (low RAM):**
```env
# In .env — reduce pages loaded into memory at once
COLPALI_PAGE_BATCH_SIZE=2   # default is 4; drop to 2 if you hit OOM
```

> ColPali model (`vidore/colpali-v1.2`) downloads ~5 GB on first run and is cached to `MODEL_CACHE_DIR`.
> Memgraph must be running before Phase 3 starts. Skip Memgraph with `USE_STUB_GRAPH=true` if Docker is unavailable.

### 8. Launch the app

```bash
uv run streamlit run src/frontend/streamlit_app.py
```

Open **http://localhost:8501**

---

## GPU VM Setup (Support Vectors)

Running the 990-page Feynman textbook on CPU takes 30+ hours.
On the Support Vectors GPU VM with the remote Qdrant cluster, the same job
completes in **2-3 hours**.

### Step 1 — Copy and edit `.env`

```bash
cp .env.example .env
nano .env   # or use any editor
```

Fill in these values from your Support Vectors dashboard (leave all others as-is):

| Key | Where to get it | Example |
|---|---|---|
| `QDRANT_URL` | Support Vectors Qdrant dashboard → Cluster URL | `https://abc123.cloud.qdrant.io` |
| `QDRANT_API_KEY` | Support Vectors Qdrant dashboard → API Keys | `sv-xxxxxxxxxxxx` |
| `USE_GPU` | Set to `true` on the GPU VM | `true` |
| `EMBEDDING_BATCH_SIZE` | Increase for GPU | `32` |
| `CARD_GEN_WORKERS` | Parallel Ollama threads for card generation | `8` |
| `CONCEPT_GEN_WORKERS` | Parallel Ollama threads for concept extraction (Phase 3) | `8` |

Your `.env` on the GPU VM should look like:

```env
# Remote Qdrant cluster (Support Vectors)
QDRANT_URL=https://your-cluster-url.cloud.qdrant.io
QDRANT_API_KEY=your-api-key-from-dashboard

# GPU acceleration
USE_GPU=true
EMBEDDING_BATCH_SIZE=32

# Parallel Ollama workers (card generation + concept extraction)
CARD_GEN_WORKERS=8
CONCEPT_GEN_WORKERS=8
OLLAMA_TIMEOUT=60
```

### Step 2 — Install Ollama and pull the model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2
```

### Step 3 — Ingest the base textbook

```bash
uv run python scripts/ingest_base_textbook.py \
  --pdf data/base_textbooks/feynman_physics_vol1.pdf \
  --title "The Feynman Lectures on Physics Vol. 1" \
  --subject "Physics" \
  --grade "Undergraduate"
```

### Step 4 — Generate cards + RAPTOR tree

```bash
uv run python scripts/run_phase2.py --tenant global
```

### Step 5 — Generate ColPali + concept graph

```bash
# PDF path is auto-detected from the ingest record — no --pdf needed
uv run python scripts/run_phase3.py --tenant global

# If Phase 3 was interrupted, re-running resumes automatically (skips what's done)
# Use --force to start over completely
uv run python scripts/run_phase3.py --tenant global --force
```

### Step 6 — Launch the app

```bash
uv run streamlit run src/frontend/streamlit_app.py
```

### Speed breakdown (990 pages, 5,047 chunks)

| Stage | CPU laptop | GPU VM (estimated) |
|---|---|---|
| Docling parsing | ~2 hours | ~20 min (GPU layout model) |
| Jina v3 embedding | ~2 hours | ~15 min (batch_size=32, CUDA) |
| Card generation (sequential) | ~25 hours | ~3 hours (8 parallel workers) |
| RAPTOR tree | ~5 min | ~2 min |
| ColPali embedding (5k pages) | ~8 hours | ~45 min (GPU) |
| Concept graph (Memgraph) | ~2 hours | ~30 min (parallel Ollama) |
| **Total** | **~40 hours** | **~5 hours** |

---

## Portal Tabs

### Student view (default — http://localhost:8501)

| Tab | What it does |
|---|---|
| 📄 Upload PDF | Upload lecture notes / supplementary reading |
| 🔍 Ask a Question | Semantic search + GraphRAG concept results |
| 🃏 Study Cards | Flashcards by type (summary, definition, Q&A, etc.) |
| 🖼️ Visual Search | Upload an image to find matching pages (ColPali) |
| 🕸️ Concept Graph | Ask a multi-hop reasoning question (Memgraph GraphRAG) |

- Source toggle: **Textbook + My Notes** (default) / **My Notes only**
- No system internals exposed (no scores, IDs, or metadata)
- After uploading a PDF, visual embeddings + concept graph are built in the background automatically

### Admin / Teacher view (http://localhost:8501?admin=true)

All student tabs **plus**:

| Tab | What it does |
|---|---|
| 🌲 RAPTOR Tree | Hierarchical cluster summaries with full metadata |
| 📊 Admin Status | Chunk / card / RAPTOR / visual page counts + ColPali status per document |

- Full similarity scores, source types, tenant IDs, concept paths visible
- "Generate Phase 2 artifacts" button in sidebar
- Upload as base textbook or user upload

---

## Retrieval Routes

The platform routes queries across four retrieval mechanisms:

| Query type | Best route | Example |
|---|---|---|
| Specific fact / formula | **Vector search** | "What is the formula for kinetic energy?" |
| Chapter overview / synthesis | **RAPTOR** | "Summarize conservation laws across the textbook" |
| Multi-hop / prerequisite | **GraphRAG** | "Why does a satellite stay in orbit?" |
| Diagram / figure / table | **ColPali visual** | "Show me the double-slit experiment diagram" |

See `data/eval_queries.json` for 22 curated evaluation queries across all four routes.

---

## Run Tests

```bash
# Unit + integration tests (fast, stubs only — no model download, no Ollama needed)
uv run pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -v -m "not slow"

# Real Jina v3 integration test (downloads model on first run)
uv run pytest tests/test_integration_real.py -v -s

# Real Ollama card generation test (requires Ollama running)
uv run pytest tests/test_phase2.py::TestOllamaCardGeneration -v -s -m "slow"
```

All 81 tests pass (including 11 real Jina v3 integration tests).

---

## Project Structure

```
pdf_ingestion/
├── pyproject.toml                  # uv project — all deps + metadata
├── uv.lock                         # deterministic lockfile
├── .env.example                    # environment variable template
├── docker-compose.yml              # Memgraph + MinIO (Phase 3)
├── data/
│   └── eval_queries.json           # 22 evaluation queries (vector/raptor/graphrag/colpali)
│
├── src/
│   ├── core/
│   │   ├── config.py               # Pydantic settings (all env vars)
│   │   └── database.py             # SQLModel tables + Qdrant + Memgraph bootstrap
│   │
│   ├── pdf_ingestion/
│   │   ├── parser.py               # Docling PDF parser (+ page rasterization)
│   │   ├── chunker.py              # Chonkie semantic chunker
│   │   ├── embedder.py             # Jina v3 late-chunking embedder
│   │   ├── store.py                # Qdrant + SQLite storage facade (Phase 1-3)
│   │   ├── card_generator.py       # Llama 3.2 → 7 card types (Phase 2)
│   │   ├── raptor_tree.py          # GMM clustering + RAPTOR summaries (Phase 2)
│   │   ├── colpali_embedder.py     # ColPali multi-vector page embeddings (Phase 3)
│   │   ├── graph_builder.py        # Memgraph concept graph builder (Phase 3)
│   │   └── image_store.py          # Page image storage abstraction (Phase 3)
│   │
│   ├── frontend/
│   │   └── streamlit_app.py        # Student + Admin UI (5 student / 7 admin tabs)
│   │
│   ├── inference/                  # Phase 4 (intent router, BM25, RRF, re-ranker)
│   ├── governance/                 # Phase 5 (DeBERTa guardrails)
│   └── telemetry/                  # Phase 6 (Arize Phoenix)
│
├── scripts/
│   ├── ingest_base_textbook.py     # Admin: ingest global knowledge base
│   ├── run_phase2.py               # Admin: generate cards + RAPTOR
│   ├── run_phase3.py               # Admin: generate ColPali + concept graph
│   └── create_test_pdf.py          # Dev: create sample physics PDF
│
└── tests/
    ├── conftest.py                 # Shared fixtures (stubs, in-memory Qdrant)
    ├── test_phase1.py              # 20 unit tests — ingestion pipeline
    ├── test_phase2.py              # 27 unit tests — cards + RAPTOR
    ├── test_phase3.py              # 23 unit tests — ColPali, image store, graph, orchestration
    └── test_integration_real.py    # Real Jina v3 integration tests
```

---

## Architecture Decisions

Key design choices and the reasoning behind them.

### Why Qdrant for concept embeddings (not Memgraph)?

Memgraph is a graph database optimised for traversal (Cypher queries, edge hops). It is not optimised for vector similarity search — storing 1024-dim embeddings as node properties and fetching them over Bolt adds ~500ms per query.

Qdrant is purpose-built for ANN (Approximate Nearest Neighbour) search using HNSW indexes. A concept lookup in Qdrant takes ~5ms regardless of how many concepts exist.

**Pattern used:** Qdrant finds concept names by embedding similarity → Memgraph traverses the concept graph from those names. Each system does what it is best at.

### Why embedding-based concept search (not LLM at query time)?

The original approach called the LLM to extract concept names from every user query — adding 2–10s latency per search. Production GraphRAG systems (Neo4j, LlamaIndex, Memgraph's own recommended patterns) instead:

1. Embed concept names once at build time
2. At query time, use the already-computed query embedding (same one used for vector search) to find matching concepts via cosine similarity

No extra LLM call, no extra embedding call. Zero overhead on top of what the vector search already does.

### Why two storage systems for graph retrieval?

```
Qdrant concept_embeddings  →  find WHICH concepts match the query (~5ms)
Memgraph                   →  find WHICH chunks those concepts link to (~10ms)
                              + walk RELATES_TO / PREREQUISITE_OF edges
```

Splitting the concerns keeps both fast. A unified graph DB that also does fast ANN would need Memgraph's vector index feature (available but slower than Qdrant HNSW) or Neo4j's vector search (same tradeoff).

### Why RAPTOR? And when not to use it?

RAPTOR builds hierarchical cluster summaries at Phase 2 (once). At query time it is just a vector search — no summarisation happens live. It handles overview/synthesis queries that span many chunks ("summarise conservation laws") where a single chunk search would miss the big picture.

RAPTOR is NOT triggered for every query. The Phase 4 intent router will classify queries and only invoke RAPTOR for overview-type questions. For factual point queries ("what is F=ma?") RAPTOR adds latency with no benefit.

### Why Memgraph over Neo4j?

Both use the same Bolt protocol and OpenCypher query language — the code is identical. Memgraph is in-memory first (faster for graph traversal), open-source, and free. Neo4j Community Edition has graph size limits. The `neo4j` Python driver works with both.

### Why ColPali multi-vector (not CLIP)?

CLIP produces a single embedding per image. ColPali produces a matrix of patch embeddings (one per image patch, ~1000 patches per page) and uses MaxSim late-interaction scoring — the same approach as ColBERT for text. This preserves spatial layout and local visual detail, making it significantly better at matching diagram/figure queries to specific page regions.

### Why local Qdrant file store as default?

Zero-dependency local development — no Docker needed for Phase 1 and 2. Three modes are supported in priority order: `QDRANT_URL` (cloud or self-hosted URL) → `QDRANT_HOST:PORT` (self-hosted server) → local file. The GPU VM uses `QDRANT_HOST` + `QDRANT_PORT` pointing to a self-hosted server so ingestion scripts and the app can run concurrently (local file mode allows only one process at a time).

### Why payload-based multi-tenancy (not separate collections)?

Separate Qdrant collections per tenant would require creating collections dynamically and make cross-tenant baseline search (global textbook + user notes) require two separate queries. Payload filtering (`tenant_id`, `is_global_baseline`) keeps everything in one collection and allows flexible per-query filtering with a single search call. The tradeoff is slightly slower searches at very high tenant counts (10,000+) — acceptable for an educational platform.

### Why parallel concept extraction (ThreadPoolExecutor)?

LLM calls are IO-bound (waiting on HTTP response). The Python GIL does not block IO-bound threads, so `CONCEPT_GEN_WORKERS` threads provide real concurrency. Separating Phase A (parallel LLM extraction) from Phase B (sequential Cypher writes) avoids Memgraph session conflicts while maximising LLM throughput. Same pattern as `CARD_GEN_WORKERS` in Phase 2.

### Why store `source_path` on Document?

Phase 3 needs to rasterize the original PDF to extract page images for ColPali. If the PDF was moved or the configured base directories changed, the original filename alone is not enough to locate it. Storing the absolute path at ingest time makes Phase 3 reliable regardless of where scripts are run from.

### SPLADE per-environment guidance

SPLADE requires re-ingestion when first enabled because it changes the Qdrant collection schema from unnamed to named vectors (`dense` + `sparse`). This is a one-time cost.

**GPU VM** — enable SPLADE (default):
```env
SPLADE_ENABLED=true
```
Re-ingest after pulling. SPLADE encodes ~5000 Feynman chunks in minutes on GPU.

**Laptop with existing Feynman data** — disable SPLADE to avoid a slow re-ingest:
```env
SPLADE_ENABLED=false
```
No data wipe needed. Dense-only search continues to work. The intent router, GraphRAG, and re-ranker all work regardless of this setting.

**Laptop with a small PDF (< 200 chunks)** — SPLADE is fine on CPU:
```env
SPLADE_ENABLED=true
```
Re-ingest takes seconds. Query-time SPLADE encoding adds ~50-100ms on the first warm-up query, then stays fast.

| Environment | SPLADE_ENABLED | Re-ingest needed? | Ingest speed |
|---|---|---|---|
| GPU VM | `true` | Yes (once) | Fast (~minutes) |
| Laptop, existing large corpus | `false` | No | N/A |
| Laptop, small PDF | `true` | Yes (once) | Fast (~seconds) |

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Complete | Docling + Chonkie + Jina v3 + Qdrant + Streamlit |
| Phase 2 | ✅ Complete | Llama 3.2 card generation + RAPTOR tree (up to 3 levels) |
| Phase 3 | ✅ Complete | ColPali visual embeddings + Memgraph GraphRAG concept graph |
| Phase 4 | 🔜 Next | Intent router + BM25 + RRF + cross-encoder re-ranker |
| Phase 5 | 🔜 | DeBERTa guardrails + answer leakage guard |
| Phase 6 | 🔜 | Arize Phoenix telemetry + Teacher/Student portals |

---

## Multi-tenancy

Text data is stored in a **single Qdrant collection** (`knowledge_base`) and visual data in a second collection (`visual_knowledge_base`), both with payload-based tenant isolation:

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
