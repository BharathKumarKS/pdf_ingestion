# HANDOFF.md — current work state

> **Living document.** This is *where we are right now*, not what the system is.
> For the durable system map read `ARCHITECTURE.md`. For setup read `README.md`.
> Keep this file short — it loads into every session in this directory.
>
> **Last updated: 2026-10-05** — P0 items 1–6 complete. If this date is old,
> re-check `git log --oneline -5` and `git status --short` before trusting
> "Current focus".

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

**P0 items 1–6 are DONE and validated (2026-10-05).** Next is **P1 item 7** —
calibrate the 7 `visual` queries.

| # | Item | Evidence |
|---|---|---|
| 1 | Reproducible baseline, committed | `6381f7b`; `data/eval_results/p0-*.md` |
| 2 | Silent fallbacks killed | judge + faithfulness + ColBERT + dense_768 + classifier now log loudly and surface in the artifact ("Run integrity") |
| 3 | sklearn pinned, classifier checked | `scikit-learn~=1.9`; type + `n_features_in_` schema check at load; pickle tracked in git |
| 4 | Config-invariant tests | `tests/test_config_invariants.py` (6) |
| 5 | Doc drift fixed | `reranker.py`, `.env.example`, `CLAUDE.md`, `README.md`, `ARCHITECTURE.md` |
| 6 | Eval gate + CI | `scripts/eval_gate.py`, `.github/workflows/ci.yml` |

Test suite: **153 pass / 5 fail** (`uv run pytest tests/ -q -m "not slow"`). The 5 are
**pre-existing** — confirmed by stashing the P0 edits and re-running the same tests on
clean source. They are NOT P0 regressions:

- `tests/test_splade.py` (×2) hardcode `tests/data/sample_physics.pdf`, which does not
  exist — the `sample_pdf` fixture generates it into a tmp dir instead.
- 3 search tests return 0 results: `test_phase1::test_hybrid_search_includes_global`,
  `test_phase2::test_search_still_works_after_phase2`,
  `test_integration_real::test_semantic_search_returns_relevant_results`.

### The finding item 2 fixed

`compute_faithfulness` returned **`1.0` — a perfect score — whenever claim extraction
failed or produced no claims**, i.e. whenever the LLM was down. `make_judge_fn` returned
`""` on failure with only a `logger.warning`, and always sent an `Authorization` header
even when the key was empty (which the gateway rejects with HTTP 500). So a dead judge
did not merely go unmeasured — it **scored perfect**. Every historical Faithfulness
number is untrustworthy. Now: failures are counted, logged at ERROR, and the artifact
carries a **Run integrity** section (synthesis ok/failed, judge calls/failures).

### Baselines — committed

### Baseline — committed

`data/eval_results/p0-baseline-oldK_2026-10-05_0635.md` (in `6381f7b`). 23/23 calibrated
queries, cluster index, SPLADE + reranker on, elapsed 56.7s:

| Scope | Recall@20 | MRR | P@6 | NDCG@6 |
|---|---|---|---|---|
| Overall | **0.636** | 0.365 | 0.174 | 0.377 |
| factual | 0.775 | 0.506 | 0.217 | 0.594 |
| overview | 0.580 | 0.218 | 0.139 | 0.237 |
| multihop | 0.486 | 0.290 | 0.143 | 0.187 |

⚠️ **The judge lane is still unmeasured in this baseline.** `Judge: none` — Faithfulness,
Answer Relevance and Citation Accuracy are all `—`. Run with `--judge-from-env` or the
artifact looks complete while three columns are unmeasured (the trap at "Fixed 2026-10-04").

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
3. **Intent classifier** — ✅ present (768d), **tracked in git**, pinned `scikit-learn~=1.9`,
   schema-checked at load (type + `n_features_in_`). P0 item 3 done.
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

- ✅ `config.yaml`'s Aug-24 `gpt-oss-20b` → `gpt-oss-120b` working-tree edit was the
  regression that killed every LLM stage; reverted and committed in `6381f7b`.
- ✅ **pytest** — install with `uv sync --extra dev` (uv at `~/.local/bin/uv`). Suite is
  151 pass / 5 pre-existing failures (listed above).
- **7 visual queries are still uncalibrated** — `colpali-001` … `colpali-007` all carry
  `"calibrated": false` and `"relevant_pages": null` in `data/eval_queries.json`. They are
  excluded from the 23/23 baseline. P1 item 7; `calibration_output.txt` is the working pass.
