# HANDOFF.md — current work state

> **Living document.** This is *where we are right now*, not what the system is.
> For the durable system map read `ARCHITECTURE.md`. For setup read `README.md`.
> Keep this file short — it loads into every session in this directory.

---

## Scope decision (settled)

**Building single-user now.** The `tenant_id` plumbing exists in the schema but is
**not enforced** — there is no authentication, and the UI takes the tenant from a
text box (`st.text_input("User ID")`). This is a known, deliberate deferral:
**multi-tenancy is the final stage, after metrics are solid.**

Consequence: do not "fix" auth or tenant isolation if asked to work on metrics.
Do not add new `tenant_id` defaults either — see the trap list.

---

## Current focus

**P0 item 1 — freeze and commit a reproducible eval baseline.**

Running `evaluate_rag.py` is not yet meaningful because the last recorded run is
`data/eval_results/v9_fixed_lab_2026-08-27_0509.md`. The technical report quotes a
"v10" figure of `Recall@100 = 0.847` that has **no artifact on disk**. Until a run is
saved, every later metric has no baseline to compare against.

### Prerequisite status (re-checked 2026-10-04 — `scripts/preflight.py`, 24/24 pass)

Point the eval at the **cluster** index: `QDRANT_HOST=10.0.10.65`. No `.env` edit is
needed — `config.py` uses pydantic-settings `env_file`, and environment variables take
precedence over the file.

1. **Qdrant** — ✅ cluster index `10.0.10.65` is the reference; the graph pairs with it,
   not with the laptop's file store. `knowledge_base` 5,135 pts
   (dense_64/dense_768/colbert/sparse), `derivative_artifacts` 81,837,
   `visual_knowledge_base` 2,923, `concept_embeddings` 11,229.
   ⚠️ In **file** mode `store.py:301` skips the ColBERT lane (`not is_local` guard), so
   ColBERT only runs against a server/cluster Qdrant.
2. **Cluster endpoint** — ✅ `.70` live for rerank / sparse / multivector.
   ⚠️ But generation is broken by default — see the backend split below.
3. **Intent classifier** — ✅ present (768d); still a gitignored pickle on a loose
   `scikit-learn>=1.5` floor (P0 item 3).
4. **Memgraph** — ✅ reachable; after cleanup 1 doc / 5,051 chunks / 7,815 concepts, and
   **0.0%** of graph chunk ids absent from Qdrant.

### Fixed 2026-10-04 — the pipeline LLM pointed at a dead model

`.70` fronted **two backends behind one gateway**, and only one was up:

| `owned_by` | models | `chat/completions` |
| --- | --- | --- |
| `vllm` | gpt-oss-20b, DeepSeek-R1-Distill-Qwen-7B, Qwen3-VL-8B-Instruct | ✅ 200 |
| `inference` | gpt-oss-120b, Qwen-Image, Wan2.2-T2V-A14B | ❌ **502** "Backend inference unreachable after 3 attempts" |

Both `config.yaml` (all four sections) and `.env` `OPENAI_MODEL` named `gpt-oss-120b`,
so **every** LLM stage — card generation, RAPTOR summarisation, intent classification,
eval judging — was silently dead. Repointed both to `gpt-oss-20b`, old values commented.
This restores what HEAD had; the uncommitted Aug-24 working-tree edit to `-120b` was the
regression.

Two traps it exposed:

- **`/v1/models` is not a liveness check.** It answers from the gateway registry while the
  backend behind a given model is down. `preflight.py` initially reported all-clear on a
  pipeline that could not generate a single token; it now issues a **real completion** per
  configured model.
- **The gateway returns HTTP 500 for an empty `Authorization: Bearer` header.** The eval
  judge defaults `judge_api_key` to `""` and only reads config under `--judge-from-env` —
  so it returned `""`, the failure was swallowed by a `logger.warning`, and the artifact
  recorded three *unmeasured* columns as `—` while looking complete. Run with
  `--judge-from-env`.

### Fixed 2026-10-03 — reranker

`ClusterCrossEncoderReranker.rerank` branched on `"index" in results[0]`, but the
cluster returns **`corpus_id`**. It fell through to a positional branch that mapped
*response position → input index*, so it returned `chunks[:top_k]` — the first N
candidates in retrieval order — while logging a success and a plausible score.
**HTTP 200, wrong output, no warning.** Reproduced against the live cluster
(correct chunk at input index 7 never returned); now returns it first.
Also: the exception path was `logger.warning` → now `logger.error` with an explicit
"RERANKER DISABLED … Precision@k/NDCG@k measured on unranked output".

