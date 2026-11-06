# Synapse — LIVE demo runbook (2026-11-02)

App is RUNNING now: **http://localhost:8503**

If you need to relaunch it:
```bash
cd /Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3 \
  DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5" DENSE_DIM=768 DENSE_DIM_LOW=64 \
  DOCUMENT_PREFIX="search_document: " QUERY_INSTRUCTION="search_query: " DA_ENABLED=true
.venv/bin/streamlit run src/frontend/streamlit_app.py \
  --server.headless true --server.port 8503 --server.fileWatcherType none
```
Health check: `curl -s http://localhost:8503/_stcore/health` → `ok`.
⚠️ Do NOT use `uv run streamlit` (conda shim → TypeError). Ports 8501/8502 belong to the other repo.

---

## Per-tab: what to click, and a query for each

### 1. 🔍 Ask a Question  (the main event — one query per query type)

| type | paste this | expect |
|---|---|---|
| **Factual** | `What is Newton's second law?` | ~66 s; answer cites the Feynman passages |
| **Factual (short)** | `What is the title of section 42-4?` | fast; a page citation |
| **Overview** (the hard type) | `How does Feynman develop the concept of conservation of energy across mechanics, waves and thermodynamics?` | ~96 s; synthesises mechanics + relativity + quantum + thermodynamics, cites pages 251 / 94 / 316 / 921 |
| **Overview (alt)** | `How does Feynman develop the principle of conservation of momentum throughout Volume 1 of The Feynman Lectures?` | long, multi-page synthesis |
| **Multihop** | `How did astronomers discover that stars are made of atoms of the same kind as those on Earth?` | the **graph lane** fires here (concept graph) |
| **Multihop (alt)** | `When a mass moves only along the radius, which quantity stays constant and how is the torque τ related to the rate of change of angular momentum?` | multi-concept |

> Say out loud: overview has our **weakest retrieval metric** yet reads well as an answer — that is
> the honest "generator stage is being measured" tension (a `v3_judged_full` run is in flight).

### 2. 🃏 Learning Cards
82k cards in SQLite. Browse by document. ⚠️ It shows the **OLD** doc (`6d55c52b`) — same PDF, so the
content is right; the id is not the live index.

### 3. 🌲 RAPTOR Tree
84 / 146 summary nodes.

### 4. 🕸️ Concept Graph
Memgraph: 3,533 chunks · 907 pages · 6,065 concepts · 21,670 edges. (Needs Docker `synapse_memgraph` up.)

### 5. 🖼️ Visual Search
✅ **Now backed by the CURRENT doc** — 968 ColPali page vectors were written for doc `7ba61432` today
(plus 1,033 for the old doc). Try:
`Show me the figure that displays water magnified one billion times.`
or `Show me the schematic diagram of DNA from Fig. 3-2.`
⚠️ The 33 visual queries carry no labels, so this lane is populated but **not measurable**.

### 6. 📄 Upload PDF
Admin only — **do not demo it live** (needs a PDF).

### 7. 📊 Status
Shows the **OLD** doc (`list_documents(global)[0]` → `6d55c52b`) while search queries the live index.
Same PDF → low impact, but visible on an admin screen.

---

## Caveats to state before your mentor finds them
1. Generator stage — now **being measured** (`v3_judged_full`, 200 queries, per-type faithfulness +
   answer_relevance); results pending.
2. Visual lane — populated for the current doc, but **not measurable** (no labels on the 33 queries).
3. Status panel shows the old doc id (same PDF).
4. Test suite: 736 passed / 4 failed / 6 skipped — the 4 are a documented pre-existing set.

## If something breaks
* App won't start → port in use: `lsof -nP -iTCP:8503 -sTCP:LISTEN`, pick another free port.
* Search hangs → the cluster (10.0.10.70:8000/8123) is down; re-run the health checks.
* "No textbook loaded yet" → the env vars above were not exported.
* Stop the app: `kill $(lsof -nP -iTCP:8503 -sTCP:LISTEN -t)`.