- **`CardType` (8 members) is now the single source for the DA card-type list.** The index
  script used to hardcode 5 types, so example / misconception / objective cards were
  generated in Phase 2 but **never indexed** into `derivative_artifacts`. Fixed;
  `tests/test_config_invariants.py` enforces it.
- **The graph lane had no connection timeout.** `graph_builder._get_driver()` built
  its own neo4j driver, ignoring `database.get_memgraph()`, which sets
  `connection_timeout=3` for exactly this reason. On the cluster — where
  `concept_embeddings` is populated, so `graph_search` actually reaches the Bolt
  query — a down Memgraph would block every multihop query on the neo4j default
  (~30s). It now delegates to `get_memgraph`; measured **3.00s** to fail against a
  black-hole IP. Pinned by `tests/test_graph_lane.py`.

### Definition of done

**Item 1 — ACHIEVED 2026-10-05.** Artifact committed under `data/eval_results/`
(`p0-baseline-oldK_2026-10-05_0635.md`, commit `6381f7b`), prerequisites recorded
(24/24 preflight), lanes stated in the artifact Config block. Outstanding: the **judge
lane was not run** — re-run with `--judge-from-env` to fill Faithfulness / Ans.Relevance
/ Citation, then re-commit the artifact.

**Item 2 — MET 2026-10-05.** Every silent fallback logs loudly and surfaces in the eval
artifact's "Run integrity" section; `tests/test_eval_integrity.py` pins the behaviour;
`pytest` is installed and the new tests pass.


---

## Priority plan (agreed)

**P0 — make the numbers trustworthy**
1. ~~Reproducible baseline + committed artifact~~ ✅ **done 2026-10-05** (`6381f7b`)
2. ~~Kill silent fallbacks~~ ✅ **done** — each logs loudly and surfaces in "Run integrity"
3. ~~Pin `scikit-learn~=1.9`; classifier schema check~~ ✅ **done**
4. ~~Config-invariant tests~~ ✅ **done** (`tests/test_config_invariants.py`)
5. ~~Fix doc drift~~ ✅ **done**
6. ~~CI eval gate on `evaluate_rag.py`~~ ✅ **done** (`scripts/eval_gate.py` + CI workflow)


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
| Chunk count | **5,051** — RESOLVED 2026-10-03: report right, README's 5,047 wrong (see topology) |
| Dense embedder | **Nomic 768d + 64d MRL** (`embedding_model` in `config.py`). `.env.example` fixed 2026-10-05 (was Jina/1024d) |
| Reranker | `BAAI/bge-reranker-v2-m3` (`cfg.reranker_model`). `reranker.py` docstring fixed 2026-10-05 (was ms-marco) |
| Chunker | `chonkie.SentenceChunker` (class is named `SemanticChunker`) |
| RAPTOR clustering | `sklearn.mixture.GaussianMixture` + optional UMAP |
| Intent classifier | 768d `LogisticRegression`; pinned `scikit-learn~=1.9`, schema-checked at load |
| Card types | **8** in `CardType` — now the single source for `DA_CARD_TYPES` |
| Eval queries | 30 total = 23 calibrated non-visual + 7 uncalibrated visual |

## Traps

- Flipping `SPLADE_ENABLED` adds a named vector → **full re-ingest required**
- `search_with_das(tenant_id="global")` is a fail-open default — pass the tenant explicitly
- Cards live in SQLite (`cards`) **and** Qdrant (`da_collection`); regenerating cards
  without re-running `scripts/index_derivative_artifacts.py` leaves retrieval stale
- `transformers` is pinned `<5.0` — the stated reason (Jina LoRA) is stale, so
  **check before bumping**, don't assume it's safe to remove
- `store.py` is a 1350-LOC hub — per `CLAUDE.md` §3, do not refactor it as a side effect
- A wider retrieval funnel is **not** a better system — `scripts/eval_gate.py` refuses
  to diff artifacts measured at different K (the report once did exactly this)

---

## Unrelated thing to be aware of

The `reliability-lab` plugin injects a "[Reliability lab — pipeline A]" banner into the
user turn whenever this profile is armed (`mode: "A"` in the plugin's state). It is a
**profile-wide** setting, not per-session, so it leaks into unrelated chats. Disarm with
`/lab off` in a chat. Not related to this project.
