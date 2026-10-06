# HANDOFF.md — current work state

> **Living document.** This is *where we are right now*, not what the system is.
> For the durable system map read `ARCHITECTURE.md`. For setup read `README.md`.
> Keep this file short — it loads into every session in this directory.
>
> **Last updated: 2026-10-05** — P0 items 1–8 complete and committed.
> **`main` is in sync with `origin/main`** (rebased + pushed at `dce5efd`). The earlier
> "6 ahead / 1 behind — expect conflicts" warning was **wrong**: the two sides touched
> disjoint files (the remote commit `6f56634` changes only `streamlit_app.py`, which no
> local commit touches) and the rebase was clean.
> If this date is old, re-check `git log --oneline -5` and
> `git status --short` before trusting "Current focus".

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

**P0 items 1–8 are DONE and validated (2026-10-05).** Next is **P0 item 9** — rebuild the
gold set (~120–150 queries); it gates all of P1. See the priority plan below.

| # | Item | Evidence |
|---|---|---|
| 1 | Reproducible baseline, committed | `6381f7b`; `data/eval_results/p0-*.md` |
| 2 | Silent fallbacks killed | judge + faithfulness + ColBERT + dense_768 + classifier now log loudly and surface in the artifact ("Run integrity") |
| 3 | sklearn pinned, classifier checked | `scikit-learn~=1.9`; type + `n_features_in_` schema check at load; pickle tracked in git |
| 4 | Config-invariant tests | `tests/test_config_invariants.py` (6) |
| 5 | Doc drift fixed | `reranker.py`, `.env.example`, `CLAUDE.md`, `README.md`, `ARCHITECTURE.md` |
| 6 | Eval gate + CI | `scripts/eval_gate.py`, `.github/workflows/ci.yml` |
| 7 | Metric set fixed | `1dad73f` — `Precision@k` → `Recall@k` + `Hit@k` |
| 8 | Judge lane measured | `p0-judge-canonical_*.md`; `JUDGE_MODEL` path fixed (`dce5efd`) |

Test suite: **164 pass / 5 fail** (`uv run pytest tests/ -q -m "not slow"`). The 5 are
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

### P0-8 — the judge lane, measured (2026-10-05)

First generation metrics this repo has ever produced. Judge = `Qwen/Qwen3-VL-8B-Instruct`
(cross-family: the generator is `openai/gpt-oss-20b`), cluster index, SPLADE + reranker on,
**1040 judge calls, 0 failures**, 23/23 calibrated queries. Artifact
`data/eval_results/p0-judge-canonical_2026-10-06_0010.md`.

| Scope | Recall@100 | Recall@20 | Hit@20 | MRR | NDCG@20 | Faithfulness | Ans.Relevance | Citation Acc. |
|---|---|---|---|---|---|---|---|---|
| Overall | 0.795 | 0.636 | 1.000 | 0.361 | 0.432 | **0.701** | **0.927** | **1.000** |
| factual | 0.900 | 0.775 | 1.000 | 0.504 | 0.573 | 0.752 | 0.867 | 1.000 |
| overview | 0.771 | 0.560 | 1.000 | 0.192 | 0.366 | 0.645 | 1.000 | 1.000 |
| multihop | 0.665 | 0.502 | 1.000 | 0.302 | 0.288 | 0.676 | 0.952 | 1.000 |

⚠️ **Faithfulness is indicative and biased LOW — treat 0.70 as a floor.** Hand-scored 10
answers against the exact passages the judge saw (instrumented run, 406 judge calls, 0
failures). Agreement 6/10 within ±0.02 (4/10 numerically identical: vec-008, vec-010,
raptor-004, graph-005); every miss is one-directional — judge mean ≈0.65 vs hand ≈0.73,
i.e. ~0.08 low. Full working: `data/eval_results/p0-judge-handscore_2026-10-05.md`.
Three systematic misses:

- **LaTeX vs mangled plaintext.** Claim `F = -G m₁m₂/r³ · r` → NO against p243, which
  states `F = -Gm 1 m 2 r /r 3`. Claim `K = ½mv²` → NO against p228's `1 2 mv 2`.
- **Near-verbatim paraphrase.** raptor-002's "energy appears in electrical, mechanical,
  radiant, heat forms" → NO against p209, which lists exactly those forms.
