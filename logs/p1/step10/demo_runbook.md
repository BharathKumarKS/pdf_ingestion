# Synapse — demo runbook (verified 2026-11-02)

> The exact commands that WORK, the ones that DON'T, and what to expect. Everything here was run and
> confirmed on 2026-11-02.

---

## 0. Pre-flight (30 s)

```bash
# 1) the cluster must be reachable
curl -s -m 5 -o /dev/null -w "LLM router   :%{http_code}\n" http://10.0.10.70:8000/v1/models
curl -s -m 5 -o /dev/null -w "embeddings   :%{http_code}\n" http://10.0.10.70:8123/
curl -s -m 5 http://10.0.10.65:6333/collections/knowledge_base_v3 | head -c 120   # expect "green", 3869
docker ps --format '{{.Names}}\t{{.Status}}' | grep memgraph                     # expect Up
```

Expected: LLM router 200 · embeddings 404 (no root route — it's UP) · v3 `green`/`3869` · memgraph Up.
**Qdrant is on `10.0.10.65`** (not the local docker `synapse_qdrant`, which is empty).

## 1. Environment (required — without it the app silently uses the WRONG index)

```bash
cd /Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65
export QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5"
export DENSE_DIM=768
export DENSE_DIM_LOW=64
export DOCUMENT_PREFIX="search_document: "
export QUERY_INSTRUCTION="search_query: "
export DA_ENABLED=true
```

## 2. Start the app — the ONE command that works

```bash
.venv/bin/streamlit run src/frontend/streamlit_app.py \
  --server.headless true --server.port 8503 --server.fileWatcherType none
```

⚠️ **Do NOT use `uv run streamlit`** — it resolves to a conda shim and dies with a conda `TypeError`
(`expected str, bytes or os.PathLike object, not NoneType`). Use the venv binary directly.

⚠️ **Ports 8501 and 8502 are already taken** by the *other* repo's apps (AI_Agents_Bootcamp). Use
**8503** (verified free).

⚠️ Ignore these, they are noise and do NOT affect the app:
* `An unexpected error has occurred. Conda has prepared the above report.` **followed by**
  `TypeError: expected str, bytes or os.PathLike object, not NoneType` — this is a conda **shell-hook**
  artifact that prints BEFORE the app starts (the very next lines are `Uvicorn server started on :::8503`
  and `You can now view your Streamlit app`). It appears in every launch, working or not.
* `Transient error ... localhost:6007/v1/traces` + `Failed to export span batch` (Phoenix is off)
* On exit only: `libc++abi: ... recursive_mutex lock failed` (a client shutdown race)

Confirm it is up:
```bash
curl -s -m 5 http://localhost:8503/_stcore/health     # expect: ok
```

## 3. The demo queries (verified end to end)

Ask these in **🔍 Ask a Question**. Both returned real answers with page citations:

1. **Factual** — `What is Newton's second law?`
   → ~66 s; reranker kept 20/82; answer cites the Feynman passages.
2. **Overview (the hard type)** — `How does Feynman develop the concept of conservation of energy across
   mechanics, waves and thermodynamics?`
   → ~96 s; answer synthesises mechanics + relativity + quantum + thermodynamics, citing pages
   **251 / 94 / 316 / 921**.

> Point out live: the *retrieval metric* for overview is our weakest, yet the *answer* reads well —
> that is the "generator unmeasured" tension, stated honestly rather than hidden.

## 4. What to say about each tab (so nothing surprises you)

| tab | state |
|---|---|
| 🔍 Ask a Question | ✅ verified live (above) |
| 🃏 Learning Cards | ✅ 82k cards in SQLite (shows the OLD doc — see caveat) |
| 🌲 RAPTOR Tree | ✅ 84/146 nodes |
| 🕸️ Concept Graph | ✅ Memgraph: 3,533 chunks · 907 pages · 6,065 concepts · 21,670 edges |
| 🖼️ Visual Search | ⚠️ works, but backed by the OLD doc's ColPali vectors (1,033) |
| 📄 Upload PDF | not exercised — needs a PDF (don't demo it live) |

## 5. Known caveats — say these before the mentor finds them

1. **Visual lane**: `visual_knowledge_base` holds **1,033 vectors, all for the OLD doc (6d55c52b)**;
   the current index is doc **7ba61432**, which has none (its `colpali_status='ready'` is stale). Both
   are the same 968-page PDF, so page numbers coincide and the results are the right pages of the right
   book — but it is not the current document's embeddings. The 33 visual queries carry no labels, so the
   lane is **not measurable**.
2. **The app's status panel shows the OLD doc** (`list_documents(global)[0]` returns 6d55c52b) while
   search queries the current index. Same PDF → low impact, but visible on an admin screen.
3. **Generator stage is unmeasured** — everything measured is retrieval.
4. **Test suite**: 736 passed / 4 failed / 6 skipped; the 4 are a documented pre-existing set.

## 6. If something fails

* App won't start → port in use. `lsof -nP -iTCP:8503 -sTCP:LISTEN`; pick another free port.
* Search hangs → the cluster LLM/embeddings are down; re-run the pre-flight.
* "No textbook loaded yet" → the env vars in §1 were not exported.
* Stop the app: `kill <pid>` (find it with `lsof -nP -iTCP:8503 -sTCP:LISTEN`).