**Implication:** any metric produced with the old code has an unranked top-k. The
report's Precision@20 / NDCG@20 and the "reranker top-20" lift need re-checking.

### Other findings

- `config.yaml` carries a **pre-existing uncommitted change** (`gpt-oss-20b` →
  `gpt-oss-120b`, mtime Aug 24). Working tree ≠ HEAD — a reproducibility problem.
- **pytest is not installed** in `.venv`, so the 141 tests can't run.
  `uv sync --extra dev` (uv is at `~/.local/bin/uv`).


### Definition of done

- `evaluate_rag.py` run and its artifact committed under `data/eval_results/`
- the dataset revision pinned in the same commit (page count + chunk count)
- a note of which of the four prerequisites were live, and which lanes were active

---

## Priority plan (agreed)

**P0 — make the numbers trustworthy**
1. Reproducible baseline + committed artifact  ← *current*
2. Kill silent fallbacks (classifier missing, dense_768 last-resort, ColBERT-skip)
   — each must log loudly and surface a flag in the eval output
3. Pin `scikit-learn~=1.9`; move the classifier artifact out of a gitignored pickle
   into a registry (or ONNX/`skops`) with a schema check at load
4. Config-invariant tests: embedder dim == `EMBEDDING_DIM`; `RERANKER_MODEL` == config;
   `CardType` is the single source for `DA_CARD_TYPES`
5. Fix doc drift (see verified facts below)
6. CI eval gate on `evaluate_rag.py` — fails the build on recall regression

**P1 — then improve metrics**
7. Calibrate the 7 `visual` queries (all currently `calibrated: false`, `relevant_pages: null`)
8. NDCG@20 = 0.382 is the precision ceiling — hard-negative mining / reranker work
9. Per-lane attribution in the eval report so we can see which lane moves which query type
10. Test the fallback chains (stub tests structurally cannot reach them)
11. `render_math()` golden-file test — ends the six-commit LaTeX patch cycle

**P2** abstention · guardrails · PPR · semantic caching · OKF cards
**P6 — kept, deferred to the very end** NiceGUI migration (`event-driven Vue.js` frontend,
per report §11). **Explicitly wanted — not dropped.** Do not remove it from the plan and do
not start it early: it waits until metrics (P0/P1), guardrails and abstention (P2) are done.
Frontend stays Streamlit until then.

---

## Environment topology (confirmed 2026-10-03)

- **The real index is on the cluster, not this laptop.** Mode B:
  `QDRANT_HOST=10.0.10.65`, `QDRANT_PORT=6333`. This laptop is Mode A
  (`./data/qdrant`, embedded) — a near-copy three points behind, not the reference.
- **Memgraph is local and reached by the VM through a reverse SSH tunnel**
  (`ssh -R 7687:localhost:7687 …`). `docker compose --profile phase3 up -d memgraph`
  locally; the `--profile phase3` flag is required or it silently does nothing.
- **ColBERT runs only against a server Qdrant.** `store.py:301` gates on `not is_local`,
  so it is skipped in laptop Mode A and active in Mode B. No migration is needed —
  the cluster already has everything.
- **Do not try to bind-mount embedded storage into the Qdrant container.** It panics on
  load (`invalid type: sequence, expected a map`) because `qdrant_client.local` is a
  Python emulation, not the Rust server. Point at the cluster instead.

### Index contents — cluster Qdrant `10.0.10.65:6333`

| Collection | Points | Vectors |
|---|---|---|
| `knowledge_base` | 5,135 | dense_64, dense_768, **colbert (multivec)**, **sparse** |
| `derivative_artifacts` | 81,837 | 768 single |
| `visual_knowledge_base` | 2,923 | colpali (multivec) |
| `concept_embeddings` | **11,229** | 768 single |

