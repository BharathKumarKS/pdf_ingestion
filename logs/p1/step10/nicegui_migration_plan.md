# NiceGUI frontend — ADDITIONAL to Streamlit (plan, not a replacement)

> **Scope decision (owner, 2026-11-02): the Streamlit app stays the supported, primary frontend.**
> NiceGUI is added **alongside** it. Nothing in `src/frontend/streamlit_app.py` changes; both apps
> run independently against the **same, unmodified** backend.
>
> Status: **design only.** Nothing here is built. Per this repo's discipline each phase below carries
> its own independent verifier before it is accepted.

---

## 0. Why keep both

* **Streamlit is the demo frontend and it works today** — verified live on port 8503, with a pinned
  runbook (`logs/p1/step10/demo_runbook.md`). The capstone demo must not depend on an unproven UI.
* NiceGUI buys what Streamlit is weak at: a real asyncio event loop, per-element reactivity, and
  `run.io_bound` for the 60–90 s blocking retrieval calls — i.e. a responsive UI without Streamlit's
  whole-script-rerun model.
* Keeping both is also the **safe** path: the NiceGUI app can be validated against the identical
  backend and the two can be compared on the same queries.

---

## 1. Feature inventory (real call sites, read from `src/frontend/streamlit_app.py`)

The app has **eight tabs** in two groups (`streamlit_app.py:368` admin group; `:379` student group):

| tab | what it does | backend call (real symbol) |
|---|---|---|
| **Upload PDF** (`:394`) | ingest an uploaded PDF | `DocumentStore.save_*` ingestion path; admin only |
| **Ask a Question** (`:481`) | the retrieval + synthesis path | `intent_router.get_intent_router(cfg).classify(q_vec)` (`:526-528`), `llm.call_llm` for HyDE (`:540`) and for synthesis (`:653`), `DocumentStore.search_fused` / `search_raptor` (`:592`) |
| **Learning Cards** (`:847`) | browse cards per document | `DocumentStore.get_cards` / `get_cards_for_chunks` (`:872`, `:892`) |
| **Figure / Visual results** (`:1129`) | show page images + results | `DocumentStore.count_visual_vectors` (`:336`), `_render_visual_results` (`:1101`) |
| **RAPTOR Tree** (`:965`) | browse summary nodes | `DocumentStore.get_raptor_tree` (`:331`) |
| **Visual Search** (`:1193`) | ColPali page search | `DocumentStore.search_raptor` / visual search path |
| **Concept Graph** (`:1297`) | browse the Memgraph graph | `graph_builder.get_graph_builder(cfg)` (`:611`) |
| **Status** (`:1401`) | corpus/index status panel | `DocumentStore.list_documents` (`:303`, `:325`) |

⚠️ **The two real, non-obvious entry points** are `src/core/llm.py::call_llm` (there is **no**
`get_response`) and `src/pdf_ingestion/graph_builder.py::get_graph_builder` (the public accessor;
`build_graph` is a method on the returned builder). `src/core/intent_router.py` exposes
`get_intent_router` + `ROUTE_MAP`.

---

## 2. NiceGUI equivalents (primitive named, and why)

| feature | NiceGUI primitive | why |
|---|---|---|
| the 8 tabs | `ui.tabs()` / `ui.tab()` / `ui.tab_panels()` / `ui.tab_panel()` | one-to-one with `st.tabs`; panels keep state |
| question box | `ui.input(placeholder=...)` + `ui.button('Search')` | explicit event handlers instead of a full-script rerun |
| the answer | `ui.markdown(...)` (and `ui.chat_message` if a conversational feel is wanted) | NiceGUI renders markdown natively; `chat_message` groups Q/A turns |
| source list | `ui.table(rows=...)` or `ui.list()` | sortable/scrollable page list |
| long call progress | `ui.spinner()` + `ui.linear_progress()` + a `ui.timer` | show liveness during the 60–90 s retrieval |
| card browser | `ui.table` + `ui.expansion()` per card | collapsible cards |
| page image / figure | `ui.image(src=...)` inside `ui.card()` | direct image binding |
| PDF upload | `ui.upload(on_upload=...)` | streaming upload handler |
| admin vs student | `ui.tabs` gated by a role value; `element.set_visibility(bool)` | hide/show, not re-render |
| graph / status | `ui.table` / `ui.tree` + `ui.label` | read-only views |

⚠️ **No `ui.session` and no `ui.visible`** — the correct NiceGUI APIs are `app.storage.*` (§4) and
`element.set_visibility(...)` / `element.visible = ...`.

---

