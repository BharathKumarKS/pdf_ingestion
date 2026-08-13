# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Project: Synapse Learning Worlds

Hybrid RAG platform for physics education. Three ingestion phases, multi-tenant.

### Run commands

```bash
# Install
uv sync

# Start app
uv run streamlit run src/frontend/streamlit_app.py

# Run tests (fast — all stubs, no model downloads)
uv run pytest tests/ -q -m "not slow"

# Ingest base textbook (Phase 1)
uv run python scripts/ingest_base_textbook.py --pdf data/base_textbooks/feynman.pdf --title "..." --subject "Physics" --grade "Undergraduate"

# Phase 2: cards + RAPTOR
uv run python scripts/run_phase2.py --tenant global

# Phase 3: ColPali + Memgraph graph
uv run python scripts/run_phase3.py --tenant global
uv run python scripts/run_phase3.py --doc-id <uuid> --graph-only   # rebuild graph only
```

### Key architecture

- **Phase 1** — Docling parser → Chonkie chunker → Jina v3 embedder → Qdrant `knowledge_base`
- **Phase 2** — LLM card generation (7 types/chunk) + RAPTOR hierarchical summaries
- **Phase 3** — ColPali page images → `visual_knowledge_base` + Memgraph concept graph + Qdrant `concept_embeddings`
- **Phase 4** — Intent router (embedding-based) + SPLADE hybrid search (dense+sparse RRF) + cross-encoder re-ranker (next)

### Retrieval flow at query time

```
query → Jina embed (q_vec)
      → Intent router (classify: factual|overview|multihop|visual)
      → Qdrant hybrid search: dense (Jina) + sparse (SPLADE) → RRF → top-6 chunks
      → RAPTOR search (overview only) → 2 summary nodes
      → Qdrant concept_embeddings ANN → Memgraph Cypher → graph chunks (multihop only)
      → [next] cross-encoder re-rank top chunks
```

### SPLADE per-environment

- **GPU VM**: `SPLADE_ENABLED=true` — re-ingest required (named vector collection)
- **Laptop with existing Feynman data**: `SPLADE_ENABLED=false` — no re-ingest needed
- **Laptop with small PDF**: `SPLADE_ENABLED=true` — re-ingest takes seconds

### Test conventions

- All stubs active by default in tests: `USE_STUB_EMBEDDER`, `USE_STUB_LLM`, `USE_STUB_COLPALI`, `USE_STUB_GRAPH`, `USE_STUB_SPLADE`
- `QDRANT_IN_MEMORY=true` in tests — no file lock conflicts
- Singletons reset between tests via `reset_db_singletons` autouse fixture
- Slow tests (real embedder, real model) marked `@pytest.mark.slow` and skipped by default

### Key files

```
src/core/config.py              — all Settings fields
src/core/database.py            — Qdrant + SQLite bootstrap, migrations
src/core/intent_router.py       — query intent classification (Phase 4)
src/core/llm.py                 — shared LLM caller (Ollama or OpenAI-compatible)
src/pdf_ingestion/store.py      — DocumentStore: save/search for all phases
src/pdf_ingestion/embedder.py   — Jina v3 dense embedder
src/pdf_ingestion/splade_embedder.py — SPLADE sparse embedder (Phase 4)
src/pdf_ingestion/graph_builder.py  — Memgraph concept graph (Phase 3)
src/pdf_ingestion/colpali_embedder.py — ColPali page embedder (Phase 3)
src/frontend/streamlit_app.py   — Streamlit UI (student + admin tabs)
```

### LLM backend

Set in `.env`:
```env
LLM_BACKEND=openai              # or "ollama"
OPENAI_API_BASE=http://your-cluster
OPENAI_MODEL=meta-llama/Llama-3.2-8B-Instruct
```

### Commit convention

Include model used:
```
Model: claude-sonnet-4-6[1m]
Co-Authored-By: Claude Sonnet 4.6 (1M context) <claude-sonnet-4-6[1m]@anthropic.com>
```