- **Meta/citation claims.** Claim extraction emits "This value appears on page 965"; no
  passage can *state* that, so it is always NO. An ill-formed claim, not a retrieval miss,
  and it drags the metric down.

Ans.Relevance (0.927) and Citation Acc. (1.000) look well-calibrated — citation is 1.000
because answers cite only retrieved pages, so it is a weak signal as currently defined.

Two harness residuals (not pipeline bugs):

1. **Claim extraction JSON is intermittently unparseable** — one run lost 2/23 queries
   (vec-003, graph-003) to `Invalid \escape` (LaTeX backslashes) and scored `None`; the
   canonical run lost 0. So ~0–9% of the measurement, run-dependent. That is P0-2 working
   as designed (logged, not silently 1.0). A tolerant parse (or JSON-safe escaping in the
   prompt) would remove the variance.
2. **`--judge-from-env` was doubly broken; fixed in `dce5efd`.** It set the judge model to
   the *generator* (self-preference bias), and posted to `/chat/completions` — the gateway
   serves only `/v1/chat/completions` (bare path → 404). Now `JUDGE_MODEL` overrides the
   generator model and the `/v1` suffix is normalised like `llm.py`.

### Frontend verified + metrics extended (2026-10-05)

Streamlit app driven end-to-end against the cluster. **Run it on a free port — 8501 and
8502 belong to other projects** (`genies-kitchen`, `strange-lamp`); verifying against them
would QA the wrong application. Ask a Question works: retrieval → HyDE → intent router →
SPLADE+ColBERT → rerank → synthesis → answer + cited sources + expandable passages.

Three real defects found; two fixed:

