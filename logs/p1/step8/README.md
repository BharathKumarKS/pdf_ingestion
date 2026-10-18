# P1 Step 7b — the query-side dense-lane switch (`IMPROVEMENTS.md` §E6)

Closes the gap Step 7 left open: the write path built a `dense_1024` collection but every query
site still embedded with the retired local Nomic 768d model. No re-ingest was needed for this —
it is a code change plus one retrain run against the cluster.

Plan: `.hermes/plans/2026-10-16-p1-reingest-plan.md` → "Step 7b".
Register: `IMPROVEMENTS.md` §E6 → "SWITCHED 2026-10-17"; new items §I12, §I13.

## What is in this directory

| File | What it is |
|---|---|
| `probe_query_lane.py` | The live probe (real cluster + real Qwen3 tokenizer). Run: `SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings USE_STUB_EMBEDDER=false uv run python logs/p1/step8/probe_query_lane.py` |
| `evidence.json` | Probe output **after** the classifier retrain |
| `evidence_pre_retrain.json` | Probe output **before** it — the state where the 768d classifier is rejected and the router falls back to 1024d prototypes |
| `suite.txt` | `uv run pytest tests/ -q -m "not slow"` → **4 failed, 361 passed, 6 skipped** |
| `README.md` | This file — the review record |

## Measured (live, cluster at `10.0.10.70:8123`)

| Claim | Measured |
|---|---|
| Query vector dimension | **1024** (`dense_dim`) |
| Query vector norm | **1.0** (client-side; the endpoint returns unnormalised vectors) |
| Query instruction applied | cosine(query-with-instruction, same text as a *passage*) = **0.8436** — near 1.0 would mean the instruction never reached the model |
| 64d MRL view matches the inline `store` slice | max delta **0.0** |
| Stale 768d classifier | **rejected** loudly → prototype fallback (1024d prototypes, `classify` → factual, score 0.996) |
| Retrained classifier | **loaded** (`n_features_in_ = 1024`), routes factual / overview / visual correctly |
| Dense vector name resolved from the collection | **`dense_1024`** (`colbert, dense_1024, dense_64`) |
| Retrain | 1,158 queries (250/250/250/408), **96.6 %** held-out accuracy, macro F1 0.96 |
| Suite | 361 pass / **4 pre-existing fail** / 6 skip |
| ruff (changed-file set) | **140 before, 140 after** — no new findings |

## The pre-existing 4 (do not "fix" here)

Confirmed by running the same two tests on a **clean `HEAD` worktree** (`git worktree add`), so
they are not regressions from this change:

1. `tests/test_splade.py` ×2 — hardcode a missing `tests/data/sample_physics.pdf`.
2. `test_phase1.py::TestStore::test_hybrid_search_includes_global` — 0 results.
3. `test_phase2.py::TestPhase1Regression::test_search_still_works_after_phase2` — 0 results.

**Trap found while establishing that baseline:** the first worktree run showed only 3 failures
because a worktree has **no `.env`** — `Settings` then falls back to defaults and
`splade_enabled=False`, which changes the collection schema *and* one of the tests' outcome.
Copy `.env` into the worktree or the baseline is not apples-to-apples.

## Two deliberate hold-backs (registered, not oversights)

- **The concept-graph lane** still embeds with the retired 768d model, because
  `concept_embeddings` is still 768d. The UI passes it a **separate** `graph_vec`
  (`streamlit_app.py`), and the admin Graph Search tab still uses `get_embedder`. Passing the
  dense lane's `q_vec` there would be a dimension error. → **§I12**, released by Step 9.
- **`reembed_chunks.py` / `validate_embedders.py`** still use the retired embedder.
  `reembed_chunks.py` is the documented recovery path when Qdrant is empty but SQLite has
  chunks — that path is now broken for the rebuilt index (loudly, on the dimension). → **§I13**.

## Finding fixed on the way: the endpoint returns UNNORMALISED vectors