**Chunk count RESOLVED: 5,051 is correct** (report right, README's 5,047 wrong).
`knowledge_base` 5,135 = 5,051 chunks + 84 RAPTOR nodes. All 5,051 belong to one
document: `6d55c52b-47ae-45ff-bee0-a3ca01ac93ce`.

### ✅ RESOLVED 2026-10-03 — the local Memgraph was half stale

The graph had accumulated a full retired copy per re-ingest (each ingest mints a new
`document_id`; `run_phase3.py` never removes the previous one), plus a 70-chunk demo
doc with no vectors.

**Measured before → after:**

| | before | after |
|---|---|---|
| documents in graph | 3 | **1** |
| chunks | 10,169 | **5,051** |
| pages | 1,519 | **757** |
| concepts | 14,966 | **7,815** |
| **dangling chunk ids** | **5,118 (50.3%)** | **0 (0.0%)** |

Cleaned with `scripts/clean_stale_graph.py` — Qdrant is the source of truth; it
deletes the stale `Document` plus its `Chunk`/`Page` nodes, then the concepts orphaned
by that removal. Memgraph and the cluster Qdrant now agree **exactly** (5,051 / 5,051,
0% dangling in both directions).

**Why it mattered:** `graph_search` filters on `tenant_id IN [$tenant_id,'global']` and
**not** on `document_id`, so retired chunks were returned as graph hits and failed to
resolve; and `Concept` nodes merge *by name*, so stale `MENTIONS`/`RELATES_TO` edges
contaminated live traversal too. It hit the `multihop` lane (7 of 30 eval queries).

**Re-run `clean_stale_graph.py` after EVERY re-ingest.**

#### Two traps the script now guards against

1. **Point it at the index the graph was built from.** The laptop's Mode A
   `./data/qdrant` holds document `5fcc9006`, which appears in *no* graph — running
   against it makes every real document look stale and deletes the live one. Use
   `--qdrant-host 10.0.10.65`. The script **refuses (exit 2)** when the graph shares
   no document id with Qdrant, and `--dry-run` (the default) always reports first.
2. **Memgraph does not implement `(k)<-[:MENTIONS]-()`** ("Not yet implemented"), so
   orphan detection is two-phase and by concept name.

### Also

- The VM's `config.yaml` still points at `http://10.0.10.51:8000/v1` (4 places) —
  needs the same `.70` repoint or card-gen / RAPTOR / eval-judge calls fail there.
- `10.0.10.65` is a **shared** Qdrant hosting ~29 collections from other bootcamp
  projects. `knowledge_base` / `concept_embeddings` are generic names on a shared host.

---

## Verified facts — trust these over any doc

| Thing | Truth |
|---|---|
| Feynman Vol 1 PDF | **968 pages** (report says 940, README says 990) |
| Chunk count | README says 5,047, report says 5,051 — **unresolved, pin it in item 1** |
| Dense embedder | **Nomic 768d + 64d MRL** (`embedding_model` in `config.py`). `.env.example` still says Jina/1024d — **stale** |
| Reranker | `BAAI/bge-reranker-v2-m3` (`cfg.reranker_model`). `reranker.py`'s docstring says ms-marco — **stale** |
| Chunker | `chonkie.SentenceChunker` (class is named `SemanticChunker`) |
| RAPTOR clustering | `sklearn.mixture.GaussianMixture` + optional UMAP |
| Intent classifier | 768d, sklearn `LogisticRegression`; venv has sklearn **1.9.0**, pyproject floor is `>=1.5` (too loose) |
| Card types | **8** in `CardType` (docs say 7) |
| Eval queries | 30 total = 23 calibrated non-visual + 7 uncalibrated visual |

## Traps

- Flipping `SPLADE_ENABLED` adds a named vector → **full re-ingest required**
- `search_with_das(tenant_id="global")` is a fail-open default — pass the tenant explicitly
- Cards live in SQLite (`cards`) **and** Qdrant (`da_collection`); regenerating cards
  without re-running `scripts/index_derivative_artifacts.py` leaves retrieval stale
- `transformers` is pinned `<5.0` — the stated reason (Jina LoRA) is stale, so
  **check before bumping**, don't assume it's safe to remove
- `store.py` is a 1350-LOC hub — per `CLAUDE.md` §3, do not refactor it as a side effect

---

## Unrelated thing to be aware of

The `reliability-lab` plugin injects a "[Reliability lab — pipeline A]" banner into the
user turn whenever this profile is armed (`mode: "A"` in the plugin's state). It is a
**profile-wide** setting, not per-session, so it leaks into unrelated chats. Disarm with
`/lab off` in a chat. Not related to this project.
