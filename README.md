# Synapse Learning Worlds — Hybrid RAG Platform

An adaptive learning platform powered by Hybrid RAG (Retrieval-Augmented Generation).  
Pre-ingest a base textbook globally, let students upload their own PDFs, and answer questions from either source — or both.

> **Architecture:** Synapse Learning Worlds v3.1 · Author: Bharath Kumar

---

## Architecture Overview

```
Offline (admin, run once)          Online (runtime, per user)
──────────────────────────         ──────────────────────────
PDF → Docling → Chonkie            Student uploads PDF
    → Jina v3 (late chunking)          → same pipeline
    → Qdrant (tenant_id=global)        → Qdrant (tenant_id=user)

Phase 2 artifacts (Llama 3.2):    Query flow:
  • 7 pedagogical cards/chunk        Intent → Qdrant filter
  • RAPTOR L1/L2 summaries           → chunks + RAPTOR summaries
  • Stored: SQLite + Qdrant          → ranked results
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| PDF parsing | Docling (IBM) |
| Chunking | Chonkie `SentenceChunker` |
| Text embeddings | Jina v3 `jinaai/jina-embeddings-v3` (late chunking) |
| Visual embeddings | ColPali (Phase 3) |
| Vector store | Qdrant (local persistent, no Docker required for dev) |
| Relational store | SQLite via SQLModel |
| LLM (card gen + RAPTOR) | Llama 3.2 via Ollama |
| API | FastAPI |
| Frontend | Streamlit |
| Package manager | uv |

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 | Pinned via `.python-version` |
| [uv](https://docs.astral.sh/uv/) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Ollama](https://ollama.com) | latest | Required for Phase 2 card generation |
| Llama 3.2 model | — | `ollama pull llama3.2` |

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
OLLAMA_HOST=http://localhost:11434           # Ollama must be running for Phase 2
OLLAMA_MODEL=llama3.2
```

### 3. Start Ollama (required for Phase 2)

```bash
ollama serve          # start the Ollama server
ollama pull llama3.2  # download the model (~2 GB, one-time)
```

### 4. Ingest the base textbook (admin step — run once)

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

### 5. Generate Phase 2 artifacts (cards + RAPTOR)

```bash
uv run python scripts/run_phase2.py --tenant global
```

This generates:
- **91 cards** (7 pedagogical types × number of chunks) via Llama 3.2
- **RAPTOR tree** (cluster summaries L1 + meta-summary L2) stored in Qdrant

### 6. Launch the app

```bash
uv run streamlit run src/frontend/streamlit_app.py
```

Open **http://localhost:8501**

---

## Two Portals

### Student view (default — http://localhost:8501)

| Tab | What it does |
|---|---|
| 📄 Upload PDF | Upload lecture notes / supplementary reading |
| 🔍 Ask a Question | Semantic search with relevance indicators |
| 🃏 Study Cards | Flashcards by type (summary, definition, Q&A, etc.) |

- Source toggle: **Textbook + My Notes** (default) / **My Notes only**
- No system internals exposed (no scores, IDs, or metadata)

### Admin / Teacher view (http://localhost:8501?admin=true)

All student tabs **plus**:

| Tab | What it does |
|---|---|
| 🌲 RAPTOR Tree | Hierarchical cluster summaries with full metadata |
| 📊 Admin Status | Chunk counts, card counts, embedding versions, document table |

- Full similarity scores, source types, tenant IDs visible
- "Generate Phase 2 artifacts" button in sidebar
- Upload as base textbook or user upload

---

## Run Tests

```bash
# Unit tests (fast, no model download, no Ollama needed)
uv run pytest tests/test_phase1.py tests/test_phase2.py -v -m "not slow"

# Real Jina v3 integration test (downloads model on first run)
uv run pytest tests/test_integration_real.py -v -s

# Real Ollama card generation test (requires Ollama running)
uv run pytest tests/test_phase2.py::TestOllamaCardGeneration -v -s -m "slow"
```

---

## Project Structure

```
pdf_ingestion/
├── pyproject.toml                  # uv project — all deps + metadata
├── uv.lock                         # deterministic lockfile
├── .env.example                    # environment variable template
├── docker-compose.yml              # Memgraph + MinIO (Phase 3+)
│
├── src/
│   ├── core/
│   │   ├── config.py               # Pydantic settings (all env vars)
│   │   └── database.py             # SQLModel tables + Qdrant bootstrap
│   │
│   ├── pdf_ingestion/
│   │   ├── parser.py               # Docling PDF parser
│   │   ├── chunker.py              # Chonkie semantic chunker
│   │   ├── embedder.py             # Jina v3 late-chunking embedder
│   │   ├── store.py                # Qdrant + SQLite storage facade
│   │   ├── card_generator.py       # Llama 3.2 → 7 card types
│   │   └── raptor_tree.py          # GMM clustering + RAPTOR summaries
│   │
│   ├── frontend/
│   │   └── streamlit_app.py        # Student + Admin UI
│   │
│   ├── inference/                  # Phase 4 (intent router, query engine)
│   ├── governance/                 # Phase 5 (DeBERTa guardrails)
│   └── telemetry/                  # Phase 6 (Arize Phoenix)
│
├── scripts/
│   ├── ingest_base_textbook.py     # Admin: ingest global knowledge base
│   ├── run_phase2.py               # Admin: generate cards + RAPTOR
│   └── create_test_pdf.py          # Dev: create sample physics PDF
│
└── tests/
    ├── conftest.py                 # Shared fixtures (stub embedder, in-memory Qdrant)
    ├── test_phase1.py              # 20 unit tests — ingestion pipeline
    ├── test_phase2.py              # 27 unit tests — cards + RAPTOR
    └── test_integration_real.py    # Real Jina v3 + Ollama integration tests
```

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Complete | Docling + Chonkie + Jina v3 + Qdrant + Streamlit |
| Phase 2 | ✅ Complete | Llama 3.2 card generation + RAPTOR tree |
| Phase 3 | 🔜 Next | ColPali visual embeddings + Memgraph GraphRAG |
| Phase 4 | 🔜 | Intent router + BM25 + RRF + cross-encoder re-ranker |
| Phase 5 | 🔜 | DeBERTa guardrails + answer leakage guard |
| Phase 6 | 🔜 | Arize Phoenix telemetry + Teacher/Student portals |

---

## Multi-tenancy

All data is stored in a **single Qdrant collection** with payload-based isolation:

```json
{
  "tenant_id": "global",          // base textbook
  "source_type": "base_textbook",
  "is_global_baseline": true
}

{
  "tenant_id": "user_abc123",     // student upload
  "source_type": "user_upload",
  "is_global_baseline": false
}
```

The source toggle controls which filter is applied at query time — no separate collections needed.

---

## License

MIT