1. **Phoenix tracing is enabled but its endpoint is down.** `.env` sets
   `PHOENIX_ENABLED=true` / `PHOENIX_ENDPOINT=http://localhost:6007` and nothing listens
   there, so every request retries span export (0.87s → 2.12s → 3.84s → "Failed to export
   span batch") — ~21 retry blocks per query, turning a ~10s retrieval into ~70s. Launch
   with `PHOENIX_ENABLED=false` (env var; no `.env` edit needed) or start Phoenix.
2. **The answer's LaTeX was not rendered** — `st.markdown(synthesis)` bypassed the math
   converter the cards use, and the generator emits `\[...\]` / `\(...\)`, which Markdown
   escapes to a literal `[ ... ]`. Fixed: `_latex_delims_to_dollars()`, plus a `$$...$$`
   fix in `_convert_braces_to_math` Pass 2 (it treated a display block's `$$` as an empty
   inline span, then brace-converted the maths inside it). Verified rendered in the app.
3. **Formulas are missing from the indexed passages** — they read
   `<!-- formula-not-decoded -->` where the formula should be. This is *why* formula claims
   score low on faithfulness: the judge is asked whether a passage supports
   `F = -Gm₁m₂/r³` and the passage contains no formula at all. A data-quality issue, not a
   judge error — it also depresses `ctx_prec_judged`.

**New metrics** (`scripts/evaluate_rag.py`): `ctx_precision` (page-level, chunk units —
diagnostic only, measured 0.05–0.10) and `ctx_prec_judged` (RAGAS-style, rank-weighted,
behind `--judged-context-precision`; needs no gold labels, so it can cover visual queries
too). Claim extraction now survives LaTeX backslashes (`_parse_claims`) rather than losing
the whole query.

**Abstention / guardrail precision: deferred to P2 as agreed** — the features do not exist
and the eval set has no negatives, so the metric is unmeasurable. Negative-query generation
is folded into P0-9.

### Visual search fixed (2026-10-05)

Visual search was **unusable in the UI** and, when reachable, **returned wrong pages**.
Three independent defects:

1. **Readiness was read from the wrong store.** The panel gated the uploader on
   `Document.colpali_status == "ready"` in **SQLite**, but the vectors live in Qdrant —
   and this machine's SQLite tracks a *different* ingest than the cluster index. Live
   state: SQLite held doc `5fcc9006` marked `processing` with 0 page images, while the
   cluster held 2,923 visual vectors for `6d55c52b`/`abc7c100`. So the UI told the user
   to re-run Phase 3 against a fully-populated index. Now `store.count_visual_vectors()`
   asks Qdrant, and `store.visual_index_documents()` exposes which docs back the index.
2. **The score threshold was three orders of magnitude off.** `visual_score_threshold`
   was `0.15`, but ColPali MaxSim is **not** a 0-1 similarity: it sums the best match per
   query patch over a fixed 1031-patch grid, so scores run to ~1031. Every result passed
   — which is exactly why an out-of-domain image returned textbook pages. **Measured**
   (in-domain page vs synthetic out-of-domain): in-domain 966–1031, out-of-domain
   444–479, stable across image size (ColPali resizes to a fixed grid). Now `600`.
3. **1,890 stale duplicate vectors.** A re-ingest minted `abc7c100` and nothing removed
   the old run, so every page existed twice and **every visual result came back
   duplicated**. Removed with the new `scripts/clean_stale_visual.py` (dry-run default,
   refuses when the visual index shares no document id with `knowledge_base` — the
   `clean_stale_graph.py` guard pattern). Collection: 2,923 → **1,033**.

Verified after the fix, through `store.visual_search` with the configured threshold:
in-domain page → matches its own page (1031) and neighbours; noise / blank / gradient →
**0 results**. Re-run `clean_stale_visual.py` after every Phase 3 re-ingest.

### Phoenix observability enabled (2026-10-05)

Tracing is now live and **verified persisting** (not just "endpoint answers"). Start the
server — it must NOT use the default ports on this machine:

```bash
PHOENIX_PORT=6007 PHOENIX_GRPC_PORT=4319 phoenix serve     # UI at http://localhost:6007
```

Two port collisions to know: **6006 is busy** (which is why `.env` uses 6007) and
**4317 is held by Docker Desktop**, so Phoenix's default gRPC port fails to bind and the
whole server exits with `Failed to bind to address [::]:4317`.

**The blocker was a corrupted database, not config.** `~/.phoenix/phoenix.db` had grown to
2.7 GB and was malformed (`Tree 10 page 505326 cell 0: invalid page number 670390`). Phoenix
accepted `POST /v1/traces` with **HTTP 200** and then failed to insert — so the app showed
no error, the sidebar said nothing useful, and only Aug-22/24 spans were ever visible. Moved
aside to `~/.phoenix/phoenix.db.corrupt-20261005`; a fresh DB fixed it.

Verified end-to-end: a UI query produced the full retrieval trace — `query`,
`retrieval.embed`, `intent_route`, `retrieval.vector_search`, `retrieval.rerank`,
`retrieval.mmr`, `retrieval.da_lane` — with 0 insert errors. The sidebar now reads
"🔭 Phoenix traces — active".

⚠️ **Gap: LLM calls are NOT traced.** `telemetry.py` claims "Auto-instrumentation covers all
OpenAI-compatible LLM calls", but `src/core/llm.py` posts with raw `httpx` and the `openai`
SDK is imported **nowhere** in `src/` — so `OpenAIInstrumentor()` patches a library that is
never used. Retrieval stages are traced; synthesis, card generation and RAPTOR are invisible,
including their latency and token counts. Fix = either call through the `openai` SDK or emit
manual spans around `call_llm`.

### Prerequisite status (re-checked 2026-10-04 — `scripts/preflight.py`, 24/24 pass)

Point the eval at the **cluster** index: `QDRANT_HOST=10.0.10.65`. No `.env` edit is
needed — `config.py` uses pydantic-settings `env_file`, and environment variables take
precedence over the file.

1. **Qdrant** — ✅ cluster index `10.0.10.65` is the reference; the graph pairs with it,
   not with the laptop's file store. `knowledge_base` 5,135 pts
   (dense_64/dense_768/colbert/sparse), `derivative_artifacts` 81,837,
   `visual_knowledge_base` 1,033 (was 2,923 — see the visual-search fix below),
   `concept_embeddings` 11,229.
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
  164 pass / 5 pre-existing failures (listed above).
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
1–6 ✅ **done 2026-10-05** (`6381f7b`, `c3a8727`) — baseline committed; silent fallbacks
   killed; sklearn pinned + classifier schema-checked; config-invariant tests; doc drift
   fixed; eval gate + CI.
7. ✅ **done 2026-10-05** (`1dad73f`) — **metric set fixed.** `Precision@top_k` divided by a
   fixed `top_k`, capping it at `min(|relevant|, top_k)/top_k` — ~0.10 for a median 2-page
   gold set; it read as failure while sitting at its own ceiling. Now `Recall@top_k` +
   `Hit@top_k`; summary columns are `Recall@100 | Recall@20 | Hit@20 | MRR | NDCG@20`, and
   `Recall@fetch_k − Recall@top_k` quantifies what ranking discards.
8. ✅ **done 2026-10-05** (`dce5efd` + `p0-judge-canonical_2026-10-06_0010.md`) — **judge
   lane measured.** Faithfulness 0.701 / Ans.Relevance 0.927 / Citation 1.000, 1040 judge
   calls, 0 failures.
   Judge is `Qwen/Qwen3-VL-8B-Instruct`; the numbers are **indicative** — hand-scoring 10
   answers showed a systematic ~0.08 low bias on formula/paraphrase claims (see P0-8 above).
   Judge choice is settled: `DeepSeek-R1-Distill-Qwen-7B` ignores YES/NO instructions and
   collapses faithfulness to ~0; `gpt-oss-120b` is still HTTP 502; `gpt-oss-20b` is the
   generator (self-preference). **Do not re-litigate.**
9. **Rebuild the gold set** — the big one, and it gates all of P1. Target **~120–150
   queries** (23 can only detect ≥0.15 effects at 80% power; 0.05 needs ~200). Per-type
   generation: factual from a known page; overview from a topic + book-wide scan;
   multihop from the Memgraph concept graph. Graded relevance; human-verify a 20–30% sample.
   **Must also include unanswerable / out-of-scope negatives (~15–20%)** — abstention
   precision (P2) is unmeasurable without them: there is currently nothing to score a
   refusal against.

**P1 — then improve metrics** (all of it gated on P0-9)
10. Ranking — overview MRR 0.191 is the one genuinely bad number. Cheapest first: config
    (MMR λ / RRF), then the cross-encoder (zero-shot `bge-reranker-v2-m3` today), then
    hard-negative fine-tuning (stage 3 of the retriever→reranker recipe).
11. Calibrate the 7 `visual` queries — folds into P0-9 (they are 23% of the eval)
12. Per-lane attribution in the eval report so we can see which lane moves which query type
13. Test the fallback chains (stub tests structurally cannot reach them)
14. `render_math()` golden-file test — ends the six-commit LaTeX patch cycle
    (partly done: `tests/test_frontend_math.py` pins both converter bugs)
15. ⏳ **Graph lane — ranking DONE, traversal still missing.** `graph_search` now orders by
    distinct concepts matched, then by concept similarity (the scores were previously
    thrown away), and the tab caption no longer claims multi-hop. Measured: ranking now
    discriminates (`'Law of Conservation of Energy'` 1.519 ranks above `'laws of physics'`).
    **Still missing:** real 1–2 hop `RELATES_TO` traversal — `hop_distance` remains the
    constant 0. **Root cause of the poor relevance:** the concept vocabulary holds
    near-duplicates as *separate nodes* ('orbit' / 'Orbit' / 'planetary orbit' /
    'Planetary Orbit', "Earth's orbit" / "Earth's orbital motion"), so nearly every chunk
    ties at 1 distinct concept. Deduplicating concept names is the bigger lever than ranking.
16. **Admin Status should report the STORES, not SQLite.** Three separate bugs today came
    from local SQLite describing a different ingest than the index (visual readiness, the
    sidebar badge, and the graph). A status panel driven by store counts would have caught
    all three.
17. **Phoenix does not trace LLM calls** — `llm.py` uses httpx, so `OpenAIInstrumentor()`
    never fires. Synthesis/card-gen/RAPTOR latency and tokens are invisible.
18. **Upload tab's "Topic" and "Difficulty" are inert** — persisted to the Document row and
    chunk payload, but nothing filters or steers on them. Wire or remove.

**P2** abstention · guardrails · PPR · semantic caching · OKF cards

**✅ Store divergence resolved (2026-10-06) — `scripts/align_stores.py`**
The app retrieves from Qdrant but renders cards from SQLite, and the two were ingested
separately: KB doc `6d55c52b` (5,135 points) vs SQLite doc `5fcc9006` (5,048 chunks) with
**zero ID overlap**. Every retrieval→SQLite join therefore failed, which is why "Key Facts"
and question-scoped "Study Cards" were *always* empty — not a matching problem, an ID one.

Fixed by renaming SQLite's IDs to the cluster's (cluster = source of truth, settled), matched
by chunk text: 4,962 exact + 82 by `chunk_index` = **99.9%**; 4 chunks keep their old ids
(their twins carry identical text). Verified: cards joining to chunks **95,213/95,213** (was
0/95,213), and the Study Cards tab returns 6 on-topic formula cards for "newtons laws of
motion". Backup at `data/synapse.db.bak-*`. Re-running is a no-op: it resolves the same
5,044 chunks to the same ids, so a second pass rewrites identical values (verified).

**Still stale, but separate:** `derivative_artifacts` was built by the OLD 5-type card list,
so it lacks objective/misconception/example (10,927 cards). Re-index from SQLite with
`scripts/index_derivative_artifacts.py --clear` when the DA lane matters.

`scripts/clean_cards.py` can now be applied — its cross-store id guard passes.

**Curation, not duplication:** 95,213 cards for a 968-page book (~19/page). Only 294 rows
(0.3%) are junk-or-duplicate; a further 9,829 (10.3%) were source-referencing and are now
filtered at generation. Mass deletion is not the lever — question-scoped cards are.

**Deferred (agreed — do not lose these)**
- **Key Facts panel** — keep it, but *measure* whether it helps before removing or expanding.
- **Feedback capture** (thumbs / "was this helpful?") — the only real-user signal available;
  the gold set is 23 queries and a judge, with no student input at all. Deferred.
- **Question history** — each question currently replaces the page; students iterate on a
  topic and have to re-ask. Deferred.
- **Topic / Difficulty** — removed as inert (they were persisted but never read). Revisit as
  a real feature: scoped card generation at a chosen level.
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
| `visual_knowledge_base` | 1,033 | colpali (multivec) |
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
- `--judge-from-env` judges with the **generator** unless `JUDGE_MODEL` is set. A model
  scoring its own output is not a measurement. The gateway also serves only
  `/v1/chat/completions` — a bare `/chat/completions` is 404.
- Retrieval is **not bit-reproducible**: HyDE generates a hypothetical at temperature 0.3,
  so two runs of identical config differ (Recall@20 0.636 → 0.628 across the two
  2026-10-05 runs). Compare artifacts with `eval_gate.py`'s tolerance, never single numbers.
- Faithfulness is a **floor**, not a point estimate: the judge under-scores formula and
  paraphrase claims (see P0-8). A faithfulness drop of <0.05 between runs is judge noise.
- **Phoenix is enabled by default with no collector running** — it silently adds ~60s of
  retry latency per query. `PHOENIX_ENABLED=false` for any latency-sensitive run.
- Passages contain `<!-- formula-not-decoded -->` where Docling failed to decode a formula.
  Formula-bearing claims then cannot be entailed by any passage — it caps faithfulness and
  `ctx_prec_judged` regardless of retrieval quality.
- **Ports 8501/8502 are other projects** on this machine. Pick a free port for this app.
- **ColPali MaxSim is not 0-1.** Scores run to ~1031 (fixed 1031-patch grid). Any
  threshold copied from a cosine-similarity habit (0.15) filters nothing. In-domain
  966-1031, out-of-domain 444-479 on this corpus.
- A per-document `colpali_status`/`source` flag in SQLite is **not** evidence the vector
  store is populated — the two can describe different ingests. Ask the store.
- **Re-run `scripts/clean_stale_visual.py` after every Phase 3 re-ingest**, or every page
  returns twice (same class as `clean_stale_graph.py`).
- **Phoenix needs `PHOENIX_GRPC_PORT`** — Docker holds 4317, and the server exits entirely
  if gRPC can't bind. 6006 is also taken; `.env` uses 6007.
- **A 200 from Phoenix does not mean the span persisted.** A malformed `~/.phoenix/phoenix.db`
  accepts `POST /v1/traces` and drops the span. Verify by reading spans back.
- **LLM calls are invisible to Phoenix** — `llm.py` uses httpx, not the `openai` SDK, so the
  OpenAI instrumentor never fires.

---

## Unrelated thing to be aware of

The `reliability-lab` plugin injects a "[Reliability lab — pipeline A]" banner into the
user turn whenever this profile is armed (`mode: "A"` in the plugin's state). It is a
**profile-wide** setting, not per-session, so it leaks into unrelated chats. Disarm with
`/lab off` in a chat. Not related to this project.