## 3. The async model (the part that must not be got wrong)

NiceGUI runs on **asyncio**. The retrieval path is **blocking** (cluster HTTP, ~60–90 s per query),
so calling it directly on the event loop would freeze the whole UI.

* Wrap every blocking backend call in **`from nicegui import run; await run.io_bound(fn, *args)`** —
  it runs `fn` in a worker thread and returns its result without blocking the loop.
* Show a `ui.spinner()` (or `ui.linear_progress()`) **before** the await and remove it after.
* Do **not** use `asyncio.create_task` for the retrieval call itself — a blocking function scheduled
  on the loop still blocks it; `run.io_bound` is the correct tool. `create_task` is fine for a
  fire-and-forget *async* helper, not for a blocking one.
* One query at a time per user; the cluster is a single point of failure (the runbook records a
  ~30 min outage on 2026-11-02), so surface a timeout/error banner rather than hanging.

---

## 4. Session and state

* Role (student vs admin) and any per-user state go in **`app.storage.user`** (per-browser session;
  requires `ui.run(storage_secret=...)`). Do **not** use `ui.session`.
* Per-connection transient state (e.g. an in-flight query) → `app.storage.client`.
* The Streamlit app's role gating is its own thing and is **left as is**; the NiceGUI role flag is
  independent.

---

## 5. Dependencies and launch (both apps)

```bash
# add the dependency (one line)
uv add nicegui            # httpx is already present

# --- Streamlit: UNCHANGED, still the primary/demo frontend ---
.venv/bin/streamlit run src/frontend/streamlit_app.py \
  --server.headless true --server.port 8503 --server.fileWatcherType none

# --- NiceGUI: the ADDITIONAL frontend, a DIFFERENT free port ---
.venv/bin/python src/frontend/nicegui_app.py     # module calls ui.run(port=8504, ...)
```

* Use the **venv binary directly**, not `uv run` (the runbook records that `uv run streamlit`
  resolves to a conda shim and dies with a `TypeError`).
* **Ports:** 8501/8502 are taken by the other repo; **8503 is the Streamlit app**; give NiceGUI
  **8504**.
* Both apps need the same env (runbook §1): `QDRANT_HOST=10.0.10.65`,
  `QDRANT_COLLECTION=knowledge_base_v3`, `DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5`, `DENSE_DIM=768`,
  `DENSE_DIM_LOW=64`, `DOCUMENT_PREFIX='search_document: '`, `QUERY_INSTRUCTION='search_query: '`,
  `DA_ENABLED=true`. Without them the app silently uses the wrong index.

---

## 6. Phased build order (a verifier per phase)

| phase | deliverable | verification |
|---|---|---|
| **P1** | `src/frontend/nicegui_app.py` skeleton: `ui.run(port=8504)`, one page, an env/config echo | launch it; `curl localhost:8504` returns 200; the echoed config matches the env (§5) |
| **P2** | the **Ask a Question** tab only: input → `run.io_bound(run_retrieval)` → markdown answer + source table | run the demo runbook's two queries; the answer + cited pages match the Streamlit app's on the same queries |
| **P3** | **Status** + **Cards** + **RAPTOR** tabs (read-only) | row counts match `DocumentStore.list_documents` / `get_cards` / `get_raptor_tree` |
| **P4** | **Visual** + **Graph** tabs | page images render; graph nodes match `get_graph_builder(cfg)` |
| **P5** | **Upload** (admin) | a small PDF ingests and appears in Status |
| **P6** | role gating + error/timeout banners | role flag hides admin tabs; a killed cluster shows a banner, not a hang |

Each phase: an **independent verifier** (a second model, read-only) before the phase is accepted —
this repo's standing rule (one verifier per step, not one at the end).

---

## 7. Risks / unknowns

* **NiceGUI dependency weight** — pulls FastAPI/uvicorn; verify it does not perturb the existing
  `pyproject.toml` resolution (run the suite after `uv add`).
* **`run.io_bound` thread safety** — the backend singletons (`get_settings`, `get_cluster_embedder`,
  `get_reranker`) are process-global; concurrent queries from multiple browser sessions share them.
  The Streamlit app serialises; NiceGUI must either serialise per user or the singletons must be
  shown thread-safe (unverified).
* **Long-call UX** — a 60–90 s await needs a visible spinner + a timeout, or it reads as a hang.
* **Two frontends to maintain** — accepted deliberately: Streamlit is the demo-safe path, NiceGUI is
  the responsive path.
* **Not measured / out of scope** — auth, multi-tenant, and any change to the retrieval path. This
  plan adds a UI only.