Measured: pooled query norm ≈ 70.1, pooled passage ≈ 83.9, per-token ≈ 90–131. The **index**
side always normalised (`late_chunk_embedder._finish`); the query side did not, and neither did
`embed_documents` (which is what `raptor_tree._embed` uses for summary vectors). Invisible under
Qdrant's COSINE distance — it normalises internally, so **no retrieval number moved** — but any
dot-product consumer was off by ~6,000×, and the class docstring claimed "L2-normalised" the
whole time.

Fixed in `cluster_embedder.py`: the pooled paths normalise client-side (`l2_normalise`), per-token
stays raw (the mean is taken before normalising). Pinned by
`test_cluster_embedder.py::test_pooled_paths_normalise_an_unnormalised_endpoint` and
`::test_per_token_path_stays_raw`. Recorded as an `ARCHITECTURE.md` §8 trap (23).

## Consequence to remember at Step 10

One query path cannot address two different vector dimensions, so the deployed
`knowledge_base` (`dense_768`) is no longer *queryable by the app*. R1's old-vs-new comparison
therefore rests on the recorded artifacts (`logs/p0-9/v2_*.json`), not on re-querying the old
index. Rollback is still possible, but it is now a **two-part** switch (collection name *and*
query lane).

## Independent review (requesting-code-review Step 5)

Verifier: `openai/gpt-oss-20b` on the cluster — a different model from the author's
(`delegation.model = sv-gptoss`). Run **single-turn with the evidence embedded** (the endpoint
cannot sustain a multi-turn tool session; measured 2026-10-17). The diff was split into two
halves because the whole thing is ~29k characters:

- **A** — the lane core: `cluster_embedder.py`, `intent_router.py`, `store.py`, `config.py`,
  `embedder.py`
- **B** — the call sites: `main.py`, `streamlit_app.py`, and the `scripts/`

| Half | Verdict | What the transcript shows |
|---|---|---|
| A | `passed: true`, no findings | Read the 13.7k-char brief, then made **2 independent verification reads** (`search_files embedding_version`, re-read `cluster_embedder.py`) before answering. Engaged with the code. |
| B | `passed: true`, no findings | Read the 19.7k-char brief and answered — **no verification reads**. A read-and-agree pass; the weakest admissible signal. |

**Adjudication (not blind application).** Both lists are empty, so both verdicts are a pass — but
B's is a read-and-agree pass and A's ran in 15 s, so the pair is *weak* evidence, not strong. The
author's own spot-check of the risk each half carried, per the skill's "spot-check the source
yourself" rule:

- **B's real risk** is a call site that imports or names something that does not exist after the
  swap. Checked mechanically rather than by reading: `ruff --select F821,F811` over `src scripts
  tests` is **unchanged** at 2 pre-existing findings (neither in a file this change touched), and
  `py_compile` passes on all 13 changed source files. No undefined name was introduced.
- **A's real risk** is the dimension read from the wrong config field. It is pinned by a test that
  fails if the field is wrong (`test_intent_router_rejects_a_legacy_dim_classifier`) and by the
  live probe (query vector 1024d / norm 1.0 / `dense_1024` resolved).
- **A pass from either reviewer on a claim they could not check is not evidence for it.** No
  finding was rejected as speculation — there were no findings at all — so nothing here was
  overridden.

No fix-and-reverify cycle was needed (no findings). The `[verified]` commit prefix is **not** used:
the repo's convention is to record the verdict in this file and the commit body, and one of the
two reviewers did not verify anything.

**Trap for the next review:** reviewer B's first `read_file` call resolved the absolute path
against the wrong root (`C:\Users\...` — a Windows-style path echoed back) and returned
`File not found`; its retry with the bare filename succeeded. A reviewer that *had* stopped at the
error would have returned an unparseable verdict, which reads as a fail — worth knowing when the
next brief is dispatched by absolute path.

