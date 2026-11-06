# HANDOFF.md — current work state

> **Living document — where we are *now*, not what the system is.** The durable map is
> `ARCHITECTURE.md` (read **§8 Invariants and traps** before your first change); the backlog is
> `IMPROVEMENTS.md`; the **decision log is `DECISIONS.md`** — every fork taken, the options, **why** it
> was chosen and **why not** the others, with the backing number (for defence and later recall).
> Keep this file short — it loads into every session.
>
> **Last updated: 2026-11-05, session 38 — see the SESSION 38 block below. One line: ▶ C1 (the response-side assertion–evidence grounding graph) and C4 (ALCE citation faithfulness) are BUILT + VERIFIED (tests + stdlib verifier + mutation + cross-family reviewer); the lab's NLI model is MEASURED to not separate unrelated from entailing text (§I121); the three session-37 steps that were MISSING a reviewer (P0/R8/C2) are now retro-verified; and a DETERMINISTIC completeness gate (`scripts/verify_plan_coverage.py` + a test) now makes a missing reviewer impossible to miss. Nothing committed. ⚠️ the cluster's sparse + rerank are STILL DOWN.**
>
> ## ▶ SESSION 38 — ▶ START HERE (2026-11-05). **C1/C4 SHIPPED AND VERIFIED; THE VERIFICATION GAP IS NOW MECHANICAL.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 38, then `.hermes/plans/2026-11-05-p1-guardrails-course-aligned-SESSIONS.md` — its **status table is the resume point**, and its **§9.5 is the new completeness gate you must keep green**. Continue the cheap-first core: **R10** (the funnel + tournament table — needs `data/guardrail_eval.jsonl`, not yet built), then **R4/R6/R9**. ⚠️ **Before any response-side gate is trusted, read §I121**: the lab's NLI model (`cross-encoder/nli-deberta-v3-base`) calls an UNRELATED passage entailment at **0.9948**, above a supporting passage's **0.9924** — so C1/C4's grounding floor cannot separate near-domain negatives as §I114 planned. ⚠️ Every step: acceptance + independent reviewer + stdlib verifier + mutation proof, then `python scripts/verify_plan_coverage.py` (0 gaps). Nothing is committed."*
>
> **1. ✅ C1 — THE ASSERTION–EVIDENCE BIPARTITE GRAPH IS BUILT (§I121).** `src/core/guardrails/response.py` now carries the lab's five response-grounding modules ported from `Labs/Week_6/response_grounding/src/response_grounding/*.py`: `ClaimExtractor` (+ the lab's sentence-split fallback, and its COSTAR prompt copied to `src/core/guardrails/prompts/claim_extractor_system_prompt.md`), `ClaimDocumentMatrixBuilder`, `SemanticSimilarityFilter` (MiniLM cosine, τ 0.5), `NLIEntailmentChecker` (DeBERTa cross-encoder, entailment = the softmax prob of the model's entailment head, τ 0.55) and `GroundednessEvaluator` (grounded iff ≥1 retained edge entails; an **isolated left node** is the hallucination signature). Deviations from the lab: **only** `call_llm` replaces `instructor`+`OpenAI`, and the encoder/checker are **injectable** so `USE_STUB_NLI` stands in offline. New config: `use_stub_nli`, `guard_similarity_model`, `guard_nli_model`, `guard_similarity_threshold`, `guard_nli_threshold`, `guard_max_claims`, `guard_max_evidence`.
>
> **2. ✅ C4 — ALCE CITATION FAITHFULNESS.** `compute_citation_faithfulness` reads the same NLI graph at the citation level: **citation recall** = the fraction of ALL statements with ≥1 entailing citation; **citation precision** = the fraction of ALL citations that entail; **both None when the answer cites nothing** (the §I115 lesson). Citations are stripped from the statement before the NLI read.
>
> **3. ⚠️ §I121's FINDING — the MODEL, not the port.** `logs/p1/step10/c1_live_probe.py` → `.json`, three passages against one claim: supporting **0.9924** entailment, **unrelated ("The cat sat on the mat…") 0.9948**, contradicting 0.1058. **The unrelated passage OUTSCORES the supporting one** (separation gap **−0.002359**): no τ separates them. The real head order is `{0: contradiction, 1: entailment, 2: neutral}` (verified live; the stub now mirrors it). ⇒ **§I114's plan to hand the 22 near-domain negatives to this grounding floor is undercut** — the floor's entailment read calls an unrelated passage entailment. Needs its own measured decision (a stronger NLI model, or a two-stage read).
>
> **4. ✅ THE VERIFICATION GAP IS NOW MECHANICAL — this is the session's process fix.** An audit against the files (not the plan's prose) found the session-37 table marked **P0, R8 and C2 ✅ with no independent reviewer** — a *consistent* omission, i.e. a forgotten ritual, not a judgment call. Two things were done: **(a)** the three steps were **retro-verified** — `p0_config_guard_verifier.py` **14/14**, the R7R8 mutation **7/7**, the C2 mutation **4/4**, and an independent cross-family reviewer (`openai/gpt-oss-20b` on the cluster router, vs the author's deepseek) **13/13 CONFIRMED** over P0+R8+C2 (`logs/p1/step10/guardrails_p0_r8_c2_review.json`). **(b)** A **deterministic completeness gate** — `scripts/verify_plan_coverage.py` + `tests/test_plan_verification_coverage.py` — now asserts that every `✅ DONE` row in the plan's §8 has a non-empty verifier, a non-empty mutation proof, a **resolvable** reviewer (a `deleg_*` id or an existing `…review…` artifact) and only existing backticked paths. **It is a test**, so it cannot be forgotten; being deterministic, it needs no verifier of its own. Demonstrated: run against the pre-fix table it names **exactly P0, R8, C2**.
>
> **5. ✅ VERIFICATION, ALL FOUR PARTS, FOR C1/C4.** Acceptance `tests/test_guardrails_response_c1.py` 23/23 + `tests/test_guardrails_citation_c4.py` 10/10; live probe asserted checks A1/A2/A4/A5/A6 pass; stdlib verifier `logs/p1/step10/guardrails_c1c4_verifier.py` **14/14** (PART 1 re-derives every probe flag from the raw probabilities; PART 2 re-derives ALCE with its own splitter/regex/arithmetic over a hand-set oracle); mutation `guardrails_c1c4_mutation.py` **13/13 reddened, no inert** (⚠️ **M9 was INERT on the first run** — the object-form test was rescued by the bracket-slice fallback; a stronger fixture was added and M9 now reddens — recorded, not hidden); independent cross-family reviewer **9/9 CONFIRMED** (`logs/p1/step10/guardrails_c1c4_review.json`).
>
> **6. ⚠️ SUITE.** `4 failed / 868 passed / 9 skipped` (scrubbed env, `-m "not slow"`) — the 4 are the **documented pre-existing** `tests/data/sample_physics.pdf` failures (`test_phase1::test_hybrid_search_includes_global`, `test_phase2::test_search_still_works_after_phase2`, `test_splade` ×2), **0 new**. (770 session-37 baseline + 61 session-37 guardrail tests + 33 C1/C4 + 4 gate tests = 868.)
>
> **7. ⚠️ WORKING TREE.** **Nothing committed this session.** New: `src/core/guardrails/prompts/`, `tests/test_guardrails_response_c1.py`, `tests/test_guardrails_citation_c4.py`, `tests/test_plan_verification_coverage.py`, `scripts/verify_plan_coverage.py`, and `logs/p1/step10/{c1_live_probe.py,.json, guardrails_c1c4_verifier.py, guardrails_c1c4_mutation.py, guardrails_c1c4_review.py,.json, guardrails_p0_r8_c2_review.py,.json}`. Modified: `src/core/guardrails/response.py`, `src/core/config.py`, `tests/conftest.py`, `IMPROVEMENTS.md` (§I121), the plan. ⚠️ **Sessions 13–37 remain uncommitted; the branch is ahead of origin and NOTHING is pushed — owner decision, outstanding.**
>
> **8. ▶ NEXT (owner-ordered 2026-11-05).** **(a)** The rest of the cheap-first core: **R10** (the funnel + tournament — ⚠️ needs `data/guardrail_eval.jsonl`, not yet built), then **R4/R6/R9**. **(b)** ⚠️ **The §I121 NLI decision** — the grounding floor's separation must be fixed or explicitly bounded before C5/H* depend on it. **(c) The R5 retrain** — a separate, pre-registerable run. **(d)** Re-probe the cluster (`python3 logs/p1/step10/cluster_probe.py`) — if sparse + rerank return, run #2 and the §G5 ablation. **(e)** ⚠️ **Remind the owner to supply the OLD architecture diagram (guardrails + observability).**
>
> ## ▶ SESSION 37 — ▶ START HERE (2026-11-05). **THE GUARDRAILS BUILD (course-aligned). Two review documents written; the owner approved the package + the cheap-first core + P0.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 37, then `.hermes/plans/2026-11-05-p1-guardrails-course-aligned-SESSIONS.md` — its **status table is the resume point** — and `.hermes/plans/2026-11-05-p1-architecture-v3-coverage-gap.md`. Continue the cheap-first core: **C1** (assertion–evidence bipartite graph, port the lab's `nli_entailment_checker.py`/`semantic_similarity_filter.py`/`groundedness_evaluator.py`), **C4** (ALCE citation faithfulness), **R10** (the funnel + tournament table), then **R4/R6/R9**. ⚠️ **The R5 retrain is a separate, pre-registerable run** (it embeds training queries via the cluster dense lane and overwrites `data/models/intent_classifier.pkl`). ⚠️ Every step: acceptance + independent reviewer + stdlib verifier + mutation proof. Nothing is committed."*
>
> **1. ✅ WHAT WAS BUILT (all in `src/core/guardrails/`, code FROM the Week-6 lab materials).** Owner decisions (2026-11-05): the **package** `src/core/guardrails/`; the **cheap-first core** R1,R2,R3,R5,R7,R8,C1,C2,C4; **R5 retrains the live `IntentRouter`**; **P0** as the plan recommended.
> * **P0** — `config.py`'s four dense defaults REVERTED to the neutral values (Qwen-1024); the deployed nomic-768 values moved to `.env`; a **read-path width guard** (`store._assert_query_width`) now RAISES on a model/collection mismatch instead of 400ing; `tests/conftest.py` pins the dense env so the suite is hermetic from `.env`. Verifier `logs/p1/step10/p0_config_guard_verifier.py` **14/14**; suite back to the documented **4 failed** baseline.
> * **R1** `sanitize.py` (lab `guradrails_req_side.py` + decode/script layers) — 13 tests, mutation 6/6, reviewer **7/7**.
> * **R2/R3** `request.py` — length/complexity bounds + the gibberish ladder (entropy floor **4.5**, MEASURED: English ≈3.9–4.0, base64 ≈4.7). 15 tests, mutation 8/8, reviewer **4 CONFIRMED / 2 REFUTED** (C5 = the author's test count was 15 not 14 — corrected; C1 = a wording misread).
> * **R5** (CODE) — `Intent.OUT_OF_SCOPE` + a refusal route + `is_refusal` + the three-band `gate()` (`guard_domain_out_conf` 0.50 / `guard_domain_in_conf` 0.20) + `train_intent_classifier.py` extended. 9 tests, mutation 7/7, reviewer **7/7**. ⚠️ **Behaviour-neutral until retrained** (a model with no `out_of_scope` class never refuses).
> * **R7** `pii.py` (lab `pii_guardrail.py` + Luhn/AKIA/ghp_) — 9 tests, mutation 7/7 (shared with R8), reviewer **6/6**.
> * **R8** `request.py` — `check_injection` (pattern pass) + `spotlight` (datamasking, U+2063). 5 tests.
> * **C2** `response.py` — citation validity + numbers-in-evidence (tier-1, stdlib). 10 tests, mutation 4/4.
>
> **2. ⚠️ §I114's CEILING STANDS.** The domain gate (R5) targets the **12 `neg-out`** queries only; the **22 in-domain negatives** (`neg-in` 12 + `neg-nea` 10) are the response-side grounding floor's job (C1/C4). The old plan's **G1 is SUPERSEDED** by R5 + the C-workstream; G1's score-floor variant is deliberately not shipped.
>
> **3. ⚠️ TWO THINGS ARE NOT DONE, stated so they are not mistaken for done.** (a) **The R5 retrain** — a run (cluster dense lane + `data/models/intent_classifier.pkl` write); pre-register it and commit the pre-registration ALONE first (D6.1/D6.5). (b) **C1/C3/C4/C5** — the response-side NLI graph needs the cross-encoder model download (`cross-encoder/nli-deberta-v3-base`) on first use.
>
> **4. ⚠️ WORKING TREE.** **Nothing committed this session.** New: `src/core/guardrails/` (6 files), 6 new test files, 5 new `logs/p1/step10/*_mutation.py` + `p0_config_guard_verifier.py`, the two plan docs. Modified: `config.py`, `store.py`, `intent_router.py`, `scripts/train_intent_classifier.py`, `.env` (gitignored), `tests/conftest.py`, `tests/test_lane_resolution.py`, `tests/test_phase_a.py`. ⚠️ Sessions 13–36 remain uncommitted; the branch is ahead of origin and **nothing is pushed** — owner decision, outstanding.
>
> **5. ⚠️ THE CLUSTER — sparse + rerank STILL DOWN** (re-probed session 37: dense 200, ColBERT 200, sparse timeout, rerank timeout). Blocks #2 and the §G5 ablation; the guardrails work is cluster-free.
>
> ## ▶ SESSION 36 — ▶ START HERE (2026-11-05). **⚠️ STILL BLOCKED ON THE CLUSTER (sparse + rerank hang, re-probed). §I118: the sparse lane's silent dropout is now COUNTED — §I96's class closed for the fourth lane.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 36, then `IMPROVEMENTS.md` §I118 and §I113–§I117. ⚠️ FIRST re-probe the cluster: `python3 logs/p1/step10/cluster_probe.py` (sparse + rerank were still hanging on 2026-11-05; the 8123 HTTP front answers unknown paths 404 in 0.08 s, so the handlers hang — NOT a moved endpoint, NOT a dead host). If they are back, run #2 (`logs/p1/step10/router_in_loop.py` → `_verifier.py` → `_mutation.py`). If not: the graph work (G3/G2/G5 — needs only Memgraph + `concept_embeddings` + the dense embedder, which is UP) or the HANDOFF hygiene."*
>
> **1. ⛔ THE BLOCKER — RE-PROBED, STILL DOWN.** `logs/p1/step10/cluster_probe.py` → `cluster_probe.json`: **dense 200 (0.19 s) · ColBERT 200 (0.12 s) · sparse timeout (35 s) · rerank timeout (35 s)** — reproduces session 35 exactly. `cluster_probe_alternates.py` excludes the competing hypotheses: `10.0.10.70:8123` answers unknown paths with a **404 in 0.08 s** (front ALIVE) and the same timeout recurs on `:8000` ⇒ the **sparse/rerank handlers hang** (a service-level hang, not network/port/route). Verifier `cluster_probe_verifier.py` **7/7 PASS** + mutation proof. ⇒ **#2 and the demo's retrieval path stay BLOCKED; the owner cannot restart the services.**
>
> **2. ✅ §I118 — THE SPARSE LANE'S SILENT DROPOUT IS NOW COUNTED.** §I96's counters existed for ColBERT/DA/RAPTOR/GRAPH; the **sparse** lane's `except` in `store._qdrant_search` only logged. It now increments `self.sparse_dropouts` / `self.last_sparse_dropout`, byte-for-byte the ColBERT shape — **13 lines, behaviour-neutral on success, query-time only, no re-ingest.** Tests `test_lane_dropout_counters.py` **15/15**; mutation `sparse_dropout_mutation.py` (M1/M2/M3, no inert check); independent reviewer **gpt-oss-20b (deleg_1b9df948)** — **5/5 claims CONFIRMED** (⚠️ its cited test line numbers were wrong; the identifiers resolve and C5 was re-derived by the author, so the substance holds — §I118 records this).
>
> **3. ⚠️ PRE-EXISTING TEST FAILURES (NOT this session's — verified by stashing the change).** 4 fail on HEAD too: `test_phase1::test_hybrid_search_includes_global`, `test_phase2::test_search_still_works_after_phase2`, and `test_splade` ×2 — all `FileNotFoundError: tests/data/sample_physics.pdf` (a missing generated fixture), unrelated to the retrieval path. **Not fixed here (out of scope).**
>
> **4. ⚠️ WORKING TREE / VERIFICATION.** Uncommitted: `src/pdf_ingestion/store.py` (+13), `tests/test_lane_dropout_counters.py` (+100), §I118 in `IMPROVEMENTS.md`, this HANDOFF block, and the four new `cluster_probe*` + `sparse_dropout_mutation` scripts/artifacts under `logs/p1/step10/`. ✅ **The independent reviewer's verdict LANDED: 5/5 claims CONFIRMED** (gpt-oss-20b, `deleg_1b9df948`, read-only) — so §I118 is verified and **ready to commit**; it is left **uncommitted** (the owner has an outstanding branch/push decision and did not ask for a commit). Sessions 13–35 remain uncommitted; the branch is ahead of origin and **nothing is pushed**.
>
> **5. ✅ §G5/§I2 — GENUINE MULTI-HOP BUILT, DEFAULT-OFF, VERIFIED.** New setting `cfg.graph_max_hops` (default **1** = shipped) + a branched `graph_search`: `== 1` keeps the legacy Cypher byte-identical; `>= 2` traverses `RELATES_TO` and reports a real `hop_distance`. **Live probe** (8 multihop queries): hop-1 all 0; hop-2 `{0,1,2}` and **+388…+492 new chunks/query (8/8)**, ~2.1 s. ⚠️ Live-only findings: **Memgraph has no `length()` on paths** (use `size(relationships(p))`); **3-hop = 66.5 s** so the bound is clamped to **2**; the expansion's tail is invisible at the shipped hop-first ranking. Tests 6/6; mutation 6/6 reddened, none inert; verifier **7/7 CONFIRMED** (`deleg_fa7bdec1`). ⚠️ **§I2 only PARTLY closed** — it ships OFF until its **ablation** runs, which is BLOCKED on the cluster. See `IMPROVEMENTS.md` "G5 outcome".
>
> **6. ✅ §G3 — THE SENSITIVE RE-MEASUREMENT: still UNRESOLVED, but DIRECTIONAL.** Pre-registered a sensitive endpoint (per-query ≥2-concept chunk count, paired, n=200) over the two 2026-10-22 artifacts. **138 → 158** (reproduces §I51 exactly); mean delta 0.10, CI [−0.013, +0.213] ⇒ **UNRESOLVED**; **11 W / 1 L / 188 ties**. ⇒ unresolved, **NOT** negative — underpowered on this endpoint, and it does not license "entity resolution doesn't help retrieval". Verifier 9/9 + mutation 9/9 no inert; independent verifier **7/7 CONFIRMED** (`deleg_7ed32af1`). See IMPROVEMENTS "G3 outcome".
>
> **7. ✅ §I119 — THE DERIVED LANE'S QWEN-INSTRUCTION LEAK, FIXED.** `get_derived_embedder` copied the model+width but **not the instruction**, so the derived (nomic-768) embedder carried the **arm's** `query_instruction` — Qwen's `Instruct: … Query: ` under the default config (`step10_env.sh` masks it). New `derived_query_instruction = "search_query: "`, copied in ⇒ the derived lane is nomic end-to-end. Tests 5/5, mutation 5/5 no inert, verifier **5/5 CONFIRMED** (`deleg_ed3b2cce`). ⚠️ **Adjacent latent trap recorded, not fixed:** the config defaults are the retired Qwen/v2 world (`dense_model` 1024) while the deployed `knowledge_base_v3` is **768** — a run without the `DENSE_MODEL` override 400s the main dense lane (measured).
>
> **8. ⚠️ §I120 — THE LAB COMPARISON + THE CO-OCCURRENCE FLOOD.** The course lab (`Labs/Week_5/week5.2/memgraphrag_concepts`, MemGraphRAG) uses a **three-layer memory (Schema/Fact/Passage) → heterogeneous typed graph → PPR with per-layer resets + applied hub suppression**, PPR as **the retrieval**. **We match the PPR iteration, not the architecture** (no schema layer, co-occurrence edges, single reset, hub suppression only reported, PPR as a re-ranker). ⇒ **§G1's null is about PPR over a dense untyped graph, not about the lab's method.** Measured density: the pool is **15 pages shipped → 296 (1-hop) → 802 (2-hop)** of ~906 — **the hop expansion is a FLOOD**, so a page-level PPR ablation on it is saturated. Also: the `*0..2` path-enumeration Cypher is pathologically slow; use level-by-level DISTINCT neighbours (0.2–0.4 s).
>
> **9. ▶ NEXT (owner-ordered 2026-11-05).** **(a) The full guardrails plan + implementation — input AND output — NEXT.** **(b) THEN the lab-aligned graph plan** (scope already written: `.hermes/plans/2026-11-05-p1-lab-aligned-graph-SCOPE.md`) — build the MemGraphRAG substrate (typed triples / three-layer memory / per-layer PPR resets / applied hub suppression) so a PPR test is a fair test of the lab's method; ⚠️ a capability build, not a metric win (§I98/§I100 bound it). **(c) Re-probe the cluster** (`python3 logs/p1/step10/cluster_probe.py`) — if sparse + rerank return, run **#2** and the §G5 ablation. **(d) The deck** rework (external for Mr. Asif + internal ablation register). **(e)** ⚠️ **Remind the owner to supply the OLD architecture diagram (guardrails + observability).**
>
> **10. ⚠️ IN-FLIGHT — DO NOT LOSE: the §I119 DEFAULT-TRAP fix is APPLIED but NOT verified, and the SUITE REVEALS IT FIGHTS A DOCUMENTED DESIGN.** `src/core/config.py` defaults were aligned to **nomic-768** (`dense_model`, `dense_dim=768`, `query_instruction="search_query: "`, `document_prefix="search_document: "`). ⚠️ **Fast suite: 17 failed / 754 passed** — 4 pre-existing (the missing `tests/data/sample_physics.pdf`) + **13 from this change**, and **two of them are DELIBERATE, documented invariants**:
> - `test_config_invariants::test_dense_lane_dim_defaults` **pins `dense_model == "Qwen/Qwen3-Embedding-0.6B"` and `dense_dim == 1024`**.
> - `test_config_invariants::test_document_prefix_defaults_empty_and_is_the_query_instruction_twin` **asserts the code default MUST be empty**, docstring: *"a non-empty default would silently prefix every passage for a model that does not want it. `.env` is the whole mechanism."*
>
> ⇒ **The code default is INTENTIONALLY neutral; `.env` carries the environment.** So the code-default edit fights the design. **RECOMMENDED DIRECTION (owner call):** **revert** the `config.py` default change and instead **(a)** set the deployed values in `.env` (`DENSE_MODEL`, `DENSE_DIM`, `QUERY_INSTRUCTION`, `DOCUMENT_PREFIX` — the intended mechanism; ⚠️ `.env` currently sets `QDRANT_COLLECTION=knowledge_base` (768) but NOT `DENSE_MODEL`, which is exactly why the trap bites) and **(b)** add the **read-path width guard** on the main dense lane (a model/collection mismatch must RAISE, not 400 silently — the §A guard covers the derived lanes only). The other 11 failures are tests encoding the old convention (`test_cluster_embedder::test_no_document_prefix_sends_the_text_verbatim`, `test_late_chunk_embedder` ×4, `test_dense_lane`, `test_lane_resolution::test_v2_is_queried_at_its_own_64d_width`, `test_dense_prefetch_limit`, `test_colbert_lane_dropout::test_file_backed_qdrant_is_not_a_dropout`, `test_chunking_pipeline`, `test_config_invariants::test_intent_router_rejects_a_legacy_dim_classifier`). Re-run: `unset PYTHONPATH && .venv/bin/python -m pytest tests/ -q -m "not slow" -rf`. ⚠️ **Behaviour-affecting — do NOT commit unverified.**
>
> ## ▶ SESSION 35 (2026-11-05). **⚠️ BLOCKED ON THE CLUSTER (sparse + rerank down). The citation metric was vacuous and is fixed; the eval bypasses the router.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 35, then `IMPROVEMENTS.md` §I113–§I117. ⚠️ FIRST probe the cluster: on 2026-11-05 the sparse and rerank POSTs to `10.0.10.70:8123` timed out (only dense + ColBERT answered), which blocks every retrieval run, #2 and the demo. If they are back, run #2 (`logs/p1/step10/router_in_loop.py` → `_verifier.py` → `_mutation.py`). If not: §I96's dropout counter, the graph work (G3/G2/G5), or the HANDOFF hygiene."*
>
> **1. ⛔ THE BLOCKER — the cluster is degraded.** `10.0.10.70:8123`: dense embeddings **200**, ColBERT **200** (`lightonai/GTE-ModernColBERT-v1` and the repo's `colbert-ir/colbertv2.0`, both 128-dim, via the custom-override field); **sparse → timeout**, **rerank → timeout** (≥30 s). `run_retrieval` then SILENTLY drops the sparse lane and returns the CE UNRANKED (§I96's class) — so **no retrieval run is measurable** and the demo's retrieval path is degraded. **The owner cannot restart the services.**
>
> **2. ✅ §I113 CLOSED — RAPTOR as generator context: a NULL, and FLAGGED.** 40 overview queries, 0 errors, wall 5,976 s. Paired faithfulness **−0.0320, CI [−0.1009, +0.0368], UNRESOLVED** (point estimate negative); answer_relevance/citation bit-identical. Verifier **24/24**, mutation **24/24**. ⚠️ **G6 FAILS** — arm A (0.4551) missed the §I108 anchor (0.5097); **diagnosed: the harness's arm-A system prompt ≠ the product's `_SYNTH_SYSTEM`**, so arm A is not the product path. Owner decision pending.
>
> **3. ✅ §I114 — the G1 pre-flight diagnostic (read-only).** The input guardrail **cannot** be built from the cheap signals: the 34 negatives are THREE problems (12 off-domain / 12 in-domain-not-covered / 10 book-lacks-the-value); a top-1 score floor is weak (AUC 0.774; best F1 0.50 at a 0.40 false-refusal rate); an off-domain signal tops out at **12/34**. ⇒ **G1 narrows to off-domain; the 22 near-domain negatives belong to G2's grounding floor.**
>
> **4. ✅ §I115 — the citation metric was VACUOUS and is FIXED.** It matched `[Page <ascii-space>N]`; the generator emits `Page`+**U+202F** or **`【Page N】`**, so it found **zero** citations in all 166 answers and returned **1.000 by its own "no citations — not penalised" rule**. Real: **85 % of answers cite a page; 65 % of cited pages were retrieved** (53/166 cite nothing). **Fixed:** the metric (both brackets + any Unicode space; returns **None** when uncited; + a `Cit.Cov.` column) and `_cited_pages` in **both** frontends. Verifier **14/14**, mutation **14/14**, **cross-family reviewer 7/7 CONFIRMED**. ⚠️ **Do NOT quote citation 1.000.** The generator's citation FORMAT is still inconsistent — a prompt fix is open (needs its own run).
>
> **5. ✅ §I116 — the eval BYPASSES the intent router.** `evaluate_rag.evaluate_query:817` uses the **gold** `query_type`; both frontends route with `IntentRouter.classify()` (**agreement 0.5714**), gating **HyDE, lane selection AND the rerank query**. §I97 measured the CE-query mis-set at **factual nDCG −0.136**. ⇒ **every published number is an ORACLE-ROUTING upper bound.** Pre-registered and **committed ALONE (`1729344`)**; the harness + verifier (12 checks) + mutation (12/12 on a synthetic fixture) are **written and ready** — it needs only the cluster.
>
> **6. ⚠️ §I117 — the cluster's embedder models moved, and the repo's upgrade fields were DEAD CONFIG.** ColBERT now lists **only** `lightonai/GTE-ModernColBERT-v1`; sparse lists `Qdrant/bm42-…`, `Qdrant/bm25`, `prithivida/Splade_PP_en_v1`. `config.py` **declared** `sv_colbert_model`/`sv_sparse_model` but **nothing read them** — now **wired** (prefer the cluster id when non-empty; **defaults are EMPTY** so nothing switches by accident; verifier **8/8**, mutation **8/8**). ⚠️ A model switch needs the lane **re-embedded** — a query-side change alone silently mismatches the stored vectors.
>
> **7. ✅ THE DECK IS REBUILT (17 pages/slides) with the corrected numbers.** The false citation 1.000 lived in **three** files (`make_demo_deck.py`, `make_demo_deck_pdf.py` — its own copy — and the hand-written `demo_deck.md`); all corrected, rebuilt, and **read back to verify**. Added: **Cite % + Validity** in the generator table, the §I112/§I113/§I115/§I116 rows in the levers ledger, and an explicit **ORACLE ROUTING — upper bound** caveat on the retrieval slide.
>
> **8. ⚠️ WORKING TREE.** Committed this session: **ONE** — the #2 pre-registration ALONE (`1729344`, D6.1). Everything else is uncommitted (**241 changed/untracked**): §I113–§I117, the citation fix + its verifier/mutation/artifact, the router harness + verifier + mutation, the config wiring + its verifier/mutation, the two embedder edits, the tests, and the deck (3 formats + 2 generators). ⚠️ **Sessions 13–34 remain uncommitted; the branch is ahead 132 of origin and NOTHING is pushed — owner decision, outstanding.**
>
> **9. ⚠️ NEXT, IN ORDER.** **(a) Probe the cluster** — if sparse + rerank are back, run #2 (the artifact files are the interface). **(b) §I96's dropout counter** — cluster-free, and we just got bitten by exactly that silent failure. **(c) The graph work** (needs only Memgraph + `concept_embeddings` + the dense embedder): **G3's sensitive re-measurement** (read-only, closes the one open graph null), **G2 community detection** (the Leiden gate passes), **G5/§I2 real multi-hop** (`hop_distance` is a constant 0). ⚠️ Caveat: the graph lane as wired is a measured content HARM (§I98) — capability + closing nulls, not a metric win. **(d) NG-P5/NG-P6** (NiceGUI upload / role gating). **(e) ⚠️ HANDOFF hygiene** — this file is **3,474 lines** and loads into every session; archive all but the recent blocks into `HANDOFF_ARCHIVE.md` (grep the durable files for anything dropped FIRST — a trim is a migration).
>
> **10. ✅ ENV NOTE (corrected 2026-11-05 — the first reading was WRONG).** The `*curl*|*sh*` deny glob in `~/.hermes/config.yaml` is a **literal-glob `curl … | sh` RCE guard**, not an "or": the `|` is a character, not alternation. **Verified live: `echo sh` passes**, so it does **NOT** block `source .hermes/step10_env.sh` or `bash …` — an earlier note in this session claimed it did and was wrong. It fires only when a command pipes a `curl`/`wget` **and** later contains `sh` (it caught one probe that had `curl … | python3 …` plus a later `…env.sh`). **No action needed; cluster runs and build scripts are unaffected.**
>
> ## ▶ SESSION 34 (2026-11-04). **ITEM 10 EXECUTED: the QUERY-side retrieval-signal lever is CLOSED (§I112, a clean null); RAPTOR-as-generator-context (§I113) is IN FLIGHT; and the first guardrails/observability step shipped (O1).**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 34, then `.hermes/plans/2026-11-04-p1-guardrails-observability-SESSIONS.md` (the guardrails + observability plan — O1 done, O2→G1→G2 next) and `IMPROVEMENTS.md` §I112. The artifact files are the interface. Continue the ordered plan; the frontend workstream resumes at NG-P4."*
>
> **1. ✅ §I112 — THE QUERY-SIDE SIGNAL LEVER IS CLOSED (NULL).** `overview_signal_probe.py` (40 overview queries, dense lane alone, read-only; prereg `f93b9e6`). Artifact `logs/p1/step10/overview_signal_probe.json` (sha256 `a72d5256…`), **all 7 guards pass**, verifier **10/10**, mutation **10/10**. Arms (R@20): **A** single HyDE hypothetical **0.2128** (reproduces §I111 to the digit) · **B** raw query **0.1489** · **C** multi-hyp max N=5 **0.2150** · **D** mean **0.2140**. Paired vs A: **C−A +0.0021, D−A +0.0012 — both UNRESOLVED**; **B−A −0.0639 RESOLVED NEGATIVE** (the control). ⇒ **no query representation beats the shipped single hypothetical**; per the prereg's falsification clause the **query side is closed** — the signal lever left is the **DOCUMENT side** (embedder / re-ingest). ⚠️ **The first full run was VOID** — G4 caught a harness dedup defect (`_dense_lane` kept raw chunk hits; `store.search` does NOT page-dedup) that faked a "C/D RESOLVED POSITIVE +0.027"; fixed, addendum §9 written, void artifacts preserved (`overview_signal_probe_VOID_run1.json`). Registered **§I112**; folded into the deck.
>
> **2. ⏳ §I113 — RAPTOR AS GENERATOR CONTEXT (in flight).** Full run launched 2026-11-04 (`background`, `persist_on_release`), logging to `logs/p1/step10/raptor_context_run.txt`, ETA ~21:40; artifact `logs/p1/step10/raptor_context.json` is the interface (it currently still holds the 2-query DRY-RUN). Dry-run PASSED (G1/G6 fail only because n=2). **verifier `raptor_context_verifier.py` (24/24) + mutation `raptor_context_mutation.py` (17 mutations, 24/24 reddened, no inert) are WRITTEN AND PROVEN.** ⚠️ **When it lands:** run the verifier + mutation, register **§I113**, fold into the deck (`bash logs/p1/step10/build_deck.sh`). Arms: A CE top-20 pages · B pages + top-2 RAPTOR summaries in the prompt.
>
> **3. ✅ O1 (§I4) — PHOENIX NOW TRACES THE LLM STAGE.** Manual `llm.call` spans added in `src/core/llm.py` (`_call_openai`/`_call_ollama`, BELOW the monkeypatch point, no-op when Phoenix off). Verifier `logs/p1/step10/llm_span_verifier.py` **9/9**; mutation `llm_span_mutation.py` **9/9 reddened, no inert**.
>
> **4. ▶ NEXT, IN ORDER (the guardrails + observability plan).** Read `.hermes/plans/2026-11-04-p1-guardrails-observability-SESSIONS.md` — its status table is the resume point. **O1 ✅ DONE** (§I4: manual `llm.call` spans in `src/core/llm.py`; verifier 9/9, mutation 9/9) **→ O2 ✅ DONE** (per-query route/latency trace: new `src/core/query_trace.py` + wired into `run_retrieval` + a "Recent queries" Status surface; verifier 12/12, mutation 12/12) **→ ⬜ G1 NEXT** (input guardrail: off-topic/abstention, measured on the **34 negatives** in `data/eval_queries_v2.json` — ids `neg-*`, `answerable:false`, `relevant_pages:[]`. ⚠️ The router is a trained sklearn classifier with a `dense_dim` schema check, so an `out_of_scope` class needs a RETRAIN; the cheaper path is a score-floor gate, and `scripts/evaluate_rag.py` already has an abstention guardrail to reuse) **→ ⬜ G2** (output guardrail: grounding floor + citation validity, decisions counted). Each step: acceptance + independent verifier + mutation proof.
>
> **5. ⚠️ WORKING TREE.** Committed this session: **NONE**. Uncommitted: `src/core/llm.py` (O1), new `src/core/query_trace.py` + `scripts/evaluate_rag.py` + `src/frontend/streamlit_app.py` (O2), the three new verifier+mutation pairs (`llm_span_*`, `query_trace_*`, `raptor_context_*`), the fixed `overview_signal_probe.py`, §I112 in `IMPROVEMENTS.md`, the prereg addendum, the deck (rebuilt), the guardrails/observability plan, and a scratch `logs/p1/step10/_diag_d100.py`. Sessions 13–32 remain uncommitted; **nothing pushed** — owner decision, outstanding.

> ## ▶ SESSION 33 — ▶ START HERE (2026-11-04). **THE MEASUREMENT PROGRAMME IS ESSENTIALLY CLOSED ON THE RETRIEVAL SIDE; THE OPEN LEVER IS THE LANES' OWN SCORING.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 33, then `IMPROVEMENTS.md` §I111 (the
> pool-order attribution) and §I110 (the overview k=50 run). The ordering loss is NOT the fusion — the
> fused order equals dense-only — it is the LANES' scoring: 60.5% of the pooled gold sits at ranks
> 21–100. Continue with the ordered list below; pre-register each run and commit the pre-registration
> ALONE first (D6.1). The frontend workstream resumes at NG-P4."*
>
> **1. ✅ THE ARCHITECTURE IS BUILT AND VERIFIED.** `Docs/synapse_architecture_v2.html` + `.pdf`
> (2 SVG diagrams: **ingestion** Phases 1·2·3, **retrieval** steps 1–7), replacing the stale Sep-1
> reference (940 pages, `knowledge_base`, Llama 3.2). **Verified twice:** a mechanical verifier
> (`logs/p1/step10/arch_v2_verifier.py`, **48/48 PASS** — every claim re-derived from `config.py` /
> `store.py` / `evaluate_rag.py` / the live Qdrant) and an **independent cross-family reviewer**
> (`gpt-oss-20b`, read-only): **11/12 confirmed**. ⚠️ **Its one refutation is INVALID** — it read
> `config.py`'s *default* (`meta-llama/Llama-3.2-8B-Instruct`); `.env` overrides it and the *resolved*
> `openai_model` is `openai/gpt-oss-20b`. Two checks now pin the resolved value.
>
> **2. ✅ THE GENERATOR IS MEASURED (§I108).** `v3_judged_full` (200 queries, cross-family judge):
> overall **faithfulness 0.636 · answer_relevance 0.857 · citation 1.000**; per type faithful/ans.rel —
> factual **0.683/0.855** · multihop **0.702/0.742** · overview **0.510/0.975**. Closes the "generator
> unmeasured" gap. ⚠️ Judge score, one run, no independent verifier.
>
> **3. ✅ T3 RAN — FLAGGED (§I109).** `t3_lane_complete.json`; 11/12 guards pass, **G8 FAILS**.
> **DIAGNOSED: the anchor is STALE, not the harness** — §I85's rows predate (a) the per-type
> rerank-query policy (`e0f1616`, which changes arm A's CE top-20 on exactly the 39/53 FACTUAL queries
> while its pool stays bit-identical) and (b) v3's pooled re-embed (which changes arm B's pool on
> 133/133). Per its own §8 the run reports nothing; **needs an owner decision** (re-register the anchor
> or re-run). ⚠️ T3 has no verifier and no mutation proof.
>
> **4. ✅ THE OVERVIEW k=50 GENERATOR RUN — NO BENEFIT (§I110).** Pre-registration committed ALONE
> (`d297da4`). Paired vs k=20 (n=33): **faithfulness 0.5278 → 0.4773, Δ −0.0505, CI [−0.1373, +0.0362],
> UNRESOLVED** (point estimate NEGATIVE); context_precision **−0.1085 RESOLVED NEGATIVE**.
> ⇒ **§I105/§I106's open reading is CLOSED: wider k does NOT pay on the answer side.**
>
> **5. ✅ THE POOL-ORDER ATTRIBUTION (§I111, read-only).** Over `fusion_attribution.json`, 133 queries:
> **FUSED@20 ≈ dense-only@20** (all +0.0222, unresolved; overview −0.0025) ⇒ **the fusion is NOT the
> culprit**; cap-500 ≈ fused (the cap appends, never reorders). **39.5 % of the pooled gold is in the
> top-20; 60.5 % sits at ranks 21–100.** ⇒ **the gold is ranked low by the LANES themselves.**
> ⚠️ **And the ceiling is arithmetic:** `R-ceil@20` for overview = `20 × mean(1/n_rel)` = **0.3992**
> exactly (label sets: min 22 / median 56.5 / mean 73.8) — **no retriever can beat ~0.35 there**.
>
> **6. ✅ THE DECK IS COMPLETE (17 pages/slides).** `logs/p1/step10/demo_deck.{pdf,pptx,md}` — complete
> retrieval metrics (coverage/R@20/R-ceil/P@20/P-ceil/nDCG/MAP/MRR/Hit), generator metrics, the per-type
> k table, **the §I99 loss decomposition** and **the §I111 attribution**, the levers ledger, and the
> architecture appendix (p16–17). **Rebuild with `bash logs/p1/step10/build_deck.sh`** (it merges the
> architecture pages idempotently — do NOT regenerate the deck PDF alone).
>
> **7. ▶ NEXT, IN ORDER (cost vs benefit).** **(a) A CE score-prior/blend** — so the CE cannot demote a
> strong-pool page (cheap; targets §I97's mechanism; ceiling = `waste_ce` 0.022 for overview).
> **(b) A stronger/other cross-encoder** (untried). **(c) The RAPTOR lane re-placed as an APPEND** for
> overview (its lane is off the eval path and *displaces* when fused, §I98). **(d) The CE fine-tune**
> (priced: 0.026 factual / 0.022 overview / nothing multihop; signoff 6 open). **(e) A better retrieval
> SIGNAL for overview** — the only class of fix the attribution leaves standing. ⚠️ **CLOSED — do not
> re-open:** the fusion's order (§I100/§I111), the cut (§I102/§I110), score fusion (§I103), lane
> inclusion (§I98), wider k (§I105/§I106/§I110), MMR (§I92), the cap (§I92).
>
> **8. ▶ FRONTEND WORKSTREAM — RESUME AT NG-P4.** Read
> `.hermes/plans/2026-11-02-p1-nicegui-and-visual-lane-SESSIONS.md`; its status table is the resume
> point. **NG-P1/P2/P3 are DONE** (skeleton 8504; Ask-a-Question; read-only Status/Cards/RAPTOR).
> **⬜ NEXT: NG-P4 — the Visual + Graph tabs** (page images render; graph nodes match
> `get_graph_builder(cfg)`), then NG-P5 (upload), NG-P6 (role gating), then VL-L1/L2/L3. ⚠️ Streamlit
> stays primary on 8503; NiceGUI is an ADDITION. ⚠️ Run pytest with a **scrubbed env** (§1b).
>
> **9. ⚠️ WORKING TREE.** Committed this session: **ONE** — the k=50 pre-registration ALONE (`d297da4`,
> D6.1). Everything else is uncommitted (~194 changed/untracked): §I108–§I111, the architecture
> html/pdf + verifier, the deck (3 formats + generators + `build_deck.sh`), the k=50 harness/artifact,
> the attribution script, the deck appendix images, `data/eval_queries_overview.json`. ⚠️ **Sessions
> 13–32 remain uncommitted; the branch is ahead of origin and NOTHING is pushed — owner decision,
> outstanding.**
>
> **10. ⏳ TWO RUNS ARE PRE-REGISTERED AND CODE-COMPLETE — DRY-RUN, THEN LAUNCH (NOT YET RUN).**
> Both pre-registrations are committed ALONE (`f93b9e6`). Neither full run has been launched — the owner
> asked to re-dry-run in the next session first (context was ~50%). **Do this, in order:**
>
>   **(a) TASK 1 — the overview retrieval-signal probe (§I112).** Question: does a different QUERY
>   REPRESENTATION make the dense lane rank the overview gold higher? Arms **A** single HyDE hypothetical
>   · **B** raw query · **C** multi-hypothetical max (N=5) · **D** mean. Read-only, dense lane alone,
>   40 overview queries.
>   * prereg `.hermes/plans/2026-11-04-p1-overview-signal-probe-preregistration.md`
>   * harness `logs/p1/step10/overview_signal_probe.py` · verifier `..._verifier.py` · mutation `..._mutation.py`
>   * **dry-run PASSED 2026-11-04** (`--limit 2`; G1/G4 fail only because it is 2 queries). It wrote a
>     **2-query hypotheses cache** (`overview_signal_hypotheses.json`) — ⚠️ the cache is MERGED, so the
>     full run fills the other 38 (do NOT delete the cache; it is the frozen-hypotheses record).
>   * run: `.venv/bin/python logs/p1/step10/overview_signal_probe.py` then
>     `.venv/bin/python logs/p1/step10/overview_signal_probe_verifier.py` then
>     `.venv/bin/python logs/p1/step10/overview_signal_probe_mutation.py`
>
>   **(b) TASK 2 — RAPTOR as generator context (§I113).** Question: do RAPTOR summaries given to the
>   GENERATOR (never the ranked list) improve overview faithfulness? Arms **A** CE top-20 pages · **B**
>   pages + top-2 RAPTOR summaries in the prompt. 40 overview queries, cross-family judge.
>   * prereg `.hermes/plans/2026-11-04-p1-raptor-generator-context-preregistration.md`
>   * **dry-run PASSED 2026-11-04** (`--limit 2`, after fixing a guard key bug: G4 read `page_list`
>     instead of `page_list_A`). It wrote `logs/p1/step10/raptor_context.json` (2 queries). **verifier +
>     mutation still NOT written** — write them from the artifact's field inventory (the repo's rule:
>     every check reddened by ≥1 mutation, no inert check) before the full launch.
>   * run: `.venv/bin/python logs/p1/step10/raptor_context_eval.py`
>
>   **Env for both** (unset PYTHONPATH first): `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
>   DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5" DENSE_DIM=768 DENSE_DIM_LOW=64
>   DOCUMENT_PREFIX="search_document: " QUERY_INSTRUCTION="search_query: " DA_ENABLED=true`.
>   **Launch with `background=true, persist_on_release=true`** so they survive `/new`; the **artifact
>   files** are the interface, not the process ids.
>   ⚠️ **Shape facts already probed:** `store.search()` returns **flat** hits (no nested `payload`) —
>   `page_number` is a top-level key; `search_raptor` carries the summary in **`text`**, `raptor_level`,
>   `source_type='raptor_summary'`, and has **no `page_number`**. `call_llm` has **no temperature knob**
>   (diversity comes from the prompt).
>
> ## ▶ SESSION 32 — ▶ START HERE (2026-11-02). **A NEW RESUMABLE WORKSTREAM: the NiceGUI frontend + the visual-lane levers. Read `.hermes/plans/2026-11-02-p1-nicegui-and-visual-lane-SESSIONS.md` — its status table is the resume point.**
>
> **1. ✅ NG-P1 DONE — the NiceGUI skeleton.** `src/frontend/nicegui_app.py` runs on **port 8504**
> (`/healthz` → 200; `/` → 200; `resolved_config()` == the exported env, 0 mismatches). ⚠️ **Streamlit
> is UNTOUCHED and still the primary frontend on 8503** (`/healthz` ok) — this is an ADDITION, per the
> owner's correction. The plan is `logs/p1/step10/nicegui_migration_plan.md`; phases NG-P2…NG-P6 pending.
>
> **2. ✅ THE VISUAL-LANE VALIDATION RAN — read `IMPROVEMENTS.md` §I107.** ⚠️ **The ColPali aperture
> CANNOT separate in-domain from near-domain**: a near-domain image (H 2p orbital, top-1 cosine
> **0.5609**) outscores the weakest in-domain concept (**0.4936**); the floor is high (noise **0.4578**,
> a logo **0.4355**); **`separating: NONE`**. V1 passes **12/12** but at **cos 1.0000 — a self-match
> signature, not cross-render proof**. ⇒ the lane has **neither a labelled retrieval metric NOR a usable
> confidence gate**. The fix path (levers 1–3) is Part B of the session brief.
>
> **3. ✅ THE PHASE-3 VISUAL WRITE COMPLETED (2026-11-02).** 968 ColPali page vectors written for the
> **current** doc `7ba61432` (13/13 checks PASS); `visual_knowledge_base` = **968 new + 1,033 old =
> 2,001**. The demo runbook's "visual lane has no data for the current doc" caveat is **RESOLVED**.
>
> **4. ✅ BOTH "IN-FLIGHT" JOBS HAVE LANDED (recorded 2026-11-02, session 32 — they finished AFTER this block was written).**
> **(a) ✅ THE GENERATOR EVAL RAN — read `IMPROVEMENTS.md` §I108.** `data/eval_results/v3_judged_full_2026-11-03_0115.{json,md}`.
> Cross-family judge (`Qwen/Qwen3-VL-8B-Instruct` vs generator `gpt-oss-20b`). Synthesis **167/200**,
> 5,057 judge calls 0 failed. **Overall faithfulness 0.636 · answer_relevance 0.857 · citation acc 1.000**;
> per type faithful/ans.rel — factual **0.683/0.855** · multihop **0.702/0.742** · overview **0.510/0.975**.
> Abstention 22/34. ⇒ **the "generator unmeasured" gap is CLOSED**; faithfulness is moderate and tracks
> the retrieval weakness (overview lowest). ⚠️ Judge score, single run — no verifier/mutation yet.
>
> **(b) ⚠️ T3 RAN BUT IS FLAGGED — read `IMPROVEMENTS.md` §I109.** `logs/p1/step10/t3_lane_complete.json`
> (sha256 `f7153581657092d8…`), 6 arms, 133 queries, 0 errors, HyDE frozen, read-only. **11 of 12 guards
> PASS** (incl. **G5 — arm A's DA lane live 133/133, so §A holds inside the full funnel**); **G8 FAILS.**
> It self-reports P1 cR@20 **+0.0104 RESOLVED → "ships"**, overview +0.0194 RESOLVED, and **A_on−A_off
> −0.0181 RESOLVED NEGATIVE** (DA+graph hurt arm A) — **but per its own pre-registration §8, G8's failure
> means the run reports nothing.** ⚠️ **DIAGNOSED: G8's anchor is STALE, not the harness.** §I85's rows
> predate TWO documented changes: (1) the **per-type rerank-query policy** (§I97/T4) shipped in `e0f1616`
> — `rerank_query` is now `hyp if overview else query_text`, which changes arm A's CE top-20 on **exactly
> the 39/53 FACTUAL queries** (0/40 overview, 0/40 multihop) while its **pool stays bit-identical**;
> (2) **v3 was re-embedded POOLED** (session 21, §I89) after Stage F measured it late-chunked, which
> changes **arm B's pool on 133/133** (arm A's pool bit-identical ⇒ the pool code path is unchanged).
> ⇒ **G9's "single-variable" claim was wrong; T3's verdict needs an owner decision** (re-register the
> anchor against the current `_off` config, or re-run). ⚠️ **T3 has NO verifier and NO mutation proof**
> (prereg §7 required `t3_verifier.py`/`t3_mutation.py` — neither exists).
>
> **5. ✅ NG-P2 DONE (2026-11-02) — the Ask-a-Question tab; ⬜ NEXT is NG-P3.** The tab is in
> `src/frontend/nicegui_app.py` (`run_ask` mirrors the Streamlit ask path; `run.io_bound` + spinner +
> timeout/error banners; Streamlit and the backend untouched). ⚠️ **The literal acceptance — "cited
> pages match Streamlit" — is REFUTED as a stable test: the generator SAMPLES** (the same NiceGUI path
> cited `[]` then `[180,195,197,224]` on the factual query across two reps). **The restated
> deterministic claim HOLDS:** the two frontends RETRIEVE the same page set — overview 20/20, factual
> 19/20 with only the lowest-ranked page varying (the **§I103 lane-tail nondeterminism**). UI wiring
> proved headlessly (`tests/nicegui/test_nicegui_ask_tab.py`; mutation reddens the thread assertion).
> Verifier `deleg_0ee79bf9` (read-only) confirmed all 5 claims — ⚠️ **with one arithmetic slip I caught
> by re-deriving it myself (`common_pages` 18 → the correct 19)**. Suite `4 failed / 745 passed /
> 7 skipped`, 0 new. Full write-up in the session brief's **§1a**. **NEXT:** **NG-P3** (Status/Cards/
> RAPTOR read-only tabs), then NG-P4, NG-P5, NG-P6, then **VL-L1** (calibrate the visual statistic).
>
> **5b. ✅ NG-P3 DONE (2026-11-02) — read-only Status / Cards / RAPTOR tabs; ⬜ NEXT is NG-P4.** Three read-only
> tabs added (Status / Cards / RAPTOR); the Streamlit Delete section is deliberately **not** ported.
> Acceptance harness `logs/p1/step10/ng_p3_acceptance.py` → **36/36 PASS**, every count re-derived
> against a direct `DocumentStore` call (2 docs; chunks 8,844 · cards 157,826 · RAPTOR 157 · visual
> 968; RAPTOR L1 72 / L2 9 / L3 3). ⚠️ **Its first draft keyed on FILENAME and produced 4 false
> failures — the SQLite file holds TWO documents with the SAME filename** (old + current ingest,
> 0 vs 968 page images); fixed to key on the id, and the Status table gained a **Doc ID** column.
> UI wiring proved headlessly (`tests/nicegui/test_nicegui_readonly_tabs.py`, mutation-proof).
> ⚠️ **NEW TEST TRAP:** running the suite with the **demo env exported** makes **11 extra tests fail**
> (`test_late_chunk_embedder` ×5 …) — **run pytest with a scrubbed env** (`env -u DENSE_MODEL -u
> DENSE_DIM -u DENSE_DIM_LOW -u DOCUMENT_PREFIX -u QUERY_INSTRUCTION -u QDRANT_HOST
> -u QDRANT_COLLECTION -u DA_ENABLED -u PYTHONPATH .venv/bin/python -m pytest …`). Suite (scrubbed):
> `4 failed / 745 passed / 8 skipped`, 0 new. **Verifier `deleg_04ed319a` (read-only): all 5 claims
> CONFIRMED**, its independently-recomputed per-document counts matching the artifact exactly.
> **NEXT:** **NG-P4** (Visual + Graph tabs), then NG-P5, NG-P6, then **VL-L1**.
>
> **5c. ✅ NG-P4 DONE (2026-11-02) — Visual + Graph tabs; ⬜ NEXT is NG-P5.** Acceptance
> `logs/p1/step10/ng_p4_acceptance.py` → **18/18 PASS**. Graph counts (independently decomposed):
> documents 1 · chunks 3,533 · pages 907 · concepts 6,065 · **edges 47,209** (RELATES_TO 21,670 +
> MENTIONS 14,405 + PART_OF 4,440 + ON_PAGE 3,533 + PREREQUISITE_OF 3,161 — ⚠️ **the runbook's
> "21,670 edges" is RELATES_TO only**). Two store-state findings, both surfaced by the acceptance
> and both **not** tab defects: (a) the visual index returns pages across BOTH documents but
> `data/page_images/` holds PNGs for the **current** doc only, so **2 of 3 cards show "image
> unavailable"**; (b) Memgraph holds **3,533** Chunk nodes vs SQLite's **3,796** (**−263**), with
> `is_content=0` only **5** — the documented recompute-vs-stored-column split. UI wiring proved
> headlessly (`tests/nicegui/test_nicegui_visual_graph_tabs.py`, mutation-proof). ⚠️ **The verifier
> `deleg_bb8ae828` was dispatched with an empty `output_schema`, which collapsed its answer to `{}`** —
> its verdict was read from the transcript (claims 1/2/3/5 CONFIRMED; claim 4 UNVERIFIABLE because it
> could not find the Memgraph container; claim 6 unread). Claim 4 was closed by the author's own
> edge-type decomposition. **Do not pass `output_schema: {}`.** Suite (scrubbed env):
> `4 failed / 745 passed / 9 skipped`, 0 new. **NEXT:** **NG-P5** (Upload, admin), then NG-P6, then
> **VL-L1**.
>
> **6. ⚠️ WORKING TREE.** Nothing in this session is committed; the branch is ahead of origin and
> **nothing is pushed** — owner decision, outstanding.
>
> ## ▶ SESSION 31 — ▶ START HERE. **4A RAN (§I103) and §A LANDED (§I104).**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 31, then `IMPROVEMENTS.md` §I103 (the
> score-fusion run) and §I104 (the per-space query-vector fix). ⚠️ §I103 §6 registers a NEW instrument
> finding: the store's vector-lane query is NONDETERMINISTIC in its low-ranked tail (it is inert at the
> pool, but it is a §I68-class hazard for every run that re-queries lanes per arm). §A unblocks T3 —
> the lane-complete v2-vs-v3 A/B (§I89). Continue the ordered plan: **T3** (the full-funnel v2-vs-v3
> ship test §I85 left unmeasured), then the **pool → top-20 ranking attribution** (§I100/§I103 both
> point there). Pre-register each and commit the pre-registration ALONE first (D6.1)."*
>
> **1. ✅ 4A RAN — read `IMPROVEMENTS.md` §I103.** Artifact `logs/p1/step10/score_fusion.json` (sha256
> `83933c365f6728f0…`), 133 queries, 0 errors, wall 620.3 s, read-only. Pre-registration `32f6c5f` +
> its **pre-run amendment §9** `047e292` (D6.1). Verifier **291 checks PASS**; mutation proof all-hit,
> **no inert check**.
> **THE RESULT:** S1 (min-max) ΔnDCG@20 **−0.0037 [−0.0125, +0.0040]**, S2 (z-score) **−0.0044
> [−0.0138, +0.0040]** — both **UNRESOLVED**, every key ≤ 0.005. ⚠️ **But both RESOLVE NEGATIVE on
> multihop** (S1 −0.0112, S2 −0.0212). Composition changes on **133/133**. ⇒ **§I100's last
> "not measured" item is closed: the score magnitude carries nothing the rank sum does not order, and
> on multihop it costs.** Rank RRF is earning its place.
>
> **2. ⚠️⚠️ §I103 §6 — A NEW INSTRUMENT FINDING, and it is NOT confined to 4A.** The store's
> **vector-lane query is nondeterministic in its low-ranked tail**: 4 identical calls (same query, same
> arm) return **2 distinct lane digests but 1 distinct pool SHA** (`score_fusion_determinism_probe.json`).
> The lane **set** never moves and the fused result is **inert** — but the first run's G3 (a
> digest-equality guard) failed on 5/133, and the guard was **restated** (lane-set identity asserted +
> a G3b inertness control), not weakened. **Any run that re-queries lanes per arm carries this**; the
> determinism guards used so far were at the **metric** level, not the lane level.
>
> **3. ✅ §A LANDED — read `IMPROVEMENTS.md` §I104.** The DA and graph lanes took the **arm's** dense
> vector to a **768-dim** collection, so a **1024-dim arm 400'd and the lane was silently skipped**
> (§I12/§D15, recorded but never fixed). The fix: **one query vector per space**, resolved **off the
> COLLECTION**, with each lane's **TEXT input preserved** (DA = the HyDE hypothetical, graph = the raw
> query) and the model swapped. Probe (`per_space_probe.json`): **A1** 0 → 5 hits on both lanes, 3/3;
> **A2** widths switched, 3/3; **A3** a 768-dim arm is a **bit-exact no-op** (resolver returns the same
> vector object; DA ids identical). Verifier **21 checks PASS**; mutation **21/21 reddened, no inert
> check**. Tests `tests/test_per_space_query_vector.py` (9).
>
> **4. ⚠️ WORKING TREE / COMMITS.** Committed this session: **`e0f1616`** (the accumulated
> uncommitted retrieval-path work, sessions ~18–28 — a session-28-only isolation was impossible, its
> edits share hunks with the §I96 counters and the lane-inclusion work), **`b04e404`** (4A's
> `_score_merge` + `fusion=` + test + the width-stub fix), **`047e292`** (the §9 amendment, alone),
> **`6462145`** (§A's pre-registration, alone). ⚠️ **Sessions 13–27 remain uncommitted; the branch is
> ahead of origin and nothing is pushed — owner decision, outstanding.**
> ⚠️ **Suite: 4 failed / 736 passed / 6 skipped** after the 4A commits (the documented pre-existing
> set, 0 new).
>
> **5. ▶ NEXT, IN ORDER.** **(a) T3** — the lane-complete v2-vs-v3 A/B, now **unblocked by §A** (the
> only controlled test of whether the embedder or the ingestion moved reachability). **(b) The
> pool → top-20 ranking attribution** — §I99, §I100 and §I103 all agree the loss is there. **(c) ⚠️
> Register the lane-tail nondeterminism as its own entry** + add a lane-digest stability control to the
> shared harness. ⚠️ **5B (graded labels) stays DEMOTED** (§I101).

>
> ## ▶ SESSION 30 — ▶ START HERE. **4B RAN (read-only): THE ENDPOINT CUT AS nDCG@k. The cut is MONOTONE and CANNOT move the top-20 — the CE's top-20 is a PREFIX of its top-50 (133/133). It adds recall only; the apparent nDCG gain is a construction artifact (unresolved on the comparable queries).**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 30, then `IMPROVEMENTS.md` §I102 (the
> cut as nDCG@k) and §I101 (the overview-metric diagnosis). The cut is a context-budget knob, not a
> ranking lever. Continue the ordered plan: **4A** (score-based fusion vs rank RRF), then §A (the
> per-space query-vector fix). Pre-register each and commit the pre-registration ALONE first (D6.1), with
> a verifier per stage."*
>
> **1. ✅ WHAT RAN — nothing ran. A READ-ONLY re-derivation** over `t4_endpoint.json` (arm C = CE top-20,
> arm W50 = CE top-50, same pool). Harness `logs/p1/step10/cut_ndcg_k.py` → `cut_ndcg_k.json` (sha256
> `fe297d18981a17e9…`); independent stdlib verifier **33/33 checks PASS**; mutation proof **31 mutations,
> 33/33 checks reddened, NO inert check**. Pre-registration committed ALONE as `df92662` (D6.1).
>
> **2. THE RESULT.** `W50_pages[:20] == C_pages` on **133/133** and the pools are identical ⇒ the cut
> **cannot move any @20 metric** (nDCG@20/R@20/P@20 identical). Paired vs C: **ΔR@k +0.1433 [+0.1126,
> +0.1780] RESOLVED, 77/0/56** — recall is monotone in k; the added gold is **overview 12.05 pages** vs
> factual 1.49 / multihop 0.33. **ΔnDCG@k +0.0233 RESOLVED** — but ⚠️ **a construction artifact**: where
> `n_rel ≤ 20` (88/133) the IDCG denominators are identical, so the delta is non-negative by construction.
> On the **45 comparable queries (`n_rel > 20`) it is UNRESOLVED (−0.0078)**. `P@k` falls (−0.0574) purely
> from the denominator.
>
> **3. ⇒ THE VERDICT: the cut is a CONTEXT-BUDGET knob, not a ranking lever.** It cannot improve the
> top-20 and its only gain is more context. Whether that helps the *answer* is the generator stage
> (unmeasured). ⚠️ **k=100 needs a run** (T4 kept ≤ 50) — a budget question, not a ranking one.
>
> **4. ⚠️ THREE DEVIATIONS, all in §I102.** (a) the comparability split was ADDED after the first run
> (the same-denominator construction is a fact that must be stated to avoid a false positive); (b) a
> **verifier bug found and fixed** — `json.dumps(sort_keys=True)` reorders `by_type` on reload, so the
> bootstrap must rebuild in fixed `TYPES` order; (c) the page-list vs chunk-list convention (§I97 §15):
> nDCG@50 differs from T4's chunk-level value by ≤ 6e-4 on 2/133; R@50 re-derives exactly.
>
> **5. ▶ NEXT, IN ORDER.** **(a) 4A** — score-based fusion vs rank RRF (normalization arms; a new code
> path, declared as a retrieval-path change). **(b) §A** — the per-space query-vector fix. ⚠️ **5B (graded
> labels) stays DEMOTED to optional hygiene** (§I101).
>
> **6. ⚠️ WORKING TREE.** Committed this session: **ONE — the 4B pre-registration ALONE (`df92662`, D6.1).**
> Uncommitted: the 4B harness/verifier/mutation-proof/logs, the artifact, §I102, this block.
>
> ## ▶ SESSION 29 — ✅ 5A RAN (read-only). **THE OVERVIEW-METRIC DIAGNOSIS: the "broken measuring stick" is REFUTED STRUCTURALLY — for overview, RECALL and PRECISION have IDENTICAL capture (0.527), so the broad-label denominator cancels; every query type is RANKER-limited. 5B (graded labels) is HYGIENE, not a fix.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 29, then `IMPROVEMENTS.md` §I101 (the
> overview-metric diagnosis). The overview metric is NOT the constraint (capture ≈ 0.53 on every family,
> all types ranker-limited); 5B is demoted to optional hygiene. Continue the ordered plan: **4B** (widen
> the endpoint cut, measure nDCG@k not just coverage), then **4A** (score-based fusion), then §A.
> Pre-register each and commit the pre-registration ALONE first (D6.1), with a verifier per stage."*
>
> **1. ✅ WHAT RAN — nothing ran. A READ-ONLY re-derivation** over `t4_endpoint.json`, `t0_baseline.json`
> and `fusion_order.json`. Harness `logs/p1/step10/overview_metric_diag.py` → `overview_metric_diag.json`
> (sha256 `a08ed9b92c1c597a…`); independent stdlib verifier `overview_metric_diag_verifier.py` **50/50
> checks PASS**; mutation proof `overview_metric_diag_mutation.py` **50 mutations, 50/50 checks reddened,
> NO inert check**. Pre-registration committed ALONE as `8f6af4f` (D6.1).
>
> **2. THE METHOD.** Per query, put the realised value beside BOTH ceilings — the **LABEL** ceiling (what
> the register already reports) and the **POOL-AWARE** ceiling (the best any ranker could do on the gold
> the pool actually holds). `capture = realised / ceiling_pool` (per-query, averaged within type).
> **`capture >= 0.90` ⇒ metric-limited; `< 0.90` ⇒ ranker-limited** — threshold fixed before the run.
>
> | type | **cap_R** | **cap_P** | **cap_nDCG** | pool_gold ≥ 20 | verdict |
> |---|---|---|---|---|---|
> | factual | 0.673 | 0.673 | 0.509 | 0.08 | ranker-limited |
> | **overview** | **0.527** | **0.527** | **0.548** | **0.80** | **ranker-limited** |
> | multihop | 0.843 | 0.843 | 0.700 | 0.00 | ranker-limited |
> | all 133 | 0.676 | 0.676 | 0.576 | — | ranker-limited |
>
> **3. ⚠️ THE STRUCTURAL FINDING.** For overview, `cap_R == cap_P == 0.527` **exactly** — both ratios
> reduce to `|gold ∩ C| / min(k, pool_gold)`, so the `n_rel` denominator **cancels**. ⇒ **a broad label set
> cannot make recall selectively unfair; recall's capture IS precision's.** The "73.8 pages is too many"
> reading is refuted for the capture question. The pool-aware ceilings are near the label ceilings
> (overview `P_ceil_pool` 0.9688, `nDCG_ceil_pool` 0.9790), and 80 % of overview queries hold ≥ 20 gold
> pages — so ≈0.43 of nDCG@20 is **real recoverable ranking**, not a metric artifact.
>
> **4. ✅ THE MMR SUBSET CHECK (the Q3 question).** MMR fires on **16 of 133** (factual 5, overview 5,
> multihop 6 — **spread across all types**). On those queries `O1 − O0` is **nDCG +0.0030, R@20 +0.0127,
> MRR +0.0037**, mixed by type (nDCG: factual +0.0091, overview +0.0195, multihop −0.0159). ⇒ the
> aggregate null (§I100) is not hiding large opposite-sign per-query effects.
>
> **5. ▶ NEXT, IN ORDER.** **(a) 4B** — widen the endpoint cut (20→50→100) and measure **nDCG@k**, not
> just coverage (T4 measured only the coverage half). **(b) 4A** — score-based fusion vs rank RRF.
> **(c) §A** — the per-space query-vector fix. ⚠️ **5B (graded labels) is DEMOTED to optional hygiene** —
> §I101 shows the metric is not the constraint; do not run it before the retrieval levers.
>
> **6. ⚠️ WORKING TREE.** Committed this session: **ONE — the 5A pre-registration ALONE (`8f6af4f`, D6.1).**
> Uncommitted: the 5A harness/verifier/mutation-proof/logs, the artifact, §I101, this block.
>
> ## ▶ SESSION 28 — ✅ THE FUSION-ORDER RUN RAN. **NO ORDER INTERVENTION MOVES THE ENDPOINT. The pool's ORDER is NOT the lever; removing SPLADE+ColBERT HURTS (RESOLVED NEGATIVE on multihop). §I99's "new #1" is CLOSED and §I89's dilution hypothesis is CONTRADICTED.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 28, then `IMPROVEMENTS.md` §I100 (the
> fusion-order run) and §I99 (the per-type endpoint decomposition). The endpoint's loss is now excluded
> from the lanes, the fusion width/cap/MMR, the fusion's ORDER, and the content filter; the cross-encoder
> is worth 0.005. The next task is **§A, the per-space query-vector fix** — it unblocks the v2-vs-v3
> comparison under the SAME labels, the only controlled test of whether the embedder or the ingestion
> moved reachability. Then treat the overview metric itself as a live suspect. Pre-register and commit
> the pre-registration ALONE first (D6.1), with a verifier per stage."*
>
> **1. ✅ WHAT RAN — nothing ran. This is a READ-ONLY re-derivation over `t4_endpoint.json` and
> `t0_baseline.json`.** Harness `logs/p1/step10/order_waste_decomp.py` → `order_waste_decomp.json`;
> independent stdlib verifier `order_waste_decomp_verifier.py` **42/42 checks PASS** (every cell
> re-derived from the SOURCE per-query arrays, not from the harness's output); mutation proof
> `order_waste_decomp_mutation.py` **42 mutations, 42/42 checks reddened, NO inert check**, every
> mutation reddens its intended check. Log: `order_waste_decomp_mutation_log.txt`.
>
> **2. THE DECOMPOSITION — per type, at the endpoint.** `oracle` = the best any ranker could do on
> the pool the product actually built (an UPPER BOUND). `N` = the pool's own order (no CE). `C` = the
> product.
>
> | type | R_ceil@20 | oracle | N | C | waste_pool | **waste_order** | waste_ce |
> |---|---|---|---|---|---|---|---|
> | factual | 0.9557 | 0.8052 | 0.5830 | 0.5574 | 0.1505 | **0.2222** | 0.0256 |
> | **overview** | 0.3992 | **0.3755** | 0.2103 | 0.1882 | **0.0236** | **0.1652** | 0.0221 |
> | multihop | 1.0000 | 0.6466 | 0.5106 | **0.5500** | 0.3534 | 0.1360 | **−0.0394** |
> | all 133 | 0.8016 | 0.6283 | 0.4491 | 0.4442 | **0.1734** | **0.1791** | **0.0050** |
>
> **3. ⚠️ THE CROSS-ENCODER IS A SMALL PART OF THE LOSS — 0.0050 overall, and it HELPS multihop
> (−0.0394).** T4 was right about the *mechanism* and wrong about the *size*. **⇒ the CE fine-tune is
> PRICED and is NOT the next move: its ceiling is 0.026 factual / 0.022 overview / nothing multihop.**
> Keep it as the last resort with that number attached.
>
> **4. ⚠️ OVERVIEW IS AN ORDERING PROBLEM, NOT A RETRIEVAL PROBLEM — the report's §3 reading is
> corrected.** The pool holds **31.4 labelled pages out of 88.9** — enough to fill all 20 slots — so
> it supports **0.3755 of the 0.3992 ceiling (94 %)** and `waste_pool` is only 0.0236. The loss is
> `waste_order` **0.1652**. The lane answer was closed in §I98; the retrieval answer is closed here.
> ⚠️ Caveat: overview's label sets are broad (mean 73.8 pages, 7.6 % of the corpus), so part of that
> order loss is the metric being unable to reward a reasonable 20-slot answer.
>
> **5. ✅ THE FUSION-ORDER RUN RAN — read `IMPROVEMENTS.md` §I100.** Artifact
> `logs/p1/step10/fusion_order.json`, 133 queries, 0 errors, wall 2,470 s, read-only. Pre-registration
> committed ALONE as `e8dda1a`, its **pre-run amendment §11** ALONE as `c65e4a6` (D6.1). Verifier
> **393/393 PASS**; mutation proof **391 mutations, 393/393 checks reddened, NO inert check**.
>
> **THE RESULT — no order intervention moves the endpoint.** Paired vs O0, n=133, all unresolved except
> one: **O1** (MMR off) +0.0004 nDCG · **O2** (no ColBERT) −0.0012 · **O3** (dense-only) **−0.0182, and
> RESOLVED NEGATIVE on multihop** (nDCG −0.0162, R@20 −0.0264) · **O4** (level-1 weights) −0.0004.
> **⇒ the pool's ORDER is NOT the lever; §I99's "new #1" is CLOSED. Removing SPLADE+ColBERT HURTS, so
> §I89's dilution hypothesis is CONTRADICTED.** Per type, overview nudges UP in every arm
> (+0.0024/+0.0050/+0.0083/+0.0050 nDCG) but **none resolves** — ~20× below what would close
> `waste_order` (0.1652).
>
> **6. ⚠️ FIVE THINGS THIS RUN FIXED OR EXPOSED, all in §I100.**
> (a) **The recorded `G3` flag is MIS-SPECIFIED** — the harness read `mmr_fired` from the arm's own
> call, and O1 has MMR disabled, so it read False 133/133. Re-derived from **O0's** delta, G3 **PASSES**:
> MMR fires on **16 of 133** and O1 differs on **exactly those 16**. Verifier re-derives it; harness fixed.
> (b) **`G5`'s `O4_pool_set_identical_to_O0_everywhere` is an INVARIANCE claim, not a mechanism check** —
> false by construction. Corrected to reported.
> (c) ⚠️ **§2's claim that O4 removes no candidates is WRONG**: O4's pool SET differs from O0's on
> **133/133** (the level-1 fusion is truncated to `limit`), so O4 is not a clean order test.
> (d) **`V4` is not "must be zero"** — 10 multihop queries carry a page-less endpoint candidate from the
> graph lane (`gold-008` on all six arms, the query §I98 flagged). The verifier now separates the metric
> FUNCTION from the AGGREGATION and reports the exclusion.
> (e) **`O0w` is bit-identical to `O0` on 133/133** — the live proof the O4 code change is inert.
> ⚠️ **Deviation, stated:** the mutation proof ran **AFTER** the run, not before as §7 required — the
> checks are population-specific and need a full-shaped artifact. It ran before any number was read.
>
> **7. ▶ NEXT, IN ORDER.** **(a) §A — the per-space query-vector fix.** The last structural lever: it
> unblocks the **v2-vs-v3 comparison under the same labels**, the only controlled test of whether the
> embedder or ingestion changed reachability. **(b) The overview metric is now a live suspect**: its
> label sets are broad (73.8 pages of 968), the pool is 35 % gold, and no ranker — fused, weighted,
> dense-only or cross-encoded — surfaces more than ~51 % of its slots as gold. **(c)** The generator
> stage is still unmeasured.
> ⚠️ **NO ACTION, and now measured so:** the lanes (§I98), the fusion width (§I67), the fusion cap and
> MMR (§I92), **the fusion's ORDER (§I100)**, the content filter (§I71), and the CE fine-tune (priced
> at 0.026 max, §I99).
>
> **8. ✅ THE CONSOLIDATED REPORT — `logs/p1/step10/levers_report.md`.** Every lever with its measured
> effect and verdict, the standing per type, the lanes' disposition, what is NOT measured, and the
> ranked next moves. **85 + 8 quoted numbers re-read out of their artifacts** — 0 mismatches.
> `nomic_gap_report.md` carries a pointer at its head naming the one conclusion this supersedes.
> ⚠️ **Its §4 levers table predates this run — the fusion-order row is now answered (§I100).**
>
> **9. ⚠️ WORKING TREE.** **Committed this session: TWO — the fusion-order pre-registration ALONE
> (`e8dda1a`) and its pre-run amendment ALONE (`c65e4a6`), D6.1.** **Uncommitted:** the O4 code change
> (`store.py` `lane_weights` + `mmr_selections`, `evaluate_rag.py`), the 2 new test files, the 2 fixed
> test stubs, §I99, §I100, `levers_report.md`, the harness/verifier/mutation-proof/log, the
> `nomic_gap_report.md` pointer, and this block.
> ⚠️ **Sessions 13–27 remain uncommitted; the branch is ahead of origin and nothing is pushed — owner
> decision, outstanding.**
> ⚠️ **Suite after the O4 change: 4 failed / 729 passed / 6 skipped — the documented pre-existing set,
> 0 new.** The 6 that were broken in the tree (5 in `test_downstream_widths.py` from the new
> `lane_weights` kwarg, 1 in `test_lane_dropout_counters.py` from **session 27's** `qdrant_point_id`
> fix) are fixed.
>
> ## ▶ SESSION 27 — ▶ START HERE. **S2-S5 RAN: THE RAPTOR LANE IS WIRED, MEASURED, AND A RESOLVED HARM ON OVERVIEW; THE OTHER TWO LANES ARE A NULL AND A CONTENT HARM. NOTHING SHIPS.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 27, then `IMPROVEMENTS.md` §I98 (lane
> inclusion) and §I97 (T4), then the pre-registration
> `.hermes/plans/2026-10-29-p1-lane-inclusion-preregistration.md` — its **§11** is a dated PRE-RUN
> amendment that caught a live defect and three bad guards. Then `IMPROVEMENTS.md` §I92: the pool →
> top-20 ranking step is still the endpoint's binding loss, and §A (the per-space query-vector fix) is
> the next unblocked item."*
>
> **1. ✅ THE LANE-INCLUSION RUN RAN — read `IMPROVEMENTS.md` §I98.** Artifact
> `logs/p1/step10/lane_inclusion.json` sha256 `0f5f5a05e01e9939…`, 133 queries, 0 errors, wall
> 5,220.6 s, read-only. **All 8 harness guards PASS**, **independent stdlib verifier 19/19**, its
> mutation proof reddens **all 14 checks, no inert check**. Pre-registration committed **ALONE** as
> `93146f5` (D6.1).
>
> **2. THE RESULT — three lanes, three answers, none of them a ship.** Six arms, each a single-variable
> contrast against **F0f** (`search_fused(lanes=())`, the vector-only fusion) with **F0** (today's
> wiring) as the product reference. **F3 (RAPTOR):** overview nDCG **−0.0383 RESOLVED**, MAP
> **−0.0148 RESOLVED**, coverage **−0.003028 RESOLVED NEGATIVE** — the two page-less summary
> candidates consume endpoint slots (58 of 133 queries) and push real pages out; factual and multihop
> are **exactly 0.0000 by construction** (the lane is gated to overview). **F1 (DA into the fusion):**
> a **NULL** vs F0 on every metric; precision/F1 RESOLVED-negative vs F0f. **F2 (graph into the
> fusion):** nDCG **−0.0209 RESOLVED**, R@20 **−0.0051 RESOLVED**, precision **−0.0147 RESOLVED** vs
> F0f — and **MRR is NOT recovered**, which the pre-registration named as the finding: the lane's cost
> is **content, not placement**. **F4** (all three) is the worst arm on every ranking metric.
>
> **3. ⚠️ A SECOND INSTRUMENT FINDING: `mrr_at_20` is structurally BLIND to a page-less lane.** F3−F0f
> on `mrr_at_20` is **exactly 0.0, CI [0,0], on all 133 queries** — the zero-width-CI tell. The
> mechanism is in the metric: `_endpoint_mrr` takes the first relevant page's rank over the
> **page-deduped** list, which **drops** page-less candidates and **compresses positions**, so a
> summary inserted above the first relevant page cannot move it. nDCG/MAP *can* see the displacement
> (the page-less candidate still occupies a gains slot) and there the effect is resolved negative.
> **Do not quote `mrr_at_20` for a page-less lane.** Same class as §I95.
>
> **4. ⚠️ THE PRE-RUN AMENDMENT FOUND A LIVE DEFECT — and it is the session's most reusable lesson.**
> `store.search_raptor` returned payload-only dicts (no `chunk_id`, no `qdrant_point_id`), and
> `_rrf_merge` keys on exactly those (§I84) — so **every RAPTOR candidate was silently dropped inside
> `search_fused`** and F3 as registered would have been a copy of its control. **Measured live: 0 of 2
> surviving before the fix, 2 of 2 after.** The unit tests **could not see it** because their fixture
> handed the fusion a `chunk_id` the real lane never produces — *a fixture that is not the live shape
> cannot guard the live path.* Found by a live probe, before the run.
>
> **5. ⚠️ THREE GUARDS WERE WRONG, ALL CORRECTED PRE-RUN (§11c/§11e/§11g), all in the
> over-strict-check class.** (a) the arms REPLACE the composition, so the superset claim against F0
> was false by construction (measured F0 pool 88 vs F3 75) → re-pointed at F0f; (b) the graph lane's
> Cypher has **no stable `ORDER BY`** (pool sizes **90/88/90** across three *identical* calls) → G3 is
> asserted only on the graph-free arms, F2/F4 reported; (c) the cross-day anchor looked broken on a
> 3-query smoke and **matches to +0.0000 on all seven endpoint keys at n=40** — the small-n aggregate
> was the noise, not the harness.
>
> **6. ▶ NEXT, IN ORDER.** **(a) §I92's pool → top-20 ranking step is still the endpoint's binding
> loss** (0.6845 → 0.4553, unattributed since T4 partially attributed it). **(b) §A** the per-space
> query-vector fix — the next *unblocked* item. **(c) The overview type is now doubly blocked:** its
> lane (RAPTOR) makes it worse **as a pool participant**, and R@20 0.1947 against a 0.3992 ceiling is
> still the worst number in the programme — **the next overview idea must not be "add the summaries to
> the pool"**. ⚠️ **NO ACTION:** DA (a null at every placement), the graph lane as wired (a content
> harm at every placement), lane weighting (F4 is worst), the fusion width (§I67).
>
> **7. ⚠️ WORKING TREE.** Committed this session: **only** the pre-registration (`93146f5`, alone, per
> D6.1). **Uncommitted:** the S2/S3/S4 code (`store.py`'s `qdrant_point_id` fix, `evaluate_rag.py`'s
> lane selector), `tests/test_lane_inclusion_eval.py`, the S2 carry-over + its verifier + mutation
> proof, the S5 harness + verifier + mutation proof, the artifacts, `§I98`, and this block.
> ⚠️ **Sessions 13-22 remain uncommitted; the branch is ahead of origin and nothing is pushed —
> owner decision, outstanding.** ⚠️ Session 26's per-type rerank-query policy work has **no handoff
> block** (it is recorded in `logs/p1/step10/policy_confirm_RESULT.md` and the policy
> pre-registration); noted, not reconstructed.
>
> ## ▶ SESSION 25 — ▶ START HERE. **T4 RAN AND ANSWERED IT: THE CROSS-ENCODER IS A NET HARM AT THE ENDPOINT, AND ON FACTUAL QUERIES THE CAUSE IS THE HyDE HYPOTHETICAL BEING USED AS ITS QUERY.** ⚠️ **NOTHING IN `src/` HAS BEEN CHANGED — the fix is attributed, not shipped.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 25, then `IMPROVEMENTS.md` §I97 (T4's
> result) and §I96 (the silent ColBERT lane dropout), then the FINAL report
> `logs/p1/step10/nomic_gap_report.md`. **The next task is the per-type rerank-query policy's
> before/after**: pre-register it, commit the pre-registration ALONE (D6.1), then run it."*
>
> **1. ✅ T4's RESULT (§I97).** Artifact `logs/p1/step10/t4_endpoint.json` sha256 `3db7c697a5bb0fec…`,
> 133/133, **14/14 guards PASS**, verifier **5,852 metric fields re-derived independently**, mutation proof
> 20 checks. **All three registered predictions confirmed:**
> * **P1 — removing the cross-encoder:** nDCG **+0.0560 [+0.0195, +0.0925]**, MAP **+0.0631**, MRR@20
>   **+0.1011** (n=133, all RESOLVED) — and **R@20 and Hit@20 UNCHANGED**. It does not lose pages; it
>   **demotes the right page**.
> * **P2 — the raw query instead of the HyDE hypothetical:** nDCG **+0.0430**, MAP **+0.0561**, MRR
>   **+0.0699** (all RESOLVED) ⇒ **one line at `evaluate_rag.py:206` recovers 77 % of the harm without
>   removing the CE.**
> * **P3 — the 20-slot cut:** coverage **+0.1451 [+0.1125, +0.1777]** RESOLVED. A deliberate context
>   budget — **no action** (§I67).
> * ⚠️ **PER TYPE, and the fix is per type:** **factual** (n=53) N−C nDCG **+0.1361** and Q−C **+0.1397**,
>   both RESOLVED — Q ≈ N, so **the hypothetical is essentially the whole cause**. **multihop** Q ≡ C
>   **EXACTLY, 40/40** (HyDE is not used there — a free internal consistency check). **overview** Q−C is
>   **negative and unresolved**, so the hypothetical is *better* there — **do NOT apply the factual fix to
>   overview.**
>
> **2. ▶ THE NEXT TASK, and it is the largest measured lever in the programme: the per-type rerank-query
> policy's before/after** — raw query for factual, keep the hypothetical for overview, either for multihop.
> Worth **+0.14 nDCG and +0.26 MRR on factual (n=53)** at **zero recall cost**, with **no embedder, index
> or re-ingest change**. ⚠️ **Pre-register it and commit the pre-registration ALONE first (D6.1)** — a
> one-line change to the live pipeline off the back of an attribution run is what D6.1 exists to prevent.
>
> **3. ⚠️ §I96 — A SILENT LANE FAILURE, FOUND BY A GUARD ADDED AT AN INDEPENDENT REVIEWER'S REQUEST.**
> `store._qdrant_search` **catches** a ColBERT query failure, logs an ERROR, and fuses from **dense+SPLADE
> only** — so the POOL is built from a reduced lane set. **There is no counter for it** (unlike
> `reranker.fallbacks`), so nothing outside the log text can see it. It cost T4's first full run G6/G6b on
> one query. **Recommended fix, no re-ingest needed:** a counter beside `_warned_colbert_local`, exposed
> like `reranker.fallbacks`, so run-integrity blocks can assert **lane health per query**.
> ⚠️ **Until then, any pool-dependent number in any artifact — T0 included — may have been taken from a
> reduced lane set.**
>
> **4. ▶ THEN, IN ORDER.** **(a)** §A the per-space query-vector fix → unblocks the cross-index comparison ·
> **(b)** B1/B2 RAPTOR into v3 + wire the overview lane (overview R@20 **0.1882**, ceiling **0.3992**) ·
> **(c)** T2 the lane ablation per type · **(d)** §E2 lane weighting. ⚠️ **NO ACTION:** precision/F1
> (ceiling-bound); the fusion width (§I67); the graph lane as wired (adds pool pages, **lowers MRR**).
>
> **5. ⚠️ THREE THINGS A FUTURE SESSION MUST NOT GET WRONG.** **(a) `coverage` is OURS** — the course uses
> the word for the abstention rate; always write *coverage of a query's reachable labelled pages*.
> **(b) `P-ceil` and `R-ceil` are the COURSE'S** (W7 §3.3, deck slide 25). **(c) Recall has a ceiling too**
> (`min(k,n)/n`) — quoting it bare overstates the overview gap ~3×.
>
> **6. ⚠️ WORKING TREE.** Sessions 13–22 remain **uncommitted**; the branch is **ahead of origin, nothing
> pushed** — **owner decision, outstanding.** Carried: signoff 3, signoff 4, the **A2 `.env` flip**, the
> arm-2 harness, §I56's DA lane, §G2's V5 build, §G5/§I2.
>
> ## ▶ SESSION 24 — ✅ T4 BUILT, INDEPENDENTLY REVIEWED, AND RUN; ⚠️ THE FIRST FULL RUN FAILED FOUR GUARDS (silent ColBERT lane dropout) AND WAS FIXED AND RE-RUN. **THE POOL → TOP-20 STEP IS THE GAP, AND T0 ALREADY SUGGESTS THE CROSS-ENCODER IS A NET HARM THERE.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 24, then
> `.hermes/plans/2026-10-27-p1-endpoint-attribution-preregistration.md` and `IMPROVEMENTS.md` §I89–§I94a,
> then `logs/p1/step10/nomic_gap_report.md` (the FINAL submission report). T4 is pre-registered and
> committed ALONE — RUN IT: `bash logs/p1/step10/run_t4.sh`, then the verifier and the mutation proof."*
>
> **1. ⚠️ THE PLAN-CHANGING FACT, and it is already IN T0's artifact — check it before designing anything.**
> T0's **fusion** row is the pool's OWN order (RRF), and T0's **cross-encoder** row is the CE's order. The
> CE's top-20 is **worse on every metric**: nDCG **0.5506 → 0.4946**, MAP **0.3421 → 0.2789**, MRR
> **0.7687 → 0.6668**, R@20 **0.4491 → 0.4442**. ⇒ **taking the top-20 in the fusion's own order beats the
> cross-encoder's top-20.** The step loses **coverage 0.6845 → 0.4553 (−0.2292)** as well. **Three
> candidate causes, with different fixes, and they have never been separated:** (a) the CE **reorders badly**,
> (b) the **20-slot cut** discards pages, (c) ⚠️ **the CE is fed the HyDE HYPOTHETICAL as its query, not the
> user's question** (`evaluate_rag.py:207` sets `rerank_query = hyp`) — a candidate nobody has tested.
>
> **2. ✅ T4 IS PRE-REGISTERED AND COMMITTED ALONE (D6.1), NOT RUN.** Four arms on one index, T0's lane set,
> HyDE frozen, read-only: **C** the product; **N** no cross-encoder (the pool's own order); **Q** the CE
> reranking against the **raw query** instead of the hypothetical; **W50** the CE with a wider cut. **TWO
> EXACT ANCHORS:** arm C must reproduce T0's `ce` row and **arm N must reproduce T0's `fusion` row** (with
> no CE the top-20 *is* the pool's top-20 — and the pool is page-deduped, so the two conventions coincide).
> **Predictions, registered so they can be falsified: the CE is a net harm (N > C), part of the harm is the
> hypothetical (Q > C), and the cut accounts for the coverage loss (W50 recovers toward 0.6845).**
>
> **3. ▶ THEN, IN ORDER.** **(a)** §A the per-space query-vector fix → unblocks the cross-index comparison ·
> **(b)** B1/B2 RAPTOR into v3 + wire the overview lane (overview R@20 **0.1882**, its ceiling **0.3992** —
> the worst type, and its lane is absent) · **(c)** T2 the lane ablation per type · **(d)** §E2 lane
> weighting. ⚠️ **NO ACTION, and say so:** precision/F1 (ceiling-bound, every type at ~half its ceiling);
> the fusion width (measured inert at the endpoint, §I67); the graph lane as wired (it adds pool pages and
> **lowers MRR 0.781 → 0.667**). ⚠️ **S6 stays PARKED** — the embedder's advantage is +0.0039 unresolved.
>
> **4. ✅ THE FINAL REPORT IS SHIPPED — `logs/p1/step10/nomic_gap_report.md`** (334 lines, committed
> `cd23c10`). Both ceilings (`P-ceil` and `R-ceil`) beside every precision and recall, the per-type split,
> **§7 what is NOT measured**, **§8 the decisions**, and a **provenance block** naming which metrics are the
> course's and which are ours. **137 quoted numbers re-verified against the artifacts — and the check
> caught a real error** (the contents-page label count was 29, not the 21 first written; corrected in
> §I94/§I94a and in §8).
>
> **5. ⚠️ THREE THINGS A FUTURE SESSION MUST NOT GET WRONG.** **(a) `coverage` is OURS**, and the course
> uses the same word for the abstention rate — always write *coverage of a query's reachable labelled
> pages*. **(b) `P-ceil` and `R-ceil` are the COURSE'S** (W7 §3.3, deck slide 25) — quote them, do not
> re-derive them as novel. **(c) Recall has a ceiling too** (`min(k,n)/n`), and quoting a recall without it
> overstates the overview gap ~3× (47 % of achievable, not the 3× the raw 0.188-vs-0.557 implies).
>
> **6. ⚠️ WORKING TREE.** Sessions 13–22 remain **uncommitted**; the branch is **ahead of origin, nothing
> pushed** — **owner decision, outstanding.** Carried: signoff 3, signoff 4, the **A2 `.env` flip**, the
> arm-2 harness (`min_chunk_tokens`, a fragment), §I56's DA lane, §G2's V5 build, §G5/§I2.
>
> ## ▶ SESSION 23 — ✅ T1 RAN (a NULL) AND THE FUSION LOSS IS **ATTRIBUTED**: it is the **100-slot CAP**, and **MMR IS INNOCENT**. ⚠️ **The cap is already known to be inert at the endpoint (§I67), so the next lever is the POOL → TOP-20 RANKING step, not the fusion.**
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 23, then `IMPROVEMENTS.md` §I91, §I92 and
> `logs/p1/step10/nomic_summary_report.md`. The endpoint loss is the pool → top-20 ranking step
> (0.684486 → 0.455330, −0.2292) and it has never been attributed. Pre-register a run that separates
> 'the cross-encoder ranks the right page low' from 'the 20-slot cut discards it' — commit the
> pre-registration ALONE first (D6.1)."*
>
> **1. ✅ T1 RAN — the BASE-LANE ship test on the POOLED index — read `IMPROVEMENTS.md` §I91.** Stage F's
> re-registered instrument **re-run against the index that changed underneath it**; the harness is a
> deliberate **copy** of `stageF_product_endpoint.py` so the only difference between the two runs is the
> treatment. Pre-registration **committed ALONE as `3ab62f7`**; artifact `t1_base_lanes.json`
> (`f84e4b6599ee1f99…`). 133 queries, 0 errors, **all 11 guards pass**.
> **P1 cR@20 +0.003894 [−0.020984, +0.028771] UNRESOLVED**; P2 +0.003805 [−0.020503, +0.028112]
> UNRESOLVED; W/L/T 24/22/87; **the point estimate is ~6× below the run's floor (0.024878)**; power ample
> (n=33 suffices for δ=0.05). **Nothing ships.** ⚠️ **R@100 RESOLVES NEGATIVE −0.018953
> [−0.036938, −0.000969]**, replicating Stage F's −0.0354. **⇒ the chain: +0.104 (base) → +0.090 (cut) →
> −0.019 RESOLVED NEG (fusion) → +0.0039 unresolved (endpoint). The funnel discards the embedder's
> advantage.**
>
> **2. ⚠️ TWO GUARDS MAKE THE NULL MEAN SOMETHING.** **E8** arm A reproduces §3d (0.4475 vs 0.452, gap
> −0.0045, inside ±0.020). **E9 (NEW)** arm A is **BIT-EXACT against Stage F's recorded arm A** — a
> different session — **133/133, 0 mismatches** on six endpoint metrics compared **by name** (the metrics
> added after Stage F are excluded, or it would be an over-strict check). Since arm A shares nothing with
> the treatment, "the treatment is isolated to arm B" is a **measurement**. Diagnostic **D1** (arm B pooled
> − arm B late-chunked at the endpoint) = **+0.004989, UNRESOLVED** — the pooled write that is worth
> **+0.1547 at the base lane** (§I87) is worth **+0.005 at the endpoint**.
>
> **3. ✅ THE FUSION LOSS IS ATTRIBUTED — read `IMPROVEMENTS.md` §I92.** Pre-registration **committed ALONE
> as `e9c3a9f`**; artifact `fusion_attribution.json` (`1a43f2d980183335…`); 133 queries, 0 errors, wall
> 2,629 s, **all nine guards pass including all THREE anchors** (arm C reproduces T0's fusion coverage
> **0.684486** *and* pool mean **86.466165**; `D500_raw` reproduces T0's b5 **0.838136**; the reachable set
> is **identical to T0's**, 888 pages by set equality).
>
> **THE RESULT — one knob.** **The cap (100 → 500, both `mmr_candidates` and `reranker_fetch_k`) lifts pool
> coverage 0.684486 → 0.868024: +0.183538 [+0.151074, +0.216001], RESOLVED, 79 wins to 0 losses.** ⚠️ **MMR
> is INNOCENT and §I89's "leading suspect" is REFUTED:** `C_nommr − C = +0.003178`, **unresolved**
> (6/3/124), and at width 500 **EXACTLY 0.000000, 0/0/133** — because `search_with_das` only calls
> `_mmr_select` when `len(deduped) > reranker_fetch_k` and the deduped pool is ≤ 389 at width 500, so the
> branch is **never taken**. ⚠️ **Predicted from the code BEFORE the run.** Page dedup is innocent too, by
> a **code** argument (it removes duplicate chunks, not pages, so it cannot lower page-level coverage) —
> **not** a measured contrast; no dedup-off flag exists. Two bonus measurements: **HyDE is worth
> +0.037794 [+0.011527, +0.064061], RESOLVED** (the first *isolated* HyDE effect in the register), and
> **fusing three lanes beats the dense lane alone at the same cap** (`C − D100 = +0.053528`, RESOLVED).
>
> **4. ⚠️⚠️ THE PLAN-CHANGING READING.** The cap is recoverable at the pool — and **§I67 already measured
> the SAME width change at the PRODUCT ENDPOINT as a NULL** (+0.0032 / +0.0027, unresolved). ⇒ **a +0.1835
> pool gain buys +0.003 at the endpoint.** **The fusion is NOT the binding constraint on the endpoint**
> (§I89's *"the fusion destroys the arm difference"* is a different claim and still stands). **The endpoint
> loss is the pool → top-20 RANKING step** (T0: **0.684486 → 0.455330, −0.2292**), which has **never been
> attributed** — no run separates *"the cross-encoder ranks the right page low"* from *"the 20-slot cut
> discards it"*. ⚠️ **Do NOT ship the fusion width** — it is measured, cheap and inert at the endpoint.
> ⚠️ **§E1b (the course's canonical MMR) drops to LOW priority** — the suspicion that motivated it is
> refuted.
>
> **5. ✅ BOTH VERIFIERS ARE INDEPENDENT AND MUTATION-PROVED.** `t1_verifier.py` (V1–V9, stdlib-only, reads
> only the written JSON): **9 mutations, each reddens its intended check, every check reddened by at least
> one — no inert check**; **ALL V1–V9 PASS**. `fusion_attribution_verifier.py` (V1–V10): **10 mutations,
> same property**; **ALL V1–V10 PASS**. ⚠️ **A DEVIATION, STATED PLAINLY: T1's mutation proof was run
> AFTER the run, not before it as its pre-registration §9 required.** It does not affect the run or the
> artifact (the verifier is a read-only checker, so mutating copies proves discrimination equally well),
> but it is recorded in the log rather than hidden.
>
> **6. ⚠️ AN INSTRUMENT FINDING WORTH CARRYING.** The **90 s `socket.setdefaulttimeout(90)` did NOT bound
> a hang** — T1's arm A rep 2 stalled **979 s** on one query before the retry raised `timed out` (that
> arm's wall: **1,387.9 s** against ~345 s for the others). The retry worked, so no artifact is affected,
> but the hardening copied from T0 is **not** a bound on the cluster's worst case.
>
> **7. ▶ NEXT, IN ORDER.** **(a) the pool → top-20 ranking attribution (the new #1)** · **(b) §A** the
> per-space query-vector fix (unblocks T3) · **(c) B1/B2** RAPTOR into v3 + wire the overview lane (the
> cheapest item, and it targets the worst type — overview **0.1937** at the endpoint, **0.5221** at the
> pool) · **(d) T2** the lane ablation per type · **(e)** then §E2 lane weighting. ⚠️ **S6 stays PARKED**
> — and the reason is now stronger: the embedder's advantage is +0.0039 unresolved at the endpoint.
>
> **8. ⚠️ WORKING TREE.** Committed this session: **three pre-registration/result commits** — `3ab62f7`
> (T1's pre-registration, alone), `e9c3a9f` (the fusion attribution's pre-registration, alone), and the
> artifacts/docs commit that follows this block. ⚠️ **Everything from sessions 13–22 is STILL
> uncommitted** and the branch is **ahead of origin; nothing pushed** — **owner decision, outstanding.**
>
> **9. ✅ THE PLAIN-LANGUAGE REPORT.** `logs/p1/step10/nomic_summary_report.md` — the nomic story from T0
> through T1 and the attribution, with the funnel table, the ship test, the attribution, what is NOT
> measured, and the ordered next actions.
>
> ## ▶ SESSION 22 — ✅ T0 RAN (10/10 GUARDS + V1–V6 PASS). The funnel loses its pages at the FUSION and the CROSS-ENCODER; the QDRANT ANN dense lane is **IDENTICAL** to exact; the aperture is **INERT** until τ ≈ 0.7
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 22, then
> `.hermes/plans/2026-10-27-p1-t0-baseline-preregistration.md`. Re-run T0:
> `bash logs/p1/step10/run_t0_all.sh` — it re-runs the mutation proof against the current harness
> revision, then the 133-query run, then the verifier."*
>
> **1. ✅ BUILT (all uncommitted).** The pre-registration's §11 deliverables:
> `logs/p1/step10/t0_baseline.py` (the harness — four boundaries, the τ sweep, guards G1–G8),
> `t0_verifier.py` (**V1–V5**, stdlib-only, one verifier per stage, each re-deriving its stage from
> the RAW per-query arrays), `run_t0.sh`, `run_t0_all.sh`, and `t0_mutation_log.txt`. The harness
> smoke-runs clean and reproduces §I89's corpus exactly (**3,489** in-window chunks / **888** pages)
> and the pre-registration's lane set (DA **100** hits, graph **5** hits, v3 **0** RAPTOR nodes).
>
> **2. ✅ THE METRICS §6 ASKED FOR ARE BUILT.** `evaluate_rag.compute_retrieval_metrics` gains
> **`map`**, **`precision_at_k` WITH its ceiling** (`precision_ceiling_at_k`) and **`f1_at_k`** —
> the ceiling travels with the precision because the removed `precision@top_k` sat at its own
> ceiling (W7 §3.3). 3 new tests, **mutation-proved** (ceiling→1.0, MAP denominator→`len(gains)`,
> F1→precision each fail their own test on the assertion). Suite after: **4 failed / 691 passed /
> 6 skipped** — the 4 are the documented pre-existing set, 0 new.
>
> **3. ✅ V1–V5 ARE MUTATION-PROVED — each mutation turns EXACTLY its own stage red** (5-query
> subset; `pass,n_bad`):
>
> | mutation | V1 | V2 | V3 | V4 | V5 |
> |---|---|---|---|---|---|
> | baseline (no mutation) | F,0 *(anchor only)* | F,0 *(anchor only)* | P,0 | P,0 | P,0 |
> | MV1 `cov_base`→0.5 | **F,5** | F,0 | P,0 | P,0 | P,0 |
> | MV2 `cov_cut`→0.5 | F,0 | **F,5** | P,0 | P,0 | P,0 |
> | MV3 fusion gains a phantom page | F,0 | F,0 | **F** | P,0 | P,0 |
> | MV4 `ce_ranked` REVERSED | F,0 | F,0 | P,0 | **F,12** | P,0 |
> | MV5 `admission_uncapped` +1 | F,0 | F,0 | P,0 | P,0 | **F,120** |
>
> ⚠️ **V1/V2 are red in EVERY run including the baseline, and that is expected** — their G3 anchor is
> §I89's **n=133** coverage row (0.918953 / 0.838136), which a subset run cannot reproduce. The
> anchor is orthogonal to the mutation; the discriminator is the stage's own re-derivation count.
> ⚠️ **MV4 is the sharpest**: it changes the ORDER only, not the page set, and V4 still goes red —
> so V4 discriminates on the rank-dependent metrics, not on set membership. Source restored
> byte-identical after every mutation.
>
> **4. ✅ THE RUN LANDED — read `IMPROVEMENTS.md` §I90.** 133 queries, **0 errors**, wall **2,707.8 s**,
> one arm (v3/nomic-768, DA **and** graph **ON** — the product's real lane set), HyDE frozen, read-only.
> **ALL TEN harness guards pass (G1–G10)** and **the independent verifier passes V1–V6**. ⚠️ **G3
> reproduces §I89's arm-B EXACT rows to 4.4e-07 / 5.1e-08** (cov_base **0.918953**, cov_cut
> **0.838136**) — the instrument IS the registered one. Artifact `logs/p1/step10/t0_baseline.json`
> (sha256 `9a5037308c71c02d…`).
>
> **The funnel** (coverage of a query's REACHABLE labelled pages, n=133): base **0.918953** → cut
> **0.838136** → **b5 (the SAME lane through QDRANT) 0.838136** → fusion **0.684486** → cross-encoder
> **0.455330**. **The two real losses are the FUSION (−0.154) and the CROSS-ENCODER (−0.229)** —
> §I89's binding-constraint finding, confirmed at the endpoint.
>
> **5. ⚠️ TWO HEADLINE FINDINGS, both plan-changing.** (a) **The Qdrant ANN dense lane is IDENTICAL to
> the exact computation at L=500** — page overlap **1.000000**, mean score gap **2e-06**, every metric
> equal on every query. So the "exact vs real-world" objection to boundaries 1–2 is, **at this limit,
> empty**. ⚠️ **Scope: L=500** — the product's own dense call uses `limit=100`. (b) **The aperture is
> INERT until τ ≈ 0.7**, because the **K=100 cap** — not a similarity bar — does the cutting: 513 pages
> clear τ=0.0 and **414 still clear τ=0.70** at the base, but only 100 are admitted. **W1 §10.2.1's
> "blind K-NN" critique, measured on our own system.** The knee is between **0.70–0.80** (base) and
> **0.60–0.70** (cut). ⚠️ **No τ is committed** — the curve is the result.
>
> **6. ⚠️ THE MUTATION PROOF IS NOW V1–V6, 7 MUTATIONS** (`logs/p1/step10/t0_mutation_log.txt`): each
> mutation turns **exactly** its own stage red; **MV5** reddens **both** V5 and V6; **MV7** isolates the
> V4 extension. ⚠️ **RUNNING THE VERIFIER ON THE FULL ARTIFACT FOUND THREE OVER-STRICT CHECKS, all
> false positives on correct data, all fixed and recorded** — V6's `recall_at_100` used the top-100
> pages where the harness uses the POOL recall (gold-004: 0.0 vs 0.6667); V3 asserted `da_live ==
> n_queries` (the DA lane was live on **132/133**, which G6 permits); V4 flagged a MAP "mismatch" on
> `gold-033` that is the **rounding boundary** (0.05625 vs 0.0563 — 1.4e-18 above a 5e-5 tolerance).
> ⚠️ **An over-strict check is worse than no check: it gets switched off.**
>
> **7. ⚠️ WORKING TREE.** Everything above is **uncommitted**; **nothing pushed**. ⚠️ **The
> re-registration and the pre-registration are both uncommitted** — D6.1 wants the pre-registration
> committed ALONE before the run, and the run has now happened; **owner to decide.** ⚠️ A stray file
> `unused` (4,235 B) sits in the repo root — written by an accidental tool call, deliberately **not**
> deleted (destructive actions need an explicit ask).
>
> **8. ▶ NEXT.** T1 (v2-vs-v3 base lanes), T2 (nomic-only lane ablation, per type), T3 (v2-vs-v3 all
> lanes — **needs §A's per-space query-vector fix**), then §E's fusion attribution. ⚠️ **The overview
> type is the loss at the endpoint (coverage 0.1937)** and its lane (RAPTOR) is absent from v3 and off
> the eval path — B1/B2 are the cheapest next move.
>
> ## ▶ SESSION 21 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 21, then
> `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md` and `IMPROVEMENTS.md` §I89. I am
> starting with task A — the per-space query-vector fix that lets a 1024-dim arm query the 768-dim
> derived lanes — then RAPTOR into v3 + wiring the overview lane, then the three measurement tracks,
> then the fusion attribution. Pre-register each run and commit the pre-registration ALONE first."*
>
> **1. ✅ THE POOLED RE-EMBED LANDED — read `IMPROVEMENTS.md` §I89.** §I88 resolved H1 (nomic's
> late-chunk path is **faithful**, cos 1.000000 to an independent span-pooling), so the 0.155 loss is a
> **METHOD** choice and the treatment is to drop late chunking. New Shape B mode
> (`scripts/reembed_chunks.py --from-collection knowledge_base_v2 --pooled` +
> `LateChunkEmbedder.embed_isolated_batch`): **3,796 pts / 341 parents / 0 failures / 91.9 s**, point
> ids + `chunk_id` set **byte-identical**, `colbert`/`sparse`/payloads carried over **unchanged**,
> `knowledge_base_v2` **untouched (3,869)**. **Acceptance:** cos(stored, a FRESH pooled embedding)
> **0.804564 → 1.000000**, and v3's coverage now reproduces §I87's `nomic_pooled` row at **every L**
> (0.591316 / 0.843325 / 0.933638 / 0.978649). ⚠️ A guard was mis-specified on the first draft (3,796
> collection points vs **3,489** in the content window) and is split and recorded — §I71/§I72's
> population-naming class.
>
> **2. ✅ STAGE G RE-RAN — 8/8 guards, two of them NEW and load-bearing.** Pre-registration
> (`.hermes/plans/2026-10-26-p1-stageG-rerun-preregistration.md`) **committed ALONE as `3d3026e`**
> before the run. **G7** arm B's gap row reproduces §I87's pooled row (gap **0.000000**); **G8** arm A
> is **bit-exact** against §I86's arm-A rows (all five gaps **0.000000000**) — the strongest control,
> because arm A shares nothing with the treatment. Artifact `stageG_decomposition.json`
> (`8a2fd64b317f2d22…`); §I86's artifacts preserved as `stageG_*_session20_latechunked.json`.
>
> **3. THE RESULT — and it inverts §I86.** Coverage of reachable pages, paired **B − A**, n=133:
> **base +0.103817 RESOLVED** (67/8/58) · **cut +0.090373 RESOLVED** (60/19/54) ·
> **fusion −0.019129 RESOLVED NEGATIVE** (17/38/78) · **cross-encoder +0.003709 unresolved** (24/22/87).
> B's coverage falls **0.838 → 0.641** across the fusion while A's falls 0.748 → 0.660. **The pooled
> index's advantage is large and real upstream and is destroyed at the fusion** — which is exactly why
> Stage F saw a null at the endpoint. ⚠️ Mechanism stated as consistent-with, not proven: sparse and
> ColBERT are **model-independent**, so RRF dilutes the better dense lane. **The RRF / dedup / MMR split
> is UNATTRIBUTED, and MMR is the leading suspect** (it penalises "redundancy", and a page with many
> relevant chunks looks like redundancy while the metric is page-level). ⚠️ Not like-for-like: arm A is
> qwen3 late-chunked, arm B is nomic pooled — the like-for-like contrast is §I87's (+0.0362).
>
> **4. ⚠️ THREE NEW FINDINGS, all plan-changing.** (a) **The fusion is the binding constraint** — not the
> embedder, not the ingestion ⇒ **S6 is aimed at the wrong stage**. (b) **A lane-complete v2-vs-v3 A/B is
> blocked by a DEFECT, not physics**: `store.search_da` and `graph_builder._find_concepts_scored` send
> the **arm's** dense vector to a 768-dim collection, so a 1024-dim arm 400s and the lane is **silently
> skipped** (§D15/§I12). The fix is **one query vector per space**. ⚠️ Production is 768-dim, so
> **production is unaffected** — it is the v2/1024 *arm* that is broken. (c) **The overview (RAPTOR) lane
> has NEVER been on the eval path** (`evaluate_rag.py` never calls `search_raptor`; the only caller is
> `streamlit_app.py:589`), and v3 has **0** RAPTOR nodes vs v2's 73. ⚠️ Also: the **visual lane cannot be
> measured** — `visual_knowledge_base` holds 1,033 points for the **old** doc `6d55c52b` only, and the
> **33 visual queries carry no labels** (hence 133 gold queries, not 166).
>
> **5. ▶ NEXT SESSION — THE ORDERED TASKS, in `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md`.**
> **(A)** the per-space query-vector fix (small, product-path; guard A3 = **arm B must stay bit-exact**,
> since its vector already is nomic's — the discriminating control) · **(B)** RAPTOR into v3 (a write,
> 3,796 → 3,869) **+ wire `search_raptor` into `evaluate_rag`** · **(C)** add **MRR/nDCG** to the stage
> ladder (gate on the reranked-metrics-valid flag — the reranker swallows failures and returns the pool
> UNRANKED, §I55) · **(D)** three tracks: **T1** v2-vs-v3 base lanes (the narrowed ship test) · **T2**
> nomic-only lane ablation, per type · **T3** v2-vs-v3 **all lanes** (the full-funnel ship test §I85 left
> unmeasured) · **(E)** THEN the **fusion attribution** (RRF vs dedup vs MMR), then lane weighting, then
> the width sweep, then the fix — validated at the pool **and** the endpoint. ⚠️ Per-type floor is
> **~0.04** at n=40, double the n=133 floor. ⚠️ The lanes will not rescue the endpoint: DA is a measured
> **harm** (−0.0262), and the graph lane **bypasses the fusion** (appended after `search_with_das`).
>
> **6. ⚠️ WORKING TREE.** Committed this session: **only** the Stage G pre-registration (`3d3026e`). The
> pooled-write code (`reembed_chunks.py`, `late_chunk_embedder.py`, its tests), the acceptance + carry-over
> probes, the Stage G harness/artifacts, `§I89`, the plan, `DECISIONS.md`, and the report are
> **uncommitted**. Branch ahead of origin; **nothing pushed**.
>
> **7. ✅ ALSO BUILT (uncommitted).** `logs/p1/step10/stageG_findings_report.{md,pdf}` — the plain-language
> write-up of the Stage G re-run plus the three design questions (cross-encoder fine-tune, the fusion
> loss, recall-vs-rank metrics). 11 pages, generated with fpdf2.
>
> ## ▶ SESSION 20 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **1. ✅ STAGE F RAN — read `IMPROVEMENTS.md` §I85.** The ONE product-endpoint run: **arm A =
> `knowledge_base_v2` / Qwen3-1024 (control)**, **arm B = `knowledge_base_v3` / nomic-768 (treatment)**,
> 133 gold queries, **HyDE ON and frozen** (§I73 cache, 93 served; a miss raises). Each arm calls the
> **product's own `evaluate_rag.run_retrieval`** + `compute_retrieval_metrics`; 133 queries / 0 errors /
> ~150 s per arm; each arm run **twice**.
>
> **2. THE RESULT — a NULL, and the one resolved secondary is negative.** Paired **B − A**:
> **P1 cR@20 −0.001213** CI [−0.023051, **+0.020626**] **UNRESOLVED**; **P2 raw R@20 −0.001185** CI
> [−0.022523, +0.020153] **UNRESOLVED**; W/L/T 21/26/86; `SD_d` 0.1285 → floor **0.021839** (the effect
> is **~18× below** the floor; power ample, n=133). **R@100 RESOLVED −0.0354** [−0.0517, −0.0191] —
> nomic's fused pool covers ~3.5 pp fewer pages. Every per-type cut unresolved. **⇒ nothing ships.**
>
> **3. ⚠️ THE HEADLINE IS THE MECHANISM.** §I63's oracle measured **nomic − qwen3 = +0.1400** R@20 on
> the base lane; §I74 measured **+0.068** at the cross-encoder on an oracle pool. At the **product**
> endpoint it is **−0.0012, unresolved**. Structural, and consistent with §I72/§I74: the **sparse +
> ColBERT lanes are model-independent** (identical in both arms → they dilute the dense difference),
> and the **cross-encoder is a strong equaliser**. **The oracle gain does not survive the funnel.**
>
> **4. ⚠️ THE PRE-REGISTRATION COULD NOT BE RUN AS WRITTEN — the whole DERIVED layer is nomic-only.**
> `search_da` (`store.py:722`) queries `derivative_artifacts` with the **DENSE** query vector, whose dim
> **IS the arm's `dense_dim`** — and §I83 re-created that collection at **768d**. So arm A's DA lane
> **400s and is SILENTLY skipped** (`store.py:748`) while arm B's is live — **not a single-variable
> A/B**, and arm A can no longer reproduce Phase E. ⚠️ **§D15/§I12 recorded the SAME 768-vs-1024 DA
> death in the §3d run.** The **graph lane** fails identically (`concept_embeddings` is 768d too;
> `graph_builder.py:686` returns `[]` — no LLM, so an asymmetry, not noise).
>
> **5. ⇒ RE-REGISTERED, COMMITTED ALONE BEFORE THE RUN** (`e708784`, amended `a409d7d`;
> `.hermes/plans/2026-10-25-p1-stageF-product-endpoint-reregistration.md`): **(a)** DA lane **OFF both
> arms**, **(b)** **E8 re-pointed to §3d** (the registered DA-off v2 row, R@20 **0.452**; tolerance =
> the ±0.020 floor, **not a fit**), **(c)** **graph lane OFF both arms**. ⚠️ **The question NARROWED to
> the base lanes** (`dense + sparse + colbert → RRF → dedup → MMR → cross-encoder`) — **stated, not
> hidden.** The full-funnel comparison is **unmeasured**.
>
> **6. ✅ ALL TEN GUARDS PASS — the load-bearing two are the strongest.** **E8:** arm A reproduces §3d —
> R@20 **0.4475** vs **0.452** (gap **−0.0045**, inside ±0.020), so the harness **IS** the registered
> instrument. **E4:** each arm run twice is **bit-exact on every metric of every query** — legitimate
> only because **§I68 landed**. Plus E1/E2/E3/E5/E6/E7 + DA-off + divisor-identical. **A DA-gap
> cross-check** holds: arm A DA-off 0.4475 vs Phase E DA-on 0.4250 → **+0.0225**, close to §I56's
> **−0.0262**. **Independent stdlib verifier `stageF_verifier.py --check`: V1–V8 ALL PASS.**
>
> **7. ⚠️ A CONVENTION PINNED.** The §I58 divisor (`mean(achievable_max)`) measured **0.97707 in BOTH
> arms** (identical by construction) ⇒ **P1 = P2 / 0.97707** — the two primaries are the **same test up
> to scale**, and the divisor **cannot** change the sign/CI/verdict. ⚠️ It differs from §I58's
> registered 0.9545 (different instrument) — recorded, immaterial. ⚠️ **Not** §I84's `cr20` (≈4.44,
> a per-query top-k-slot convention).
>
> **8. ✅ STAGE G ALSO RAN — read `IMPROVEMENTS.md` §I86.** The §I66 stage decomposition on BOTH arms
> (base → full-dim cut → fusion → cross-encoder), same config as F, **all guards pass and the
> KNOWN-ANSWER CHECK IS EXACT** (arm A reproduces §I66's rows: 0.815136 vs 0.8151; 0.747763 vs 0.7478).
> ⚠️ **It REFUTES this session's own hypothesis.** Every stage is **≤ 0 for nomic** — base **−0.0152**
> (unresolved), cut **−0.0556** (unresolved, near), **fusion −0.0358 RESOLVED −**, cross-encoder
> **−0.0012** (unresolved). So there is **no base-lane advantage to destroy**; the only resolved stage
> is the **fused pool**, and the **cross-encoder absorbs it** (§I72 reproduced on the real funnel).
> ⚠️ **THEN THE GAP ROW WAS MEASURED, AND IT INVERTS §I63.** Full-dim over all 3,489 chunks, **no
> prefilter** (§I63's own configuration; reproduces §I66's grid exactly, guard G6): **v3 is WORSE than
> v2 at every L** — L=500 **0.8286 vs 0.6887, Δ −0.1399 RESOLVED**. **Opposite sign to §I63's
> `nomic +0.1400`, same magnitude.** ⚠️ **The cause is source-read, not inferred:** §I63's nomic arm
> embedded **POOLED** vectors (`cross_embedder_experiment.py:295`) while arm Q used **stored** ones
> (`:265/:329`) — and v3 stores **late-chunked** vectors. Measured: stored-vs-pooled cosine v2
> **0.9559**, v3 **0.8153**. **⇒ the oracle's +0.14 was never about the index we built.** ⚠️ **New cheap
> open question:** pooled nomic scored well, late-chunked nomic scores worse than qwen3 — **consistent
> with late chunking (E3) being the cause, but NOT isolated.** If so the lever is the **ingestion**.
>
> **8b. ⚠️⚠️ THEN THE ISOLATION RAN — AND LATE CHUNKING IS THE CAUSE. Read `IMPROVEMENTS.md` §I87.**
> **FOUR arms** (both pooled arms added — the first run was asymmetric: only nomic was pooled), one
> instrument, all guards pass (anchored exactly to §I86). **Full-dim, no prefilter, L=500: qwen3
> late-chunked 0.8286 · qwen3 pooled 0.8071 · `nomic_pooled` 0.8433 · nomic late-chunked (v3) 0.6887.**
> The four paired contrasts: **nomic pooled − nomic late-chunked +0.1547 RESOLVED** · **qwen3 pooled −
> qwen3 late-chunked −0.0215 UNRESOLVED (≈neutral)** · **nomic pooled − qwen3 pooled +0.0362 RESOLVED
> (like-for-like, nomic WINS)** · nomic late-chunked − qwen3 late-chunked −0.1399 RESOLVED. ⇒ ⚠️ **THE
> SIGN FLIP IS AN INTERACTION — late chunking × nomic** — and **the lever is the INGESTION, not the
> embedder.** ⚠️ **The interaction points at H2, not H1:** if late chunking were simply bad it would
> hurt qwen3 too — it does not. **H2 = the nomic late-chunk path MIS-POOLS (a defect)**; the tell is
> stored-vs-pooled cosine **v2 0.9559 vs v3 0.8153 (min 0.502)**. ⚠️ **§I80/§I81 verified the alignment
> COUNT and a QWEN3 reproduction — never that a nomic child equals a manual span-pooling. A count is not
> a span.** That check does not exist; it is the cheap discriminating test.
>
> **9. ▶ NEXT, IN ORDER.** (a) ⚠️ **RE-TARGET S6.** The fine-tune is aimed at the **embedder**, but the
> measured lever is the **ingestion** (§I87) — fine-tuning then late-chunking would run the gain through
> the same 0.155 loss. **The cheap discriminating test first:** does a nomic child's late-chunked vector
> equal a manual pooling of the parent's token vectors over that child's span? (**H1 vs H2**, ~10 min,
> read-only). **Signoff 6 (passage-level split) is TAKEN.** (b) **The full-funnel question** — needs a
> **1024d `derivative_artifacts` AND a 1024d `concept_embeddings`** (both a write). (c) ✅ **Reviewer
> `deleg_e607dda1`** (`openai/gpt-oss-20b`, cross-family, read-only, on a 34 KB compact extract)
> **RETURNED: 7/7 CONFIRMED, no refutations** — it independently re-derived the means, Δ, CI, W/L/T and
> the R@100 row (matching to the last digit). ⚠️ **NOT BANKED** (4 API calls, 71 s — a cheap verdict);
> the substantive half is the ten guards + E4/E8 + the stdlib verifier. ⚠️ Still carried: **signoff 4** (accept §I79),
> **signoff 3** (re-confirm Shape B), the **A2 `.env` flip**, the **arm-2 harness** (§I56's DA lane),
> §G2's V5 build, §G5/§I2.
>
> **10. ⚠️ WORKING TREE.** Two docs commits this session (`e708784`, `a409d7d`, the re-registration
> alone before the run). The Stage F harness + verifier + the five artifacts + this block are
> **uncommitted**. Branch **ahead of origin; nothing pushed.**
>
> ## ▶ SESSION 19 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 19, then the Stage F pre-registration
> (`.hermes/plans/2026-10-25-p1-stageF-product-endpoint-preregistration.md`) and `IMPROVEMENTS.md`
> §I84. I am running Stage F: the ONE product-endpoint run, nomic/v3 vs qwen3/v2, 133 queries, HyDE ON
> and frozen. Assert the per-arm env first, retrieval-only, and the full synthesis+judge run only if
> the retrieval endpoint resolves."*
>
> **1. ✅ §I68 IS LANDED AND COMMITTED (`939beae`) — read `IMPROVEMENTS.md` §I84.** The funnel no longer
> uses Qdrant's server-side `FusionQuery`; it issues **one `query_points` per lane** and fuses
> client-side with `store._rrf_merge(..., rrf_k=1)`. ⚠️ **`rrf_k=1` is MEASURED, not chosen** — the
> live server's RRF is exactly `Σ_lanes 1/(1+rank)` (probed; `_rrf_merge`'s own default is 60 and would
> have rescaled every score ~60×). The fused result is returned in the `.points[i].score/.id/.payload`
> shape `search()` reads, so **`search()` is unchanged**.
>
> **2. ✅ THE SWAP IS ENDPOINT-IDENTICAL.** Before/after harness `logs/p1/step10/i68_rrf_swap_ab.{py,json}`
> (sha256 `6609a64e…`), 133 queries, HyDE off, **5/5 guards pass**: determinism fixed (before 2/6, 6/6,
> 6/6, 4/6 distinct → **after 1/6 on all four**), and **R@20 `0.41049414968626663` in BOTH arms — Δ 0.0,
> CI [0,0], W/L/T 0/0/133**. ⚠️ The artifact is **NOT byte-reproducible** (one arm IS the
> nondeterministic one), so the BEFORE-derived counts wobble between runs; the **endpoint fields are
> identical to the last digit** — quote those, never the wobble counts.
>
> **3. ⚠️ TWO REAL DEFECTS WERE FOUND BY RUNNING IT (not by review), both fixed.** (a) `_rrf_merge`
> keyed on `chunk_id` alone and **silently DROPPED** the 73 `raptor_summary` nodes, which carry none,
> while Qdrant keyed on the point id and kept them — fixed with a `qdrant_point_id` fallback (the
> product was masked by `search()`'s `_NOT_RAPTOR` filter, the only reason it was not a live recall
> loss). (b) The harness's filter omitted `_NOT_RAPTOR`/`is_content`, so it compared on a pool the
> product never sees — **that was the whole of a spurious +0.0040 delta**, which became 0.0 once fixed.
>
> **4. ⚠️ BLAST RADIUS CORRECTED: THREE test files break by construction, not the two §I68 §4a
> recorded** — `test_lane_resolution.py` was missed. All three are rewritten to the new call shape;
> mutation-proved (reverting the mechanism fails **16** tests, all on `AssertionError`, 0
> collection/syntax errors). `scripts/funnel_boundary_recall.py` moved **with** the product (it claims
> to mirror `_qdrant_search` exactly); `scripts/why_colbert.py` is deliberately left as a one-off.
> Suite **685 passed / 4 failed / 6 skipped**; the 4 are the documented pre-existing set, **proved** by
> stashing `store.py` to HEAD. ruff: 39 errors, **all pre-existing (0 introduced)**.
>
> **5. ✅ STAGE F'S PRE-REGISTRATION IS WRITTEN AND COMMITTED ALONE (`51de3f2`)** — the file named in
> the opening prompt. Arms **A = v2/Qwen3-1024 (control)**, **B = v3/nomic-768 (treatment)**; HyDE ON
> and frozen via `data/hyde_cache/` (the existing file resolves — `OPENAI_MODEL=openai/gpt-oss-20b`,
> queries digest `18ece9b9404688c8`, prompt digest `ab681b8e43855a46`; a miss RAISES, never a live LLM
> call); endpoint **P1 paired ceiling-normalised R@20**, ⚠️ **product convention = pages of the top-k
> CHUNKS** (§I72's VOID was exactly this confusion); 8 guards, **E4** (bit-exact negative control — now
> legitimate because §I68 landed) and **E8** (arm A must reproduce a §I64/§I57 row, or the harness is
> not the product path) are load-bearing. ⚠️ The intent router is **not** on the eval path, so the
> classifier's dimension does not confound the arms.
>
> **6. ⚠️ THE DIFF VERDICT, AND WHY `[verified]` IS OFF.** Reviewer `deleg_dc2675b3`
> (`openai/gpt-oss-20b`, read-only, cross-family) returned **7/7 CONFIRMED, no silent wrong answer** —
> but it is a **CHEAP verdict (19 calls, 33.6 s) whose cited line numbers do not resolve**, so it is
> **not banked**. The substantive half is the author's mechanical evidence: the live determinism
> measurement, ΔR@20 = 0.0, the two mutation proofs, the suite. `939beae`'s body says exactly this.
>
> **7. ▶ NEXT, IN ORDER.** (a) **Stage F, retrieval-only** — assert the per-arm env (pre-registration
> §3: `DENSE_MODEL`/`DENSE_DIM`/`DENSE_DIM_LOW`/`QUERY_INSTRUCTION`/`DOCUMENT_PREFIX` + `QDRANT_HOST` +
> `QDRANT_COLLECTION`) and run it; the full synthesis+judge run (**~70 min, 5,434 judge calls**) only
> if the retrieval endpoint resolves. (b) **Stage G** — the §I66 stage decomposition, alongside it.
> (c) Then **S6, the fine-tune** (signoff 6 open). ⚠️ Still carried: **signoff 4** (accept §I79's
> measurement), **signoff 3** (re-confirm Shape B), the **A2 `.env` flip** (owner action, still open),
> the **arm-2 harness** — the two untracked `min_chunk_tokens_ab*.py` are a **fragment** and arm 2 is
> **NOT built** — §I56's DA lane, §G2's V5 build, §G5/§I2.
>
> **8. ⚠️ WORKING TREE.** Everything above is committed (`51de3f2`, `939beae`, `9b7920a`); the branch is
> **ahead of origin and nothing is pushed**. The only untracked files are the arm-2 fragment, left out
> deliberately.
>
> ## ▶ SESSION 18 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **▶ NEXT SESSION'S OPENING PROMPT:** *"Read HANDOFF.md session 18 (items 15–16 especially), then the
> nomic plan's §3 Stage F/G and §7 signoffs, then `IMPROVEMENTS.md` §I68. I am starting S5: land the
> §I68 client-side-RRF fix first, then pre-register the ONE product-endpoint run (nomic/v3 vs
> qwen3/v2, HyDE ON and frozen) and COMMIT THE PRE-REGISTRATION ALONE before running it."*
> ⚠️ **The A2 `.env` flip is still NOT applied** — every stage so far has run on env exports
> (`DENSE_MODEL`/`DENSE_DIM`/`DENSE_DIM_LOW`/`QUERY_INSTRUCTION`/`DOCUMENT_PREFIX` + `QDRANT_HOST`
> `QDRANT_COLLECTION`); forget them and the run silently uses Qwen3/1024. **Owner action, still open.**
>
> **1. ✅ S1 (Stage A2 + A2b) IS FINISHED AND GREEN — but session 17's end left it UNCOMMITTED and RED,
> and neither the handoff nor `IMPROVEMENTS.md` recorded it.** Full entry: `IMPROVEMENTS.md` **§I78**.
> One line: the code for the document-side prefix, the span shift and the model-aware special-token
> layout was in the tree; the suite was RED — **20 failed / 661 passed**, i.e. **16 NEW failures** on
> top of the 4 documented pre-existing ones; nothing was committed.
>
> **2. ⚠️ THE FINDING THAT MATTERS — the special-token layout was resolved from a GLOBAL flag, not the
> embedder in use.** `LateChunkEmbedder` read `cfg.use_stub_embedder` (True across the whole test
> suite) to decide the endpoint's layout, so it assumed `(0, 0)` while the tests' mock endpoint
> returned `n_local + 1` vectors — a count mismatch that raised in **14 tests**. Fixed to
> `isinstance(self._embedder, StubClusterEmbedder)`; **behaviour-preserving in production** (the
> factory returns a stub exactly when the flag is True), so it is a contract fix, not a test
> accommodation. The other 2 new failures were the `dense_128 → dense_64` rename in stale tests.
>
> **3. ✅ THE TWO A2b GUARDS THE BUILD WAS MISSING ARE NOW BUILT** (S1's definition of done requires
> them): **span invariance** (trap 2 — a prefix must not move a child's pooled tokens) and
> **prefix-on-payload for BOTH passage paths** (trap 1), plus model-aware `_DECLARED_SPECIALS` tests.
> ⚠️ The test helper `_token_vector` was made **position-independent** first, or the span guard would
> have failed for the wrong reason.
>
> **4. ✅ THE ALIGNMENT RULE IS PROBED, NOT ASSUMED (trap 3).** `probe_nomic_alignment.json`: nomic =
> **0 leading + 2 trailing** (margin **7.87×**), Qwen3 = **0 + 1**. Declared in `_DECLARED_SPECIALS`;
> `declared_specials` RAISES for an unknown model. The BERT-style `(1,1)` guess was **wrong**.
>
> **5. ✅ SIGNOFF 4 (the MRL convention) IS MEASURED — a NULL: KEEP the project's plain slice.**
> `mrl_convention_ab` (all 6 guards pass): `layer_norm`-then-slice vs plain slice, Δ **+0.000314**, CI
> [−0.0035, +0.0042] straddles 0 and sits **below the run's floor (0.003853)** ⇒ **§I59's rows stand,
> no re-measurement.** ⚠️ It was OPEN and gated S3; it no longer does — **owner to accept the
> measurement.** Entry: §I79.
>
> **6. ✅ MUTATION-PROVEN.** 6 of 7 mutations make their guard fail; the one that does not (**M5**) is a
> **no-op mutation**, replaced by M5b which discriminates — recorded in
> `logs/p1/step10/s1_a2b_mutation_log.txt`, and **caught independently** by a read-only reviewer. Both
> source files restored byte-identical. Suite after: **4 failed / 683 passed / 6 skipped** (the 4 are
> the documented pre-existing set, **proved** by stashing the src changes and re-running).
>
> **7. ⚠️ REVIEWERS: three dispatches, and only the mechanical evidence is banked.** (a) the multi-turn
> reviewer **DIED on this gateway** (`unexpected tokens remaining in message header:
> Some("to=functions.read_file")`) — **no verdict, not a pass**; a mis-scoped child answered
> all-UNVERIFIED with fabricated risks. (b) the compact single-turn reviewer returned **8/8 CONFIRMED,
> no refutations — cheap (10 calls / 25 s), NOT banked**. (c) the mutation-check reviewer returned
> **5 CONFIRMED / 1 REFUTED (M5)** — the refutation was **VALID** and is why the log was reconciled.
>
> **8. ✅ S1 IS COMMITTED** (4 commits: `ff2651f` feat, `5f1c0c2`/`87d3221` logs, `e97f165` docs). The
> only untracked files are the **arm-2 fragment** (`min_chunk_tokens_ab*.py`) — deliberately left out,
> it is the known-broken fragment the brief says to treat as **arm 2 unstarted**.
>
> **9. ✅ S2 IS LANDED — read `IMPROVEMENTS.md` §I80.** `knowledge_base_v3` was dropped (it held the
> gemma shape, 0 points) and re-created through the project's own bootstrap with the §2 schema —
> verified by an **INDEPENDENT** live read-back (fresh client, §I33): `dense_64` 64 + `dense_full` 768
> + `colbert` 128 + `sparse`, **0 points**; **v2 untouched (3,869)**. ⚠️ `verify_collection_lanes.py`
> exits 2 on an EMPTY collection — it is the **S3** gate, not S2's.
>
> **10. ✅ C0 PASSES UNDER NOMIC — ~7.0 min, NOT the derived ~48 min.** 20/20 parents, 0 failed, all
> four guards True; the corpus reproduced exactly (341 parents / 3,796 children / 11.132 per parent);
> mean **1.232 s/parent**, p90 4.467. ⚠️ **C0-G2 confirms the `(0,2)` alignment declaration against
> the LIVE endpoint** — trap 3 closed end-to-end. ⚠️ **Signoff 3 (Shape B) is now at its confirmation
> point — owner to re-confirm** (the measured number is far under budget; Shape A is not cheaper).
>
> **11. ⚠️ TWO OWNER ACTIONS, BOTH §I44's CLASS, RECORDED IN §I80.** (a) **The A2 `.env` flip is
> still NOT applied** — S2 ran on **env overrides**. ⚠️ Every stage must export
> `DENSE_MODEL`/`DENSE_DIM`/`DENSE_DIM_LOW`/`QUERY_INSTRUCTION`/`DOCUMENT_PREFIX` (or the `.env` flip
> must land, which the plan wants anyway for Stage F's per-arm switching) or it will **silently run
> Qwen3/1024**. (b) The C0 probe writes to a **fixed path** and overwrote the gemma FAILED artifact
> (preserved as `c0_gemma_late_chunk_timing_FAILED.json`); the probe needs an `--out` argument.
>
> **12. ✅ S3 IS DONE — read `IMPROVEMENTS.md` §I81. `knowledge_base_v3` IS POPULATED.** Shape B
> re-embed: `scripts/reembed_chunks.py --from-collection knowledge_base_v2` (new mode; the SQLite mode
> and its §I13 refusal are unchanged) recomputes the **dense** lanes with nomic **late-chunked**, and
> **carries `colbert` + `sparse` over** from v2 (same models, unchanged vectors — plan §2). **3,796
> points / 341 parents in 612.7 s, exit 0, 0 failures.** All five verifiers pass
> (`logs/p1/step10/reembed_v3_verify.py`): **V1** chunk_id set byte-identical (3,796/3,796, 0
> missing/extra), **V2** every lane on every chunk point, **V5** point ids preserved, **V3** A-vs-A
> bit-identical (29 children), **V4** the known-vector spot check — Qwen3 recomputation reproduces
> v2's stored `dense_1024` at **cos 1.000000**. The plan's gate
> (`verify_collection_lanes.py --collection knowledge_base_v3`) → **exit 0, all four lanes 3,796/3,796**.
> A **negative control** (V2 pointed at v2) FAILS 3,796/3,796 — the lane check discriminates.
>
> **13. ⚠️ S3's SCOPE — do not assume more than this.** **RAPTOR (73 nodes) is NOT in v3** (the gate
> reports 0 raptor; the harness says so out loud) — that is a separate step
> (`run_phase2.py --raptor-only`). **No unit test was added for the Shape B mode** — the evidence is
> the live run + V1–V5 + the negative control. ⚠️ `knowledge_base_v2` is **still untouched (3,869)**.
> ⚠️ Also caught while verifying: **the cluster embedder is a memoised singleton** — a check that asks
> one process for two models must build the second one explicitly (V4 failed for the wrong reason
> until it did).
>
> **14. ✅ S4's CLASSIFIER HALF IS DONE — read `IMPROVEMENTS.md` §I82.** Retrained
> (`--train-only`, the existing 1,158-query set re-embedded with nomic) → `(1158, 768)` at
> `data/models/intent_classifier.pkl`. ⚠️ Its synthetic held-out accuracy is **99.6 %** — that is
> self-consistency on synthetic queries, **not** a product measure. Verifier
> (`logs/p1/step10/s4_intent_verify.py`, ALL PASS): the router **REFUSES** the 1024 pickle under a 768
> config (V2 — why this stage is not optional); the new one loads and predicts; on the **133 gold
> queries** agreement is **0.5714 vs the old 0.3534 (Δ +0.2180)** — ⚠️ mostly the **overview** class
> (old **0.000**), while **multihop got slightly worse** (0.725 vs 0.825), and the absolute 0.57 is
> **moderate** (synthetic training does not transfer cleanly to real queries — reported, not buried);
> and a **real query through the product funnel returns 5 hits** (V6).
>
> **15. ✅ S4 IS COMPLETE — the preflight is CLEAN (exit 0). Read `IMPROVEMENTS.md` §I83.** The two
> blockers were the derived collections at the retired **1024d**. They were dropped via the
> **allowlisted** `scripts/reset_derived_collections.py` (NOT `reset_for_reingest.py`, which would also
> clear `knowledge_base` + SQLite), recreated at **768** by `get_qdrant()`, and re-populated:
> **`derivative_artifacts` 73,406** (`index_derivative_artifacts.py --clear --doc-id …`, ~26 min) and
> **`concept_embeddings` 6,065** (NEW `logs/p1/step10/reindex_concepts_768.py`, ~24 min).
> ⚠️ **The concept re-embed did NOT rebuild the graph** — `run_phase3 --graph-only` would re-extract
> concepts (an LLM pass, ~1 h 6 m) and **double every `RELATES_TO` weight** unless the graph is
> cleared. Only the vectors changed width; the graph was valid, so only the NAMES were re-embedded
> (reproducing `graph_builder._upsert_concepts_to_qdrant`'s id scheme and its `embed_query`
> both-sides convention). **Result: `preflight.py` exits 0 — *"All checks passed — safe to run the
> baseline."*** v3 3,796; both derived dim checks **768d == dense_dim**; graph↔Qdrant 0/3,533 absent.
> ⚠️ DA reads **0 points until it finishes** (it buffers all points, then upserts in 256-batches) —
> not a stall.
>
> **16. ▶ NEXT — S5.** (a) **§I68's client-side-RRF fix** (Qdrant's server-side RRF is
> nondeterministic; `store._rrf_merge` is the in-repo replacement — blast radius: one source file,
> **two test files that break by construction**, one harness). (b) The **ONE pre-registered
> product-endpoint run**: **nomic/v3 vs qwen3/v2**, 133 queries, paired, **HyDE ON and frozen** via
> `data/hyde_cache/`; pre-registration **committed ALONE first**. (c) The **§I66 decomposition**
> alongside it. (d) S6, the fine-tune (**signoff 6** open). ⚠️ `data/embed_cache/` (874 dirs) cannot
> be reused. ⚠️ Still carried: **signoff 4** (accept the §I79 measurement), **signoff 3** (re-confirm
> Shape B), the **A2 `.env` flip**, the arm-2 harness, §I56's DA lane, §G2's V5 build, §G5/§I2.
>
> ## ▶ SESSION 17b — THE EMBEDDER DECISION, AND THE NEXT SESSION'S OPENING PROMPT
>
> **⚠️ THE ADOPTED EMBEDDER IS NOW `nomic-ai/nomic-embed-text-v1.5` @768/64 — NOT gemma.** Owner
> decision 2026-10-25, taken on the measurement in **`IMPROVEMENTS.md` §I77** and its **addendum**.
>
> **▶ READ, in this order and only this much:** this block → the nomic plan's **§0, §1, §8**
> (`.hermes/plans/2026-10-25-p1-nomic-adoption-reembed-and-finetune-plan.md`) → the nomic brief
> (`.hermes/plans/2026-10-25-p1-nomic-adoption-SESSIONS.md`) → then only the § your stage needs.
> **Opening prompt:** *"Read HANDOFF.md session 17b, then the nomic plan's §0/§1/§8 and the nomic
> SESSIONS brief. I am starting S1 (Stage A2 + A2b). Signoff 4 (the MRL convention) is still open and
> gates S3 — take it first."*
>
> **1. WHY NOMIC, AND THE HALF THAT MUST SURVIVE.** ⚠️ **This is a COST decision on NEW MEASUREMENT —
> it is NOT a finding that nomic is better.** §I74's product-stage contrast still favours gemma
> (**+0.029248**, resolved but only ~1.19× the run's own resolution floor, CI lower bound below it).
> What changed is the **cost**, measured on both candidates over the same corpus: gemma's endpoint
> **truncates at 2048 tokens** (71/341 parents, **37.3 %** of children in a truncated parent, **9.2 %**
> losing vectors outright) while nomic's window is **8192** and **0/341 parents exceed it**; and gemma's
> tokenizer is a **gated HF repo** while nomic's is **ungated**. ⚠️ **Do not restate this later as
> "gemma was worse"** — that is the one sentence the plan's §0 forbids.
>
> **2. ⚠️ THE FOUR TRAPS (plan §1) — three of them bite SILENTLY. Read them before writing code.**
> (a) **The document-side prefix does not exist on the cluster path**: `NomicEmbedder` (local) prefixes
> both sides, but `ClusterDenseEmbedder` applies the query instruction only — nomic would be used out of
> distribution (§I62: unprefixed cosine 0.949 vs 1.000000). (b) ⚠️ **The prefix collides with late
> chunking**: offsets are computed on the RAW parent text while the endpoint would get PREFIXED text, so
> **every span shifts by the prefix's token count** — a mis-pooled vector with **no warning**. (c) **The
> alignment rule must be re-probed**: nomic's endpoint returns `n_api == n_local + 2` (the same delta as
> gemma) and `_content_tokens` accepts only `n_local`/`n_local+1`, so **it raises on every parent**.
> (d) **The MRL convention is now load-bearing**: `mrl_slice` does a plain slice + re-normalise while
> Nomic's card prescribes `layer_norm`-then-slice, so **every Nomic-64 number in the register is under
> the project's convention** — and the 64d lane IS the funnel's first stage. **Signoff 4, still open.**
>
> **3. WHAT SURVIVES FROM THE GEMMA WORK.** Stage A's machinery is **in force and load-bearing**:
> `_LOW_VECTOR_NAMES = ("dense_128", "dense_64")` + `_resolve_low_lane`, which reads the lane's **name
> and width off the collection**, is exactly what makes this embedder change a **config switch** rather
> than a code fork. The full lane stays the width-free **`dense_full`**. ⚠️ `dense_dim_low` goes
> **128 → 64** and the low lane is named **`dense_64`** (nomic's MRL slot). **Stage A: ✅ committed.**
>
> **4. ✅ ALSO DONE THIS SESSION:** the **lane gate** (`scripts/verify_collection_lanes.py` — it did not
> exist; 11 tests, 5/5 mutations, verified live against v2 at 3,796/3,869) · **§I76** (v2 carries FOUR
> lanes incl. `sparse`, measured) · **§I77** + its addendum · sessions 13–17 committed (13 commits).
>
> **5. ⚠️ CURRENT MACHINE STATE, so the next session does not mis-read it.** `.env` holds **no**
> `DENSE_*` keys — the config resolves to the **Qwen3/1024** default, so v2 works normally and **no
> interim hazard is armed**. ⚠️ **`knowledge_base_v3` EXISTS WITH THE GEMMA SHAPE** (`dense_128` 128d +
> `dense_full` 768d, **0 points**): **S2 drops and re-creates it** — a dimension is immutable.
> **`knowledge_base_v2` is untouched (3,869 points).** ⚠️ **The re-ingest itself has still NOT STARTED:
> 0 %.**
>
> **6. ▶ THE OPEN SIGNOFFS** (plan §7): **3** Shape B vs A — provisional, confirmed at S2's C0; **4** the
> MRL truncation convention — **OPEN, gates S3**; **6** the fine-tune's validation split (by
> document/passage, not by card) — **OPEN, gates S6**.
>
> ## ▶ SESSION 17 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **1. ✅ THE FIVE OWNER SIGNOFFS ARE TAKEN (2026-10-25).** The plan's §7, in the brief's order:
> **(1)** the low lane is **`dense_128`** — ⚠️ **the owner overrode the plan's `dense_low`
> recommendation**; the plan had rejected `dense_128` *because it encodes the dimension*, which is
> §I13's trap. Implemented as instructed and recorded as the owner's call, so it is not re-litigated
> later — but the cost stands: the **next** embedder change repeats this rename. **(2)** `dense_full`
> renamed **NOW** (not deferred as debt). **(3)** build into a **new `knowledge_base_v3`**, v2 left
> untouched and queryable. **(4)** **Shape B, provisional** — confirmed at S2's C0. **(5)** §I68's
> client-side-RRF fix lands **before Stage F**. Plus: **commit sessions 13–17 now**.
>
> **2. ✅ STAGE A IS LANDED (the lane rename).** `_DENSE_VECTOR_NAMES = ("dense_full", "dense_1024",
> "dense_768")`, `_LOW_VECTOR_NAMES = ("dense_128", "dense_64")`, `dense_dim_low = 128`,
> `database._ensure_collection` declares `dense_128`/`dense_full`, and the log line now derives its
> lane list from `vectors_config` (it had printed `dense_64+dense_1024` for two sessions — a record
> that drifted from the thing it recorded, §I44's class).
>
> **3. ⚠️ THE DESIGN FINDING THE PLAN LEFT IMPLICIT — the low lane's WIDTH must be resolved off the
> COLLECTION, not from `cfg.dense_dim_low`.** With `dense_dim_low = 128`, slicing the query vector to
> the config value sends **128d into v2's 64d lane**: Stage F's **baseline arm dies**. v2's low lane
> is 64d and v3's is 128d, and the A/B queries **both**. So `store._resolve_low_lane(vectors_cfg, cfg)`
> returns `(name, width)` from the collection, the **read** path slices *to* that width, and the
> **write** path asserts the produced vector's width against the lane (`_assert_lane_width`) — a
> mismatch raises naming the lane, both widths and the remedy, instead of a bare Qdrant 400 (§I47).
> ⚠️ The assert is on the **vector's** width, not on `cfg`: that is what keeps a deployed 64d-lane
> collection **writable** (the case `test_save_document_writes_dense_768_into_a_dense_768_collection`
> exists to protect).
>
> **4. ✅ §I76 — `v2` CARRIES **FOUR** LANES, INCLUDING `sparse`.** The plan's §2/§8 "correction"
> (*"no sparse lane; a four-lane assertion is unpassable"*) was **itself wrong**: `splade_enabled`
> resolves **True** (`.env:159` beats `config.py:178`) and the sparse lane lives in
> **`params.sparse_vectors`**, a separate key from `params.vectors` — which is what the session-16
> check read. Measured live: **3,796 of 3,869** points carry real SPLADE vectors, and the 73 without
> are `raptor_level: 1` summary nodes. **⇒ v3 declares FOUR lanes and carries `sparse` (and
> `colbert`) over by id.** A three-lane v3 would be a regression on a lane the product path reads
> (`store.py:460`) and would confound Stage F with a lane-presence difference.
>
> **5. ✅ THE §I28 SWEEP, SCOPED BY MEASUREMENT — 34 quoted lane literals across 22 files.**
> Repointed: `src/` (store, database, embed_cache), `scripts/` (reembed_chunks, funnel_boundary_recall,
> why_colbert — all now resolve the lane off the collection) and the 6 test files. ⚠️ **Deliberately
> NOT repointed: the `logs/p1/**` probes.** They hardcode `COLLECTION = "knowledge_base_v2"` and
> **abort** if the config disagrees, so `dense_64`/`dense_1024` **are** their correct names and
> repointing them would break them against the store they measure. ⚠️ The plan's §8 sweep list said
> "6 probes under `logs/p1/`" — blanket-sweeping those is wrong.
>
> **6. ✅ `scripts/verify_collection_lanes.py` IS BUILT AND VERIFIED LIVE** (S2's deliverable, pulled
> forward; the brief had moved it out of Stage C so the run would not write its own gate).
> `tests/test_verify_collection_lanes.py` — 11 tests, **5/5 guards proven to discriminate by
> mutation**. Live against v2: **3,869 points (3,796 chunk / 73 raptor), colbert 3,796, sparse 3,796,
> dense_64/dense_1024 3,869, 0 gaps, exit 0** — reproducing the independently-measured numbers
> exactly. v3 absent → **loud 404, exit 2** (so Stage B has provably not run). ⚠️ It builds its own
> client and **must not** use `database.get_qdrant`, which **creates** the collection it cannot find —
> a gate that creates its subject can never report it missing. ⚠️ Its first draft (a dispatched
> child's) read `point.vectors` where a real record exposes **`point.vector`** → every point skipped →
> **silent all-clear with zero coverage**, and its 2 tests passed because the stub declared the same
> wrong attribute. Both are fixed; the scoping also excludes `colbert` from the RAPTOR requirement
> (it lives in `params.vectors` but summary nodes do not carry it — 73 false gaps otherwise).
>
> **7. ✅ SUITE: 667 passed / 4 failed / 6 skipped.** The 4 are the **documented pre-existing set**
> (`test_phase1` ×1, `test_phase2` ×1, `test_splade` ×2) — ⚠️ **proved, not assumed**: the three
> `src/` files were stashed and `test_hybrid_search_includes_global` re-run, and it fails on the
> baseline too. Stage A's own 5 mutations all discriminate; `store.py` restored byte-identically
> (sha256 `912b393a…`).
>
> **8. ⚠️ DELEGATION: TWO CHILDREN MISREPORTED, AND BOTH WERE CAUGHT BY CHECKING DISK.**
> (a) The first arm-2 child reported creating `min_chunk_tokens_ab.py` and a `.json` artifact —
> **neither existed**. (b) The re-dispatched child produced real files but a **fabricated `ls`**
> (`user group`, `Jun 25` — this machine is `bharathkumar staff`) and a guard table listing **guards it
> had not implemented**. ⚠️ **The arm-2 harness is a FRAGMENT, not the experiment**: it re-chunks and
> prints child counts, then stops — **no embedding, no ranking, no endpoint, no artifact**, and its
> "verifier" reads a JSON nothing writes. **Arm 2 is NOT built.** The rule that earned its keep: *a
> child's report is a self-report; require a verifiable handle and check it yourself.*
>
> **9a. ⚠️ A NEW STAGE, FOUND BY RUNNING STAGE B — and it gates the re-ingest.** **No stage in the
> plan assigns `dense_model` / `dense_dim`.** Stage A lists only `dense_dim_low = 128`, and §2
> declares `dense_full` at **768** — but `config.py:72-73` still reads `Qwen/Qwen3-Embedding-0.6B` /
> `1024`. **Measured:** running Stage B created v3 with **`dense_full` at 1024d** — a dimension is
> **immutable**, so it can never hold gemma's 768d vectors. v3 was empty, so it was **dropped** and
> v2 verified untouched (3,869). **Stage B's own gate caught it**, which is what it is for.
> **⇒ Stage A2 = `dense_model = google/embeddinggemma-300m`, `dense_dim = 768`, and it must land
> BEFORE Stage B.** ⚠️ **It is not a one-line flip:** `cfg.dense_dim` is **42 sites / 16 files**;
> `embed_cache._FINGERPRINT_FIELDS` carries it (cache invalidates); and the **derived collections are
> declared at `dense_dim`**, so `_assert_collection_dim` will **refuse** against the existing 1024d
> ones (§I47, by design) until they are reset — the flip, the reset and the re-embed belong to
> **one co-ordinated window**. ⚠️ **Interim hazard:** with the config at 768 and v2 still live, the
> default path produces 768d query vectors against v2's `dense_1024` slot → Qdrant rejects. v2 stays
> queryable only via a caller that supplies the matching embedder per arm. **Full note: the plan's
> Stage A2.** **OWNER DECISION, NOT TAKEN.**
>
> **9b. ✅ A2 AND B ARE DONE (2026-10-25). ⚠️ C0 IS BLOCKED — AND IT BLOCKS STAGE C TOO.**
> **A2**: `dense_model`/`dense_dim` are now an **`.env` override** (`.env:170-171`, gitignored) —
> chosen over a `config.py` default change so Stage F can switch per arm in one process and the flip
> reverts without a code edit. Resolved config prints `google/embeddinggemma-300m` / **768**.
> **B**: `knowledge_base_v3` **EXISTS**, read back from the LIVE store — `dense_full` **768**,
> `dense_128` **128**, `colbert` (max_sim), `sparse`, **0 points**; **v2 untouched (3,869)**.
> ⚠️ **C0 cannot run, and the reason blocks Stage C as well:** `google/embeddinggemma-300m` is a
> **GATED HuggingFace repo** and the late-chunk path needs its **tokenizer locally**
> (`LateChunkEmbedder._get_tokenizer`) — the cluster returns per-token *vectors*, but the
> **character offsets** that define each child's span come from a local tokenization. Measured:
> **401 gated repo**, and **no HF credential is configured on this machine** (no `HF_TOKEN`, no
> `HUGGING_FACE_HUB_TOKEN`, no stored token). The previous ingest never hit this because **Qwen3 is
> not gated**. ⇒ **Shape B's cost is unmeasurable and Stage C cannot start until the gemma tokenizer
> is available locally. OWNER ACTION (authenticate HF + accept the Gemma licence), not a code fix.**
> Probe/artifact: `logs/p1/step10/c0_late_chunk_timing.{py,json}` → `status: BLOCKED_ON_TOKENIZER`,
> exit 3. ✅ Its corpus half **did** verify: **341 parents / 3,796 children / 11.13 per parent**,
> reproducing the register exactly.
> ✅ **RESOLVED THE SAME DAY (owner decisions, session 17).** **(a) The tokenizer is unblocked by
> HuggingFace auth + accepting the Gemma licence** — clean provenance, `cfg.dense_model` unchanged.
> **This is an OWNER ACTION and it is OUTSTANDING.** ⚠️ **Diagnosed exactly 2026-10-25: `hf login`
> HAS been run and the token is VALID** (`whoami` → `BharathKS`, type `user`; connectivity fine — an
> ungated file returns 200). **The gated file still returns 403, and the server's message names the
> TOKEN, not the licence:** *"Please enable access to public gated repositories in your fine-grained
> token settings"*. ⇒ **Two conditions:** (1) the token must be permitted to reach public gated
> repos (enable it in the fine-grained token's settings, or use a **classic read token**, which has
> it by default); (2) the Gemma licence accepted on the model page. ⚠️ (1) **masks** whether (2) is
> already done — re-run the probe after fixing the token. ⚠️ **The trap: `transformers` reports this
> 403 as `LocalEntryNotFoundError` — "couldn't connect … check your internet connection" — with
> `status=None`.** The text blames the network; the cause is a permission. Read the status with the
> auth header, do not chase connectivity. ⚠️ The ungated `unsloth/embeddinggemma-300m`
> mirror **does** load without credentials (measured: `GemmaTokenizerFast`, vocab 262,144, offsets
> returned) but was **DECLINED**: third-party copy, the Gemma licence still applies, and byte-identity
> against the gated original cannot be verified. **(b) The `.env` flip was REVERTED** — the dense lane
> is back to `Qwen/Qwen3-Embedding-0.6B` / 1024, with `dense_dim_low = 128` standing (that is Stage A).
> ⚠️ **v3 is unaffected and stays valid: its `dense_full` is 768, and a dimension is immutable.**
> **A2 is re-applied as the FIRST step of the re-embed window, not before it.**
>
> **9c. ✅ HF ACCESS IS FIXED; ⚠️ C0 THEN RAN AND FAILED — read `IMPROVEMENTS.md` §I77.** The 403 was
> the **fine-grained token's missing "public gated repositories" permission**; once fixed the gated
> file returned **200** and the gemma tokenizer loaded through the project's own path
> (`GemmaTokenizerFast`, vocab 262,144). **C0 ran: 20 of 20 parents FAILED.** Two structural defects:
> **(1) the alignment contract is off-by-TWO for gemma** (`<bos>` + `<eos>`, so the content matrix is
> `matrix[1:-1]`; `_content_tokens` raises rather than mis-shifting — the guard worked); **(2) the
> gemma endpoint TRUNCATES at 2048 tokens**, which Qwen3's larger window meant the corpus never met —
> **71/341 parents (20.8 %) exceed it** and **351/3,796 children (9.2 %) cannot be late-chunked
> faithfully** (281 entirely beyond, 70 straddling). ⚠️ **The late-chunk pass — Shape B's core —
> cannot run under gemma at all, so the ~48 min estimate is MOOT until this is settled, and it is a
> DESIGN DECISION, not a bug fix:** (a) pre-registered MIXED index (90.8 % late-chunked / 9.2 %
> isolated), (b) split long parents ⇒ new chunk ids ⇒ **Shape A**, or (c) drop late chunking for
> gemma. **OWNER DECISION, NOT TAKEN.** ⚠️ **It does NOT touch §I70/§I72/§I74's measured gain** —
> those embedded the text **pooled, not late-chunked**.
>
> **9. ▶ NEXT, IN ORDER.** (a) **OWNER: decide the late-chunk disposition (§I77)** — this now gates
> Stage C. (b) **Stage B** ✅ done.
> (c) **Stage C0** — time the late-chunk pass on **~20 PARENTS** (not chunks)
> (`dense_full` 768, `dense_128` 128, `colbert`, `sparse`); seconds. (b) **Stage C0** — time the
> late-chunk pass on **~20 PARENTS** (not chunks) and record the unit; this confirms signoff 4. (c)
> Stage C (the re-embed, Shape B), then D (classifier retrain), E (preflight), F (the ONE
> pre-registered product-endpoint run), G (§I66 decomposition alongside F). ⚠️ Still carried:
> §I68 before F, arm 2's harness, §I56's DA lane, §G2's V5 build, §G5/§I2, §I55's follow-on,
> §I58's `gold-003` caveat, §I53 item 6.
>
> ## ▶ SESSION 16 — WHAT HAPPENED, AND THE NEXT SESSION'S OPENING PROMPT
>
> **1. ▶ THE NEXT SESSION TAKES THE GEMMA RE-INGEST.** Read, in this order and **only this much**:
> `HANDOFF.md` (this block) → **`.hermes/plans/2026-10-24-p1-gemma-adoption-SESSIONS.md`** (the
> per-session brief — which slice each session owns) → the gemma plan's **§8** (verified literals)
> → then **only the § of the plan your stage needs**. Do **not** read the 320-line plan whole.
> **Opening prompt:** *"Read HANDOFF.md session 16, then `.hermes/plans/2026-10-24-p1-gemma-adoption-SESSIONS.md`.
> I am starting S1 (Stage A). Take the five owner signoffs in §0 first."*
> ⚠️ **Five owner signoffs gate Stage A** — none can be deferred. §0 of the brief sequences them
> (take 1/2/3/5 now; 4 is provisional until S2's C0 measurement).
>
> **2. ✅ §I75 — THE GRAPH LANE IS REACHABLE AND SERVING. The recorded blocker was FALSE.** The plan
> and session-13 §5 excluded the graph lane because *"Memgraph is DOWN — 7687 refused"*. That probe
> tested the **cluster** IPs; the code and `.env` point at **`localhost:7687`**, where Docker
> `synapse_memgraph` (2.18.1) is **Up** — the §I49 Finding 1 class again, a host assumed not resolved.
> Measured: 1 Document / 3,533 Chunk / 907 Page / 6,065 Concept, and **5/5 multihop queries returned
> 5 chunks each in ~5 s** through the production path (`graph_lane_probe.json`). ⚠️ Two red herrings
> recorded: the container reports **`unhealthy`** purely because its healthcheck execs `mg_client`,
> which is not in the image (24,362 consecutive failures, DB fine); and ⚠️ **reachability is not
> contribution** — every query returned exactly its limit and several concept sets are off-query
> (§I56 is the precedent). **`hop_distance` is still a constant 0** (a **code** defect, §G5/§I2) —
> that is the only remaining reason to exclude the lane. ⚠️ **Also flagged, unexplained: Concept nodes
> and `concept_embeddings` both read 6,065 now, against 7,427 recorded at §I21/§I49 — −1,362 in
> lockstep. Mechanism not established; needs its own check.**
>
> **3. ✅ ARM 2 IS PRE-REGISTERED AND ~20× CHEAPER THAN ASSUMED.** `min_chunk_tokens` needed a
> Docling re-parse of the 968-page PDF in the plan's reading. **It does not:** the E1 chunking is a
> **pure function of the stored payloads** — 341 parents reconstructed from `parent_id`/`parent_text`
> reproduce the index **exactly** (3,796 children, boundary-for-boundary, **~3 s**), run twice with a
> byte-identical artifact. ⚠️ **And the knob is bigger than §E1 recorded: the merge removes 1,919
> children = 33.6 %** (5,715 raw → 3,796), against §E1's 27 % on a 42-parent fixture. Pre-registration:
> `.hermes/plans/2026-10-24-p1-min-chunk-tokens-ab-preregistration.md` — **commit it alone before the
> run**. ⚠️ **The chunking arms do NOT force Shape A** (measuring is cheap; *shipping* a chunking
> change is what needs a full re-ingest) — corrected in the gemma plan §5.
>
> **4. ⚠️ §I68's BLAST RADIUS IS MEASURED, AND A RECON UNDER-REPORTED IT** (`IMPROVEMENTS.md` §I68
> §4a). The client-side-RRF fix is **not** a one-file no-op: `FusionQuery(fusion=Fusion.RRF)` is also
> in `scripts/funnel_boundary_recall.py:249,279` (**the harness §I68's own measurement ran through**)
> and `scripts/why_colbert.py:84`; and **two unit tests call `_qdrant_search` directly and assert on
> the exact `Prefetch` structure the swap removes** (`tests/test_dense_prefetch_limit.py:51,61-65`,
> `tests/test_downstream_widths.py:55`) — they break by construction and must be rewritten. The
> dispatched recon claimed both "only store.py" and "no tests" — **both false, re-checked against the
> source before recording.**
>
> **5. ✅ THE GEMMA PLAN'S LITERALS ARE VERIFIED — FOUR WERE WRONG, ALL CORRECTED IN PLACE** (plan
> §8): the `sparse` lane **does not exist on v2** (`splade_enabled=False`, so nothing to carry over,
> and a four-lane Stage E assertion is unpassable) — ⚠️ **THAT "CORRECTION" IS ITSELF WRONG, found and
> registered 2026-10-24 (session 17) as `IMPROVEMENTS.md` §I76: `v2` DOES carry a `sparse` lane on
> 3,796/3,869 points, it lives in `params.sparse_vectors` (a separate key from `params.vectors`, which
> is what the session-16 check read), and `splade_enabled` resolves **True** (`.env:159` beats
> `config.py:178`'s default). v3 must declare FOUR lanes.**; Stage C0's sample unit is **PARENTS, not chunks**
> (one cluster call per parent); §5's "arms 2–3 need Shape A" (above); §6's "Memgraph is down". ✅
> Holds: `store.py:451`/`:432`, `intent_router.py:156`, `evaluate_rag.py:333-341`, all four named
> scripts present, `verify_collection_lanes.py` confirmed **absent**, the payload keys, and the HyDE
> cache — **127 entries = exactly the 93 HyDE-eligible queries** (53 factual + 40 overview) of the
> 133; the 40 "missing" are multihop, which `evaluate_rag.py:190` never Hyde-ifies. **Nothing to
> generate; do not extend it.** ⚠️ The `dense_64` sweep surface is **33 literals across 18 files**,
> and `dense_dim_low` sits in `embed_cache._FINGERPRINT_FIELDS` — so the rename **invalidates the
> 874-dir resume cache** (correct, but it must be in the cost).
>
> **6. ⚠️ NOT COMMITTED, AND IT IS NOW SESSIONS 13–16.** The brief's §4 lists the independent lanes
> (arm 2, §I68, §I75's follow-ups, housekeeping). **Committing is an owner decision and has been
> outstanding since session 13.**
>
> **Last updated: 2026-10-23, session 12. ✅ §I61'S PRE-REGISTERED A/B RAN — THE LEVER IS A NULL, AND
> THE LOSS IS THE 100-SLOT FUSION, NOT THE PREFETCH. Read `IMPROVEMENTS.md` §I65 and §I66 first.**
>
> **Last updated: 2026-10-24, session 14. ✅ PLAN §1 RAN — THE EMBEDDER SCREEN HAS A WINNER:
> `google/embeddinggemma-300m` @768 PASSES the pre-registered rule, beating BOTH the incumbent
> (Qwen3-1024, +0.1865) and §I63's Nomic-768 (+0.0465), all eleven verifiers passing. Read
> `IMPROVEMENTS.md` §I70. ⚠️ It is an ORACLE screen — it licenses COSTING the re-ingest and ONE
> product-endpoint run, both OWNER DECISIONS, NOT TAKEN.**
>
> **Last updated: 2026-10-24, session 15. ✅ §I71 ARM 1 RAN — THE CONTENT FILTER IS A NULL ON
> BASE-LANE PAGE RANKING, AND THE REASON IS STRUCTURAL. The pre-registration's premise was WRONG and
> the correction is the finding: the content window `[30, 936]` already excludes **244 of the
> filter's 263 rejects**, so the treatment is **19 chunks, not 263**. The first run went VOID on that
> premise error (C2/C4) plus one harness bug (C3); re-registered as C2′/C4′ and re-run, all EIGHT
> guards pass. Read `IMPROVEMENTS.md` §I71, then the re-registration
> `.hermes/plans/2026-10-24-p1-chunk-filter-ab-reregistration.md`.**
>
> ## ▶ SESSION 15 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **1. ✅ THE RESULT — THE FILTER DOES NOT MOVE THE BASE LANE.** Paired Δ **ceiling-normalised
> R@20** (§I58), arm T − arm C, n = 133, primary **gemma@768**:
>
> | contrast | what it moves | result |
> |---|---|---|
> | **gemma@768, cR@20** (PRIMARY) | pool 3,489 → 3,470 | Δ **−0.006330**, CI **[−0.021115, +0.008456]** **UNRESOLVED**, W/L/T **1/8/124** |
> | gemma@768, raw R@20 | ″ | Δ −0.006391, CI [−0.021173, +0.008391] **UNRESOLVED** |
> | qwen3@1024, cR@20 | ″ | Δ **+0.000009**, CI [−0.000009, +0.000028] **UNRESOLVED**; raw Δ **exactly 0** |
>
> **Per the pre-registered rule the filter does NOT ship**, and the honest statement is the
> pre-registered one: **applying the content filter does not move base-lane page ranking on this
> corpus — a RESULT, not an unresolved one.** The point estimate is slightly negative and is **under
> half the resolution floor** (0.014786 at n = 133), so it is not a measured harm either. Under
> qwen3 the treatment is **literally inert** (raw R@20 identical on all 133 queries).
>
> **2. ⚠️ THE HEADLINE IS THE PREMISE ERROR, AND IT IS THE FINDING.** The pre-registration's F1 said
> the CURRENT filter would exclude **263** chunks and built two guards on it. That 263 is the
> **WHOLE-CORPUS** count (3,796 chunks: 72 TOC on pages 22–34 + 186 index on pages **937–968** + 5
> front matter on pages **2–14**). This arm's pool is the **content window `[30, 936]`** — 3,489
> chunks — and **244 of the 263 sit outside it** (the index is entirely above 936, the front matter
> entirely below 30, the TOC mostly below 30). **The treatment is 19 chunks.** ⚠️ **§I39's premise is
> true of the CORPUS and false of the BASE LANE**: the retrieval lane is window-bounded, the card
> generator (§I39's 5,100 junk cards) is **not**. The filter's marginal reach on the base lane is
> **structurally capped at 19 chunks** — which is why the null was close to predictable in advance,
> and why the *size* of the lever, not just its sign, is the result. ⚠️ F2's "pages with chunks
> **933**" is also wrong: §I70's own artifact and this run both measure **888** (guard X1, two
> independent directions agreeing exactly).
>
> **3. ⚠️ §I71 — THE FIRST RUN WAS VOID, AND THE DISPOSITION SPLIT IN TWO.** It failed **C2, C4**
> (the premise error above — a corpus count written into a guard about a window-filtered pool) and
> **C3**. C3 failed as **266 metric mismatches on bit-identical vectors** (`max_abs_diff 0.0`, 0 rows
> differing) — impossible, and the tell that the *check* was wrong: the control arm was scored
> against the raw reachable set instead of arm C's **own per-query ceiling**. **A control compared
> under a different denominator is not a control.** Fixed. ⚠️ **C3 was a check that could only
> fail.** VOID artifact preserved: `chunk_filter_ab_firstrun_VOID.json` (sha256 `0b25fd34…`).
> **Re-registered** (`.hermes/plans/2026-10-24-p1-chunk-filter-ab-reregistration.md`, §I67's E4 → E4′
> precedent — restated **by measurement**, not relaxed) and **re-run: all eight guards pass**, exit 0.
> The pre-registration itself was **NOT edited**.
>
> **4. ✅ VERIFIERS: all EIGHT pass on the re-registered run**, including **C1 — arm C reproduces
> §I70's qwen3@1024 row EXACTLY** (0.293934 / 0.569074 / 0.922982 / 1.0) — plus a **third exact
> reproduction found after the run**: arm **C under gemma@768** equals §I70's `gemma@768` row
> (R@20 **0.480410**, R@100 **0.704882**, R@500 **0.946105**), and C6's page-array sha256
> `0ca575fabc5c59be…` is the array §I70's V6 reported. **Mechanical evidence, kept apart from any
> verdict:** `chunk_filter_ab_verifier.py --check` — an independently written stdlib aggregation
> reading only the raw per-query array — re-derives every aggregate, endpoint, CI and decision field
> at **197 checks / 0 mismatches**. ✅ **Independent verifier `deleg_fac6860b` (`openai/gpt-oss-20b`,
> model resolved from `hermes config get delegation`; empty fallback chain) dispatched READ-ONLY —
> this session's shell returns empty stdout with exit 0, smoke-tested first — and it RETURNED:
> 8/8 CONFIRMED, no refutations.** ⚠️ **NOT BANKED (4 API calls, 32.8 s): two of its cited field
> paths do not exist in the artifact** (`meta.assembly`, `decision.pages_C` — verified absent), so its
> verdicts are a weak corroboration and its citations are not evidence. ⚠️ **Both of its
> "additional risks" are REFUTED**: the artifact does carry all 133 per-query rows, and the log does
> print the text-vs-stale-column evidence (`19` flagged from text vs `5` stored `False`, which C4
> asserts). The substantive half remains the mechanical evidence.
>
> **5. ▶ NEXT, IN ORDER.** (a) **Arm 2 — `min_chunk_tokens`** (32; §E1 measured it merging 27 % of the
> new children and never re-checking the grown child's size), then arm 3 `semantic_threshold` (0.8),
> then arm 4 late chunking (36 min/arm, and it changes the embedding rather than the chunking, so it
> is its own contrast). ⚠️ **§0's power rule stands:** n = 133, floor ≈ **0.020** — a knob with a
> plausible effect below that is out of scope for this gold set; record it, do not chase it. (b)
> Unchanged and carried forward: the **owner decision on the gemma re-ingest** (§I70 — cost it
> honestly; it needs a new named vector at 128 and a re-index of every derived collection), plan §2's
> **HyDE cache** (which the product-endpoint run needs), the **§I66 stage decomposition**, §I68's
> **client-side-RRF fix**, §I56's DA lane, §G2's V5 build, §I55's exclude-from-metrics follow-on,
> §I58's `gold-003` caveat, §I53 item 6, and **whether to commit sessions 13–15's work (all
> uncommitted)**.
>
> **6. ✅ BUILT IN THIS SESSION (not committed).** `logs/p1/step10/chunk_filter_ab.py` (the harness;
> extends §I70's `embedder_screen.py`, metric helpers copied verbatim so C1 can be an exact
> reproduction), `…_verifier.py` (independent stdlib aggregation, `--check` / `--extract`),
> `chunk_filter_ab.json` (sha256 `4e64f1ac…`, wall 176.4 s), `…_firstrun_VOID.json` (preserved),
> `…_verifier_extract.json`, the run log `chunk_filter_ab_run_session15.txt`, the **re-registration**
> plan, the §I71 register entry, and this block. **No writes to any collection, no LLM calls, no
> parse, no re-embed of the corpus.**
>
> **7. ✅ §I72 — THE CROSS-ENCODER SURVIVAL TEST RAN: THE EMBEDDER'S GAIN SURVIVES, BUT IT IS
> HALVED.** This is the stage §I66 named as the funnel's largest single loss (0.6048 → 0.4318), and
> the largest unmeasured risk in the gemma bet. Design: same corpus and shipped pool as §I70/§I71
> (3,489 chunks), 133 queries, HyDE off, exact cosine; per query take the top **100** chunks by
> cosine under each embedder (`cfg.reranker_fetch_k` — the product's own pool width), push each list
> through the **LIVE** cluster cross-encoder, and score page-level ceiling-normalised R@20 before and
> after. Endpoint: paired POST Δ, `gemma@768 − qwen3@1024`, n = 133.
>
> | stage | qwen3@1024 | gemma@768 | Δ | 95 % CI | W/L/T |
> |---|---|---|---|---|---|
> | **PRE** (cosine) | 0.274348 | 0.458665 | **+0.184317** | [+0.130809, +0.237824] | 12/77/44 |
> | **POST** (cross-encoder) | 0.363144 | 0.460703 | **+0.097559** | [+0.056072, +0.139045] | 22/46/65 |
>
> **survival ratio 0.5293.** ⚠️ **The reading is the mechanism, not the verdict:** the cross-encoder
> is a strong **equaliser** — it lifts the **weaker** embedder by **+0.0888** and the stronger by
> **+0.0020**. So gemma's incremental value **at the product's last retrieval stage is +0.0976, not
> the base lane's +0.1865.** ⚠️ It also partly explains why §I67's width levers were nulls: the
> cross-encoder already repairs most pool-quality difference.
>
> **8. ⚠️ §I72 — THE FIRST RUN WAS VOID ON A METRIC-CONVENTION MISMATCH (the session's third
> premise error).** Two page-level recall conventions are in play: §I70's screen uses **"top-k
> PAGES"** (rank every chunk, dedupe to pages, take the first k pages — it produced the register's
> 0.293934 / 0.480410), while the **PRODUCT** uses **"pages of the top-k CHUNKS"**
> (`scripts/evaluate_rag.py:333-341`, and the only one available for a reranked arm). The
> pre-registration's §2 described the product convention and its §4 required the PRE arm to
> reproduce §I70's — **two different numbers**, −0.0196 / −0.0217 apart on the two embedders. **S1
> failed; the run is VOID** (`ce_survival_firstrun_VOID.json`, sha256 `0947bc0d…`) and its numbers
> are **not registered**. Restated as **S1′** (re-registration; §I67's E4→E4′ and §I71's C2→C2′
> precedent): **(a)** §I70's convention is computed separately and reproduces the register
> **exactly** (0.293934 / 0.480410) — that pins the instrument; **(b)** the contrast's two sides are
> asserted to share ONE convention. Re-run: **all eight guards pass**, exit 0, artifact sha256
> `47f20747…`. ⚠️ **Three premise errors in one session now** (§I71 F1, §I70 F2, this) — the
> standing lesson: **when a guard asserts a reproduction of a number from elsewhere, name the
> population AND the convention it was measured under.**
>
> **9. ✅ TWO INSTRUMENT RESULTS WORTH CARRYING.** (a) **The cluster cross-encoder is
> DETERMINISTIC** — 10/10 repeat calls returned the identical order (S3), in direct contrast to
> **Qdrant's server-side RRF, which §I68 measured nondeterministic**. So a reranked A/B on this path
> does **not** inherit §I68's tolerance problem. ⚠️ 10 controls over 5 queries × 2 embedders — enough
> for this run, not a characterisation under load. (b) **0 rerank failures** on 266 calls at
> `fetch_k=100` (S4), where §I55 measured 1/133 rejections on the product path.
> **Mechanical evidence:** `ce_survival_verifier.py --check` = **144 checks / 0 mismatches**.
> **✅ Independent reviewer `deleg_c05e651f` (`openai/gpt-oss-20b`, read-only) RETURNED: 7/8
> CONFIRMED, 1 UNVERIFIED, no refutations** — ⚠️ **not banked** (23 calls, 40 s). Its one
> `unverified` is the determinism claim on sample size, which is **already the caveat §I72 records**.
> ⚠️ **Its one "risk" is REFUTED and the error is in the reviewer's own arithmetic**: it expected
> `gain_qwen3 + gain_gemma` (0.0908) to equal `post_delta` (0.0976); the correct identity is
> `post_delta = pre_delta + gain_gemma − gain_qwen3`, which holds to **1e-9, and per-query to 1e-12
> with 0 violations across 133 rows**. Recorded: **check a reviewer's arithmetic against the artifact
> before defending anything.**
>
> **10. ✅ THE HYDE CACHE IS BUILT (plan §2) — item 1 of the two the owner asked for.**
> `src/pdf_ingestion/hyde_cache.py` + `tests/test_hyde_cache.py` (**14 tests, all six guards
> mutation-proven** — each mutation makes its guard fail) + `scripts/build_hyde_cache.py` +
> `data/hyde_cache/` (gitignored). It caches the **TEXT** keyed by **query id**, so one file serves
> every candidate embedder; the file name carries the query-set, model and prompt digests and the
> **header is re-validated on read** (a model/prompt/query change is an honest miss, never a silent
> reuse). ⚠️ **A miss raises; it never falls back to a live LLM call mid-run** — that is the
> nondeterminism it exists to remove. ⚠️ The HyDE prompt is **duplicated** in `evaluate_rag.py` and
> `funnel_boundary_recall.py`; a test now asserts this module's prompt still matches both call sites,
> because the cache key derives from it. **Not wired into §I70's screen** (HyDE-off by design).
>
> **11. ✅ §I74 — GEMMA vs NOMIC AT THE CROSS-ENCODER: GEMMA WINS, NARROWLY.** The run §I72 left
> open (it compared gemma against the *incumbent*, not against the cheap candidate). Same design plus
> a third arm — `qwen3@1024` as the instrument anchor, `nomic@768` and `gemma@768` as the contrast —
> same pool, 133 queries, HyDE off, top-100 cosine candidates per arm, live cross-encoder.
>
> | contrast | Δ | 95 % CI | W/L/T |
> |---|---|---|---|
> | **PRE** (cosine order) | **+0.045469** | [+0.020104, +0.070835] | 16/50/67 |
> | **POST** (cross-encoder) | **+0.029248** | [+0.004620, +0.053876] | 12/34/87 |
>
> **survival ratio 0.643251** — gemma's advantage over nomic shrinks **36 %** through the stage (less
> than the 47 % its advantage over the incumbent lost, §I72). Context: `gemma − qwen3` POST
> **+0.097559**, `nomic − qwen3` **+0.068311** — **nomic alone already recovers ~70 % of gemma's gain
> over the incumbent.** **Three anchors reproduced §I70 EXACTLY** (qwen3 0.293934, nomic 0.433930,
> gemma 0.480410) under §I70's own convention. All **nine guards pass**, exit 0, artifact sha256
> `7de5cca4…`; independent aggregation **182 checks / 0 mismatches** (⚠️ its first `--check` caught a
> bug in **itself** — reversed operands for the `nomic_minus_qwen3` label — not in the artifact).
> ⚠️ **Reviewer: the first dispatch (`deleg_862d3e0a`) DIED on output-length truncation** after being
> pointed at the 400 KB artifact — **no verdict, not a pass**. Re-dispatched against a **23 KB compact
> pack** with a 5-claim / 500-word cap: **`deleg_4b0ece7b` RETURNED 5/5 CONFIRMED, no refutations**
> (5 calls, 16.7 s — ⚠️ **not banked**; one cited path misattributed, and on one claim it *inferred*
> the resolved flag rather than reading it). **Lesson: point a reviewer at a compact pack, never at a
> large artifact whole.**
>
> ⚠️ **The margin is thin and the entry says so:** the run's own resolution floor is **0.024628**, so
> δ = +0.029248 is only **~1.19× the floor**, and the CI's lower bound (+0.004620) sits well below it
> — the data are also consistent with a true effect *smaller* than the floor. The artifact records
> both floors and the CI; the "thin" reading is the register entry's, derived from those fields.
>
> **12. ✅ THE ADOPTION CALL IS TAKEN (OWNER, 2026-10-24): `google/embeddinggemma-300m` @768**, with
> the low lane renamed and widened 64 → 128. The pre-registered rule was met (+0.029248, CI excluding
> 0, δ > the 0.020 floor) and ⚠️ **the margin is narrow — ~1.19× the run's own resolution floor
> (0.024628), with the CI's lower bound (+0.004620) below it. Quote the size, not just the sign.**
> ⚠️ **nomic was DECLINED as a COST decision, not a data finding** — it is a same-width drop-in (MRL
> 64 keeps `dense_64` true) needing **no code change**, so it is not to be restated later as "nomic
> was worse".
>
> **▶ THE EXECUTION PLAN: `.hermes/plans/2026-10-24-p1-gemma-adoption-and-reembed-plan.md`.** Stages
> A–G, each with a verifier that can fail: **A** the code change (⚠️ **the rename lands BEFORE the
> widening** — `store.py:451` hardcodes `using="dense_64"` and `store.py:432` keys the schema on the
> literal string, so widening first would need a lane *named* `dense_64` that is 128-dim, §I13's trap);
> **B** create `knowledge_base_v3` with four lanes (dense full 768 + `dense_low` 128 + `colbert` +
> `sparse` — ⚠️ the last two are **carried over**, different models, unchanged vectors); **C0** measure
> the late-chunk pass on ~20 chunks BEFORE committing; **C** the re-embed — ⚠️ **Shape B, preserving
> chunk ids**, because the payloads carry `text` / `parent_text` / `char_start` / `char_end`, so late
> chunking is reproducible **without re-parsing** and **cards (8.9 h) + the graph (1 h 6 m) stay
> valid**; **D** retrain the intent classifier (⚠️ `intent_router.py:156` **refuses** a 1024-trained
> model against a 768 embedder — not optional); **E** preflight; **F** ONE pre-registered
> product-endpoint run, HyDE frozen via §I73's cache; **G** the §I66 stage decomposition alongside it.
> ⚠️ **Five signoff points** in the plan's §7 (lane name, `dense_full` now-or-debt, v3-not-in-place,
> Shape B vs A, §I68 before F). ⚠️ **A new deliverable falls out: `scripts/verify_collection_lanes.py`
> does not exist in the repo** (the name came from the lost skill files) and Stage C must write it.
>
> **13. ▶ WHAT A SHIP STILL NEEDS (unchanged by this run).** The **product endpoint itself** is
> unmeasured. It needs (a) the HyDE cache ✅ built, (b) the **low-lane rename** (gemma) or nothing
> (nomic), (c) the **§I68 client-side-RRF fix** if the run is to be free of that tolerance, then the
> **scratch-index product-endpoint run** (plan §3) — retrieval-only first, then the full run with
> synthesis + judge (~70 min, 5,434 judge calls per §I64). ⚠️ And the **full re-ingest is a separate
> owner decision**: ~58.6 min ingest + 8.9 h cards + 1 h 6 m graph + every derived collection +
> the intent-classifier retrain.
>
> ## ▶ SESSION 14 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **1. ✅ §I70 — THE EMBEDDER SCREEN RAN, AND THERE IS A WINNER.** Plan
> `.hermes/plans/2026-10-24-p1-embedder-screen-hyde-cache-and-finetune-plan.md` §1. Instrument §I63's
> cross-embedder experiment, extended: corpus fixed (doc `7ba61432`, 3,489 in-window chunks), exact
> brute-force cosine, 133 gold queries, endpoint **paired ceiling-normalised R@20**, **HyDE off**,
> **no LLM calls, no writes**. Probe `logs/p1/step10/embedder_screen.py`, artifact
> `logs/p1/step10/embedder_screen.json` (sha256 `990e400f…`), independent aggregation
> `…_verifier.py`, reviewer pack `…_verifier_extract.json`.
>
> | arm | ceiling-norm R@20 | Δ vs qwen3@1024 | Δ vs nomic@768 |
> |---|---|---|---|
> | qwen3@1024 *baseline* | 0.293934 | — | — |
> | nomic@768 *baseline* | 0.433930 | +0.1400 (§I63, reproduced) | — |
> | **gemma@768** | **0.480410** | **+0.186476 [+0.1333, +0.2397]** | **+0.046480 [+0.0170, +0.0760]** |
> | gemma@128 | 0.410032 | +0.116098 | −0.023898 *(straddles 0)* |
> | mpnet@768 | 0.306226 | +0.012292 *(straddles 0)* | −0.127704 |
>
> **The rule:** a candidate must beat **BOTH** baselines with a CI excluding 0 before a re-ingest is
> even costed. **`gemma@768` is the only arm that passes** — and it passes on both contrasts. mpnet
> (NLI, not retrieval) loses to the incumbent, exactly as predicted.
>
> **2. ⚠️ THE ADOPTION COST IS THE 64d LANE.** EmbeddingGemma has **no 64d MRL slot** (its smallest is
> **128**), and at 128 it is *not* better than nomic@768 (−0.0239, unresolved). So a gemma re-ingest
> means **a new named vector at 128** — a change of width *and* model in the funnel's fast first
> stage — plus a re-index of every derived collection. The win is at **full dimension 768**.
>
> **3. ✅ VERIFIERS: all TWELVE pass, four of them EXACT reproductions of registered rows** — §I60's
> d=1024 (V3), §I59's `new_fulldim` (V4) and `new_mrl64` (V5), §I63's arm N (V11). Plus: the whole
> screen was **run three times** and all three artifacts agree on every per-query arm score (A-vs-A
> across runs), and a **second, independently written stdlib aggregation** re-derives every aggregate,
> endpoint and decision field with **0 mismatches**. ✅ **Independent verifier `deleg_1dd4aa6a`
> (`openai/gpt-oss-20b`, model confirmed from the run's `manifest.json`): 10/10 CONFIRMED**, but it was
> **cheap (4 API calls, 39 s) so it is NOT banked** — the substantive half is the mechanical evidence.
> ⚠️ **Its one finding was REAL and is FIXED: V1 skips qwen3, so the INCUMBENT's query-side prefix was
> the one prefix nothing asserted.** (Indirectly pinned by V3/V4/V5/V11, but indirect is not asserted.)
> **V12** now asserts `embed_query` == cluster(`instruction + text`) at cos **1.000000**, raw cos
> **0.818934**; the screen was **re-run** so the artifact matches the probe revision. Artifact is now
> sha256 **`990e400f…`**. **Still nothing committed** — that is an owner call.
>
> **4. ⚠️ NEW FINDING, REGISTERED NOT MEASURED — the project's Nomic MRL truncation may not be
> Nomic's.** `NomicEmbedder._truncate` / `cluster_embedder.mrl_slice` do a **plain slice + re-normalise**;
> Nomic's own model card prescribes **`F.layer_norm` over the full 768 dims BEFORE the slice**. Different
> functions ⇒ **every Nomic-64d number in the register is under the project's convention**. Do not
> "fix" it without re-measuring — §I59's rows were produced this way. (In §I70.)
>
> **5. ▶ NEXT, IN ORDER.** (a) **Owner decision on the re-ingest** — cost it honestly (58.6 min ingest
> + 8.9 h cards + 1 h 6 m graph + `derivative_artifacts` 73,406 + `concept_embeddings` 7,427 + the
> intent classifier + RAPTOR + ColPali + §I58's `_REPOINT` map; a new embedder means new chunk ids, so
> **all** of it). (b) If yes: **ONE** pre-registered product-endpoint run, **HyDE on and frozen** —
> which needs **plan §2's HyDE cache first** (it does not exist today; `evaluate_rag.py:190` calls the
> LLM per query, so every arm's query vector is nondeterministic — the §I68 class). (c) Run the §I66
> stage decomposition alongside it (base → funnel → cross-encoder → generator) to show whether the
> better embedder fixed the full-dimension **ranking** lane or just moved the loss. (d) Plan §4's
> domain fine-tune is the remaining lever if the re-ingest is declined. (e) Carried forward unchanged:
> §I56's DA lane (one-variable test), the §I68 client-side-RRF fix, §G2's V5 build, §I55's
> exclude-from-metrics follow-on, §I58's `gold-003` caveat, §I53 item 6, and **whether to commit
> session 13's work (still uncommitted)**.
>
> **6. ▶ NEXT SESSION — THE CHUNKING QUESTION, PRE-REGISTERED AND COMMITTED. Read
> `.hermes/plans/2026-10-24-p1-chunking-filter-ab-preregistration.md` FIRST; it is the spec.**
> The owner's position is that the NEW corpus's chunking is better on the merits; the register's only
> relevant number points the other way (Nomic: old 0.498722 cnorm / new 0.433930). §I63's 0.0648
> residual mixes **chunking + content-filter state + chunk count**, and none has been isolated.
> **Arm 1 isolates the content-filter state**, because it is the one of the three that can be varied
> with **no parse, no re-chunk and no re-embed** — the filter only changes *which chunks are in the
> candidate pool*, over vectors already stored. Two arms (control = the shipped pool; treatment =
> that pool minus the **263** chunks the CURRENT `content_filter` rejects — ⚠️ computed from the
> **TEXT**, not the stale stored `is_content`, which reads 5), endpoint **paired ceiling-normalised
> R@20**, primary embedder **gemma@768**, secondary **qwen3@1024**, guards **C1–C6**.
> ⚠️ **Report `chunks/page` in every arm** — page-deduped recall scores a page at its best chunk's
> rank, and it is **6.68 old vs 4.07 new**, a 64 % difference in chances. ⚠️ **A negative is
> interpretable**: removing a high-ranking TOC chunk from a page can *lower* that page's score.
> Pre-registration committed **alone** as **`aa4b55b`**, before the harness exists.
> **Deliverables:** `logs/p1/step10/chunk_filter_ab.{py,json}`, `…_verifier.py` (independently written,
> `--check`), the §I71 register entry, and a verifier dispatched **with** the run
> (`openai/gpt-oss-20b`, read-only — this session's shell returned empty stdout with exit 0).
> Then arm 2 = `min_chunk_tokens`, arm 3 = `semantic_threshold`, arm 4 = late chunking (36 min/arm).
>
> **Last updated: 2026-10-24, session 13. ✅ THE DOWNSTREAM WIDTHS ARE MEASURED — **BOTH LEVERS ARE
> NULLS** at the product endpoint (the fusion width W, and the re-score cut L), at ample power. The
> chain §I65 → §I66 → this is closed. Read `IMPROVEMENTS.md` §I67 (VOID → re-registration → result),
> §I68 (a product defect), §I69 (a harness float leak) first.**
>
> ## ▶ SESSION 13 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **1. ✅ THE RESULT — BOTH DOWNSTREAM WIDTHS ARE NULLS.** Task 1 from session 12, built, run, re-run
> and verified. Paired Δ **R@20 ceiling-normalised** (§I58), n=133, on the product path:
>
> | contrast | what it moves | result |
> |---|---|---|
> | **W1 − C** (width, PRIMARY) | W 100 → 300 | Δ **+0.0032**, CI [−0.0164, +0.0227] **UNRESOLVED** |
> | **W2 − C** (width, sensitivity) | W 100 → 500 | Δ **+0.0027**, CI [−0.0171, +0.0224] **UNRESOLVED** |
> | **L1 − W2** (cut, PRIMARY) | L 500 → 1000 | Δ **+0.0025**, CI [−0.0024, +0.0074] **UNRESOLVED** |
> | **L2 − W2** (cut, sensitivity) | L 500 → 2000 | Δ **+0.0029**, CI [−0.0021, +0.0078] **UNRESOLVED** |
>
> **Per the pre-registered rule NEITHER ships** — both recorded **measured-and-unresolved**. Power was
> ample, not the limit: SD_d(W1) 0.115 → required n for δ=0.05 is **21**; SD_d(L1) 0.0289 → **2**. The
> effect is ~15× below δ. Secondary (readable, but not the endpoint): **MRR RESOLVES POSITIVE** for the
> width (+0.0935, CI [+0.0559, +0.1311]) while **context_precision RESOLVES NEGATIVE** (−0.0075 /
> −0.0083) — a wider pool reorders the pool, not the product. **This closes the chain: §I65 (the
> prefetch is a null) → §I66 (the fusion output is the binding constraint) → a raised ceiling is still
> not recall.** ⚠️ Not production numbers (HyDE off, prefetch pinned at 2000) — quote the delta.
>
> **2. ⚠️ §I67 — THE FIRST RUN WAS VOID, AND WHY.** It failed its own load-bearing guard E4 (the
> negative control must be bit-exact): 1,064 comparisons, 2 mismatches, **max_abs_diff 0.0** — on
> `ovw-041` arm C's pool was 95 and arm N's 94. **Every metric was bit-exact; only a pool size
> differed**, and it reproduced (six identical C-config repeats gave 95/95/95/94/94/95). ⚠️ **The first
> attribution was WRONG and is corrected here:** it was NOT the ANN — every lane (`dense_64`, `sparse`,
> `colbert`) is deterministic 6/6, and `exact=True` / `hnsw_ef=512` changed nothing. **See §I68.**
> **Disposition:** re-registered with **E4′ (metrics-only; diagnostics reported, not voiding)** —
> a disambiguation of the original wording ("every METRIC"), justified by a **measured** floor (30
> queries × 4 repeats → R@20 c-norm spread **0.000000**), **not** a relaxation. The re-run **PASSED
> E4′** (0 metric mismatches, max_abs_diff 0.0). The VOID artifact is preserved as
> `logs/p1/step10/downstream_widths_ab_firstrun_VOID.json`.
>
> **3. ⚠️ §I68 — QDRANT'S SERVER-SIDE RRF FUSION IS NON-DETERMINISTIC (a product defect, registered not
> fixed).** Identical inputs, identical lane results, different fused output: `gold-052` returned **6
> distinct candidate sets in 6 runs**, `gold-004` 5/6, `gold-078` 3/6. It is **sparse** downstream
> (30 queries × 4 repeats → 0 metric spread; the VOID run's only trace was one pool size) but it **is**
> the root cause of §I67 and it makes **any** A/B on this path depend on a tolerance. **The fix already
> exists in-repo:** `store._rrf_merge` is a *client-side* RRF — moving the funnel off Qdrant's
> `FusionQuery` onto it would make the funnel deterministic. ⚠️ That is a change to the product path
> (ties may reorder), so it needs its own before/after and its own entry — **not** a silent swap.
> ⚠️ **Do NOT reach for `exact=True`:** the ANN is already deterministic.
>
> **4. ⚠️ §I69 — A HARNESS FLOAT LEAK, FOUND BY E5.** `compute_retrieval_metrics` returns **`ndcg` as
> `np.float64`** (all other metrics are plain `float`); `np.float64` IS a subclass of `float`, so
> `json.dumps` writes it silently and the type is **lost on read**. numpy's and CPython's tie rounding
> differ, so the artifact's summary is **not re-derivable from its own per-query array** at 3 tie keys
> (1e-6, one secondary metric, **no endpoint affected** — `all_queries` re-derives byte-identically).
> **Fixed at the point of record** (`_f()` coercion in the harness). ⚠️ **The fix needs a re-run to give
> a fully clean artifact**; the conclusion does not depend on it.
>
> **5. ▶ NEXT SESSION — READ THE NEW PLAN FIRST: `.hermes/plans/2026-10-24-p1-embedder-screen-hyde-cache-and-finetune-plan.md`.**
> It carries the doctrine, the embedder screen spec, the HyDE cache spec, the fine-tune stage, and what
> is explicitly OUT of scope. The short version:
>
> - ⚠️ **DOCTRINE (§0) — explore cheap, confirm powered.** The widths work burned three ~1-hour runs
>   confirming a null a 40-query screen had already indicated. **The resolution floor at n=133 is
>   ~0.020** (`1.96·0.115/√133`), so **any knob with a plausible effect < ~0.02 is out of scope for this
>   gold set** — record it, do not re-test it. And **not every finding is an effect size**: §I47/§I49/§I68
>   are bugs needing a fix, not a power analysis.
> - **§1 THE EMBEDDER SCREEN (~15 min, do first).** §I63's exact-cosine oracle, 133 queries, HyDE OFF.
>   Four models, each at its OWN smallest MRL slot **and** full dim: Qwen3-1024 (incumbent) ·
>   Nomic-768 (§I63's known-best, +0.1400) · embeddinggemma-300m (MRL 512/256/128 — **no 64d**) ·
>   mpnet-base-nli-matryoshka (has 64d, NLI not retrieval). Rule: a candidate must beat **BOTH**
>   Qwen3-1024 AND Nomic-768 before a re-ingest is costed. It is an **oracle** screen, not the product.
> - **§2 THE HYDE CACHE (parallel, small build).** There is **no cache today** (`evaluate_rag.py:190`).
>   Cache the **TEXT keyed by query id, not the vector** — it is embedder-independent, so one cache
>   serves every candidate and the re-ingest. Freeze model + prompt; loud on a miss (§I25). Do **not**
>   wire it into the screen.
> - **§3 AFTER A WINNER:** cost the re-ingest (58.6 min ingest + 8.9 h cards + 1 h 6 m graph + all
>   derived collections), then **ONE** pre-registered product-endpoint run (HyDE on and frozen) plus the
>   **§I66 stage decomposition** (base → funnel → cross-encoder → generator) to show whether the
>   embedder fixed the full-dim ranking lane or just moved the loss.
> - **§4 THE DOMAIN FINE-TUNE (stage 3, a BUILD).** Owner's point, and it is measured: generic
>   embedders lose here. **The training set already exists** — 29,321 `question` cards each paired with
>   its source chunk (~29k synthetic (query, passage) pairs in physics). Validate on the SAME §I63
>   instrument; expect leakage (card questions are generated from the passages); compare against the
>   §1 **winner**, not the incumbent. GPU job — hours, not minutes.
> - ⚠️ **OUT OF SCOPE (§5):** sub-0.02 knobs; **the widths (§I67 closed them — do not re-test, including
>   "more candidates from DA/graph/overview pooled at the fusion lane")**; an **all-lanes-at-once**
>   matrix (§I56's unattributability defect); ⚠️ ~~the **graph lane** (Memgraph is DOWN — 7687 refused
>   — and `hop_distance` is a constant 0)~~ — **CORRECTED 2026-10-24 (session 16), see §I75: Memgraph
>   is UP on `localhost:7687` (Docker `synapse_memgraph`), and the lane is REACHABLE AND SERVING.
>   The "DOWN" reading probed the CLUSTER IPs; the code and `.env` point at localhost.** What still
>   stands is `hop_distance` = a constant 0 (a **code** defect, §G5/§I2) — so the lane is no longer
>   excluded on an infrastructure premise, and reachability is **not** contribution (§I56). The visual
>   lane still needs ColPali data for the new doc.
> - **Also carried forward:** the §I68 client-side-RRF fix (own plan; also removes the instrument
>   nondeterminism); §I56's DA lane (one-variable test); §G2's V5 build (signed off, not built); §I55's
>   exclude-from-metrics follow-on; §I58's `gold-003` caveat; §I53 item 6 (the stale §G2 artifact); and
>   **whether to commit session 13's work (currently uncommitted)** and whether to re-run once more so
>   the artifact is self-consistent (§I69's 3 tie keys — the conclusion does not depend on it).
>
> **6. ✅ BUILT AND VERIFIED IN THIS SESSION (not committed).** NEW `dense_rescore_limit` (500) and
> `da_fetch_k` (100) settings, both defaulting to the shipped value; the fusion width **W** is
> `mmr_candidates` **and** `reranker_fetch_k` moving together (§I66's binding constraint — raising
> either alone does NOT widen the fusion). `tests/test_downstream_widths.py` (17 tests, mutation-proven:
> hardcoding the cut fails 2; recoupling the DA lane fails 1). Harness `logs/p1/step10/downstream_widths_ab.py`,
> verifier `…_verifier.py` (E2–E9, `--extract` for the reviewer pack), run script
> `run_downstream_widths_ab.sh`. Artifacts: **`downstream_widths_ab.json` (the re-run — the result)**
> and **`downstream_widths_ab_firstrun_VOID.json` (preserved as evidence of the VOID)**. Plan
> `.hermes/plans/2026-10-23-p1-downstream-widths-and-embedder-screen-plan.md` §1 updated;
> pre-registration `.hermes/plans/2026-10-23-p1-downstream-widths-ab-preregistration.md` and
> **re-registration `.hermes/plans/2026-10-24-p1-downstream-widths-ab-reregistration.md` (E4′)**.
> **Suite 636 passed / 4 failed / 6 skipped** — the 4 are the documented pre-existing set.
> ⚠️ The pre-registration was committed WITH the results (owner decision), not alone first — §I67.7.
>
> **7. ⚠️ A DESIGN FINDING THAT SURVIVES THE VOID.** The re-score cut is **inert by construction** at
> the shipped **W=100** (smoke test: Δ exactly 0.0000, W/L/T 0/0/3 identical) — the fusion emits only
> 100 candidates, so raising L just reshuffles candidates far below the cut. The cut arms were
> re-registered (before the run) to run at **W=500** and be read against **W2**. **A knob downstream of
> a saturated cut is inert (§G1's defect); testing it requires the upstream width to admit it.**
>
> **8. ⚠️ STILL OPEN, UNCHANGED:** §I56's DA lane (one-variable test); the **embedder screen** (deferred
> by the owner); §G2's V5 build (signed off, not built); §G5/§I2 (`hop_distance` constant 0); §I55's
> exclude-from-metrics follow-on; §I58's `gold-003` caveat; §I53 item 6 (the stale §G2 artifact).
>
> ## ▶ SESSION 12 — WHAT HAPPENED, AND WHAT IS NEXT
>
> **1. ✅ §I61's PRE-REGISTERED A/B RAN AND THE LEVER IS A NULL — `IMPROVEMENTS.md` §I65.** The
> pre-registration (`.hermes/plans/2026-10-23-p1-i61-prefetch-limit-ab-preregistration.md`) was
> **committed alone first (`e0fed5e`)** — that is what makes it a pre-registration. Four arms, one
> variable (`cfg.dense_prefetch_limit`, a NEW config field; default 1000 = the shipped value), 133
> queries, paired, on the product retrieval path, **HyDE off** so every arm shares one query vector:
>
> | arm | limit | R@20 |
> |---|---|---|
> | C control | 1000 | 0.431769 |
> | T treatment | 2000 | 0.434590 — Δ **+0.0028**, CI [−0.0006, +0.0062] **UNRESOLVED** |
> | S exact search | 3489 | 0.434849 — Δ **+0.0031**, CI [−0.0004, +0.0065] **UNRESOLVED** |
> | N negative control | 1000 | **bit-exact vs C: 0 mismatches / 931 metrics, max_abs_diff 0.0** |
>
> W/L/T **6/2/125**; **Hit@20 identical to 4 dp in every arm**; every secondary metric and every
> per-type cut UNRESOLVED. **The mechanism reproduced at full sample** (64d lane pool coverage 0.815136
> @1000 → 0.960627 @2000 → 1.0000 @3489, vs §I61's 40-query screening 0.804127 / 0.971526 / 1.0000) —
> so §I61 was right about the mechanism and the product endpoint still did not move. **Per the
> pre-registered rule the change does NOT ship; §I61 is recorded measured-and-unresolved.** Power was
> ample, not the limit (SD_d 0.020013 → required n for δ=0.05 is **1**; the effect is ~17× below δ).
> ⚠️ **Not production numbers** (HyDE off by design) — quote the delta, not the absolute.
>
> **2. ✅ §I66 — THE LOSS IS THE 100-SLOT FUSION. `logs/p1/step10/rescore_cut_curve.{py,json}`.** A
> direct (prefetch N × re-score cut L) ceiling, computed by **exact brute force at both dimensions**
> (no ANN, no Qdrant scoring, no RRF/dedup/MMR), so it isolates the cut instead of confounding it. It
> **reproduces §I65's mechanism arm exactly** (0.8151 at N=1000/L≥N vs M1's 0.815136; 1.0000 at
> N=3489/L=3489) — different code path, same number, which is what makes the grid trustworthy. The
> decomposition, of a query's reachable labelled pages:
>
> | stage | production (N=1000) | exact prefetch (N=3489) |
> |---|---|---|
> | 64d lane | 0.8151 | 1.0000 |
> | → after the full-dim re-score cut (L=500) | 0.7478 | 0.8286 |
> | → after the fusion (RRF + dedup + MMR to 100) | **0.6048** | **0.6071** |
> | → after the cross-encoder to top-20 | 0.4318 | 0.4348 |
>
> ⚠️ **The session's own hypothesis was WRONG and the probe refuted it.** The re-score cut was named as
> the prime suspect for the 8 queries whose pool held none of their labelled pages even at exact
> prefetch; **5 of the 8 have ALL their labelled pages inside the L=500 candidate set and 2 more are
> partially inside** (`gold-004`'s best labelled chunk ranks **127th of 3,489**, `gold-052`'s 470th)
> — only `gold-078` (rank **1325**) is entirely lost. **So the loss is downstream of the cut.**
> ⚠️ **And this explains the null mechanistically: at exact prefetch the fusion's own loss GROWS
> (0.143 → 0.222).** Feeding the fusion more candidates does not grow the pool, because the fusion's
> output width (`fetch_k` = 100) does not grow. **The binding constraint is the 100-slot fusion
> output.** The cut is still a large *ceiling* lever at exact prefetch (L=1000 +0.0980, L=2000 +0.1486,
> L=3489 +0.1714, all RESOLVED) — but a raised ceiling is not recall, and the fusion's 0.143–0.222 has
> never been attributed between RRF, page dedup and MMR.
>
> **3. ⚠️ THE GOLD SET NEEDS NO PRUNING — the premise that "41 queries have answers out of bounds" is
> not right.** `n_reachable == 0` on **0 of 133** queries: no query is unanswerable. **38 of 133** have
> *at least one* label outside the window (98.51 % of all 3,631 labels are reachable), **30 of the 38
> are overview** — a label-*size* artifact (§I58: overview averages 73.8 labels, so any single miss
> caps the query). Dropping them would take n 133 → 95 for a bias **ceiling-normalisation already
> removes**; and the §I65 null survives on the uncapped subset alone (n=95, ΔT−C +0.0036, CI
> [−0.0012, +0.0083], UNRESOLVED). **§I58's repair list stands: re-point `gold-003` and optionally the
> two ±1 queries — 1–3 queries, not 38.**
>
> **4. ▶ NEXT TASKS, IN ORDER.**
> 1. **The DOWNSTREAM WIDTHS — the re-score cut L (500) and `fetch_k`/MMR (100). This is the lever
>    §I66 points at, and it is the only one left with a measured ceiling.** Both are hardcoded in
>    `store._qdrant_search` / `search_with_das`; make them settings as `dense_prefetch_limit` was, then
>    run a **pre-registered A/B** on the product endpoint. Arms to pre-register: L ∈ {500, 1000, 2000}
>    with the prefetch at 2000 (so the lane is not the cap), and `fetch_k`/MMR ∈ {100, 200}. Expected
>    ceilings from §I66: L=500 → 0.8286, L=1000 → 0.9266, L=2000 → 0.9773 at exact prefetch.
>    ⚠️ **Do not assume the ceiling becomes recall** — §I65 is the cautionary case.
> 2. **§I56's DA lane — settle it with a ONE-VARIABLE test** (DA live vs DA off, everything else
>    pinned). The owner's "keep as-is" stands; §I56 measured −0.0262 on top-20 R@20 and §I64 moved
>    −0.0274 from §3d, consistent but **unattributed** (four things changed at once). ⚠️ **The DA lane
>    enters the same fusion stage §I66 fingers**, so it is worth reading the two together.
> 3. **The EMBEDDER SCREEN — owner decision this session: defer it, and do NOT force a fixed 64d.**
>    Use **each model's own available MRL slice**. Candidates, all already served by the cluster
>    (verified live on `10.0.10.70:8123/embed-text`, not assumed):
>    `Qwen/Qwen3-Embedding-0.6B` (incumbent, 1024d, MRL 32–1024, MTEB-ml-v2 64.33) ·
>    `nomic-ai/nomic-embed-text-v1.5` (768d, MRL 64–768 — the §I63 known-best on this corpus, +0.1400
>    over Qwen3) · `google/embeddinggemma-300m` (768d, **MRL 512/256/128 — there is NO 64d slot**;
>    308M params, MTEB-ml-v2 61.15 @768d) · `tomaarsen/mpnet-base-nli-matryoshka` (768d, MRL
>    **768/512/256/128/64**, trained with `MatryoshkaLoss`, base ~110M, NLI-trained). ⚠️ **"EmbeddingGemma-500m"
>    does not exist** (the family is `embeddinggemma-300m` and the un-loaded `embeddinggemma-2`, 740M).
>    ⚠️ **The endpoint IGNORES a `dimensions` param** — slice client-side and re-normalise. ⚠️ **The
>    §I62 prefix trap applies to EmbeddingGemma too** (`"task: search result | query: "` /
>    `"title: none | text: "`, asymmetric) — the cluster is a generic passthrough and applies none.
>    Instrument: §I63's cross-embedder experiment (fixed corpus, swap only the embedder, exact
>    brute-force cosine, 133 queries, ceiling-normalised paired R@20; 124 s, no LLM, no writes).
>    Pre-register the rule: **a candidate must beat BOTH Qwen3-1024 AND Nomic-768** before a re-ingest
>    is even costed. **Nothing here is a recall lever** — §I65/§I66 show coverage is not the constraint;
>    the embedder can only help through full-dimension *ranking*.
> 4. **§G2's V5 build — SIGNED OFF, not built.** Plan
>    `.hermes/plans/2026-10-22-p1-g2-v5-ablation-plan.md` (level 2 primary, equal 2-slot budget, C/D
>    only if the primary resolves, null ⇒ recorded-and-not-wired). Steps 1a–1c: new
>    `community_summary_search.py`, a CLI, and `--community-summaries` **off** by default.
> 5. **§G5/§I2** — `hop_distance` is a constant 0, so "multihop" is nominal.
> 6. **Smaller, still open:** §I55's exclude-from-metrics follow-on; §I58's caveat that `gold-003`'s
>    label is a TOC line that will die at the next re-ingest; and **§I53 item 6** — the committed §G2
>    artifact (`g2_summaries_2026-10-22.json`) **predates the code that made it**
>    (`prompt_chars_by_level: {}` and the old `planned_leaf_map_calls`), so regenerate it or mark it
>    stale before quoting it.
>
> **5. ⚠️ VERIFIED IN TWO LABELLED HALVES — NOT `[verified]`, AND THE REASON IS IN THE REGISTER.**
> ⚠️ **The tool-using reviewer cannot run on this gateway.** `openai/gpt-oss-20b` died twice on the
> multi-turn tool loop — once truncated after reading the 255 KB artifact whole, once with
> `Unknown role: assistant<|channel|>commentary` (its own control tokens leaking into the replayed
> history). The verdict was therefore taken as **(a) mechanical evidence** — an independent
> aggregation reproduces every summary value from the per-query array (grid 18/18, deltas 6/6,
> histogram, counts; probe re-run byte-identical, `038e12ba…`) — and **(b) a single-turn reviewer**
> (no tools, data embedded) on the *method*, which confirmed single-variable design, the negative
> control's meaning, the endpoint choice, no cross-arm leakage, and HyDE-off's legitimacy; its one
> UNVERIFIED item (a silent-failure audit) was adjudicated — two claimed defects do not occur, the
> third is guard E4 itself. ⚠️ **`[verified]` is deliberately OFF on both commits**: the arithmetic
> half is the author checking the author, so per the standing rule this is partial verification, not
> verification. Details: `IMPROVEMENTS.md` §I65 and §I66.
>
> **Committed:** the `dense_prefetch_limit` field + its single read site, `tests/test_dense_prefetch_limit.py`
> (8 tests, mutation-proven: 5 of 8 fail on restoring the hardcoded 1000), both probes and their
> artifacts, the harness, the two compact verifier extracts, the §I65/§I66 register entries, this
> HANDOFF block, and `.hermes/plans/2026-10-23-p1-downstream-widths-and-embedder-screen-plan.md`.
>
> **Last updated: 2026-10-22, session 11. ✅ SESSION 10'S VERIFIED WORK IS COMMITTED; §I57's DURABLE
> FIX LANDED; ✅ PHASE E RAN (see §I64).** Read this block next, then session 10's below.
>
> ## ▶ SESSION 11 — WHAT HAPPENED, AND WHAT IS IN FLIGHT
>
> **1. ✅ SESSION 10'S VERIFIED WORK IS COMMITTED — 4 commits, working tree clean.** `5ac90b5`
> §I53a · `6f17abe` §I55 · `9c99f88` §I58 (the three label re-points) · `75ac3f2` §I63 + the
> session-10 measurement register (§I56/§I57/§I59/§I60/§I62) and the two plans. **Nothing pushed.**
>
> **2. ✅ §I57's DURABLE FIX — `evaluate_rag.py` now emits a per-query JSON twin.** NEW
> `write_run_artifacts` writes the `.md` (content unchanged, still the regression baseline) **and**
> a `.json` carrying `config_snapshot`, an `integrity` block, `aggregated` and the per-query
> `results` — so a cross-run comparison pairs by query id instead of parsing markdown (which is
> the only reason `compare_old_vs_new_index.py` had to). `_json_default` converts numpy scalars
> and **re-raises** for anything else (loud, never silently stringified). 3 new tests in
> `tests/test_eval_integrity.py` (20 there). **Three guards proven to discriminate by mutation** —
> drop the json write → 3 fail; neuter the encoder → 1; make unknown types silent → 1; each on its
> own assertion, tree restored byte-identical. ⚠️ **Verifier `deleg_e9e29bc5` returned `completed`,
> CONFIRMED on C1–C3**, but it was **cheap (19 s, 3 reads, no test run) with pack-relative line
> numbers → NOT banked**; the mutation runs are the evidence. ✅ **COMMITTED `0a5bead`** — the
> verdict's C6 refutation (which blamed this diff for §I55's pre-existing `return 3`) is recorded
> as **void** in §I57.
>
> **3. ✅ PHASE E RAN AND ITS NUMBERS EXIST — the run that had never happened (owner decision,
> session 11).** The authoritative FULL `evaluate_rag.py` (retrieval + synthesis + judge) on
> `knowledge_base_v2`, pre-registered **before the run finished**
> (`.hermes/plans/2026-10-22-p1-phaseE-preregistration.md`, `36e28f3`) and harnessed
> (`logs/p1/step10/run_phaseE.sh`). Artifact
> `data/eval_results/p1-phaseE-v2_2026-10-23_0650.{md,json}`; log
> `logs/p1/step10/phaseE_run_2026-10-22_2127.txt`. 4,180 s compute, **5,434 judge calls / 0
> failures**, 167/167 synthesis. **All five guards pass**, including **E5 — the `aggregated` block
> re-derives EXACTLY from the per-query `results` array** (the §I57 fix's first production use).
> `reranked_metrics_valid=false` with **gold-004** named (exit 3); reported both ways, and it moves
> the headline by ≤0.003, so the conclusion does not depend on it. **Full entry: `IMPROVEMENTS.md`
> §I64.**
>
> **THE ANSWER, stated as narrowly as the evidence allows:** the missing half is now measured and it
> is a **TIE** — Faithfulness **0.637** vs the deployed system's **0.661**, Answer Relevance
> **0.852** vs **0.852**. On retrieval, ceiling-normalised (§I58), the new index still captures
> **less** of its headroom (R@100 **0.7058** vs **0.7259**; R@20 **0.4453** vs **0.5275**) while
> **raw R@100 rose** (+0.035) and **MRR fell** (−0.121). **There is no generation-side improvement
> to show** — the rebuild's hoped-for gain did not appear where the product ships. ⚠️ The §D12
> comparison is **descriptive, not causal** (a different run on a different day; the six §I57
> confounds plus this run's own).
>
> ✅ **PHASE E'S ARTIFACT VERIFIER RETURNED — `deleg_4bdde8d0`, 7/7 CONFIRMED, no defects.** Unlike
> the session's two cheap verdicts, this one was substantive (**15 API calls, 104.6 s**): it
> **counted 133 metrics rows / 34 negatives out of `results` itself** and **recomputed every overall
> mean from `results`**, matching the `aggregated` block exactly — so guard **E5 has an independent
> re-derivation, not just the author's**. ✅ The **harness + pre-registration** were verified
> 2026-10-22 (`deleg_9533b2a5`, 7/7 CONFIRMED, no defects) — a cheap verdict (8 API calls, 32 s)
> with misattributed line numbers, so **not banked**: C7 was re-proven by the author
> (`set -euo pipefail` + `tee` propagates a non-zero exit; the control without `pipefail` swallows
> it, so the check can genuinely fail).
>
> **4. ✅ OWNER DECISIONS TAKEN 2026-10-22 (session 11):** **V5 is SIGNED OFF as written** (level 2
> / res 0.5 primary, equal 2-slot budget, C/D only if the primary resolves, null ⇒
> recorded-and-not-wired); **§I56 keeps the DA lane AS-IS** (no change); **Phase E runs next.**
>
> **5. ▶ NEXT TASKS, IN ORDER (written 2026-10-23, session 11).**
>
> 1. **§I61 — RAISE THE 64d PREFETCH LIMIT. This is the cheapest lever found so far, and it is new
>    this session.** The sweep had **run but was never written up**; §I61 now records it, re-derived
>    from the per-query array. At the production limit 1000 the new index's `dense_64` lane covers
>    **0.804127** of the reachable pool against **0.932368** full-dim — a **0.128** gap, ~**30×** the
>    old index's 0.004. Raising the limit recovers it (1500 → 0.904495, 2000 → 0.971526), **at 2000
>    the dimension stops mattering** (64d 0.971526 vs full-dim 0.971966), and at limit = every
>    in-window chunk **both lanes are exactly 1.0000** — so the loss is **entirely the filtered-HNSW
>    search path**. **Code/config only: no re-ingest, no model change, no new named vector.** ⚠️ It
>    is a **40-query screening subsample**, so it needs its own **pre-registered** A/B (raise vs
>    current, 133 queries, paired, product endpoint) before it ships.
> 2. **§I56's DA lane — settle it with a ONE-VARIABLE test** (DA live vs DA off, everything else
>    pinned). The owner's "keep as-is" stands; this is why it is worth re-opening: §I56 measured
>    **−0.0262** on top-20 R@20 and Phase E moved **−0.0274** from §3d — consistent, but **four**
>    things changed at once, so it is not attributed.
> 3. **§G2's V5 build — SIGNED OFF, not built.** Plan
>    `.hermes/plans/2026-10-22-p1-g2-v5-ablation-plan.md` (level 2 primary, equal 2-slot budget, C/D
>    only if the primary resolves, null ⇒ recorded-and-not-wired). Steps 1a–1c: new
>    `community_summary_search.py`, a CLI, and `--community-summaries` **off** by default.
> 4. **§G5/§I2** — `hop_distance` is a constant 0, so "multihop" is nominal.
> 5. **Smaller, still open:** §I55's exclude-from-metrics follow-on; §I58's caveat that `gold-003`'s
>    label is a TOC line that will die at the next re-ingest; and **§I53 item 6** — the committed §G2
>    artifact (`g2_summaries_2026-10-22.json`) **predates the code that made it**
>    (`prompt_chars_by_level: {}` and the old `planned_leaf_map_calls`), so regenerate it or mark it
>    stale before quoting it.
>
> **Last updated: 2026-10-22, session 10. ✅ THE CROSS-EMBEDDER EXPERIMENT RAN — ALL SIX VERIFIERS PASS.
> §I59's Effect 2 is 68 % ATTRIBUTED to the embedder (a residual of +0.0648 is still unattributed —
> §I63). §I55 IS FIXED and verified. Read `IMPROVEMENTS.md` §I63 first, then §I55 and §I53a.**
>
> ## ▶ NEXT SESSION — START HERE (written 2026-10-22, session 10)
>
> **1. ✅ §I63 — THE CROSS-EMBEDDER EXPERIMENT. THE FULL-DIM REGRESSION IS THE EMBEDDER.**
> `logs/p1/step10/cross_embedder_experiment.{py,json}` (sha256 `7c5e92f9…`). **124 s wall, no LLM
> calls, no writes.** Hold the corpus fixed (new doc `7ba61432`, 3,489 in-window chunks), swap ONLY
> the embedder, exact brute-force cosine (not Qdrant — §I60 measured up to 18.5 % HNSW loss), 133
> queries, endpoint R@20 paired + ceiling-normalised:
>
> | arm | embedder | R@20 | R@100 | R@500 | R@1000 |
> |---|---|---|---|---|---|
> | **Q** | Qwen3 1024d | 0.2939 | 0.5691 | 0.9230 | 1.0000 |
> | **N** | Nomic 768d | **0.4339** | **0.6290** | 0.9273 | 1.0000 |
>
> **Δ R@20 = +0.1400, CI [+0.0907, +0.1893], W/L/T 26/60/47 → RESOLVED, N > Q.** Secondary R@100
> +0.0599 [+0.0132, +0.1067] → also RESOLVED. So **Qwen3 ranks worse than Nomic on this corpus**, and
> §I59's Effect 2 — the full-dimension ranking loss no instrument could attribute — is **68 % the
> embedder**: swapping the embedder alone recovers **+0.139996** of the **−0.204788** drop. ⚠️ **A
> residual of +0.064792 (31.6 %) is NOT attributed** — it mixes the chunking, the content filter and
> the chunk count, so **§I59's Effect 2 is 68 % attributed, not closed**. ⚠️ **The chunking itself is
> already BUILT** (E1 semantic chunking / E2 parents / E3 late chunking, landed 2026-10-17 and in this
> corpus) — what is missing is its **attribution**, plus one knob never re-tuned
> (`min_chunk_tokens = 32`). ⚠️ **This does NOT license a revert** (plan §1: a revert is a
> re-ingest + a re-index of 73,406 DA + 6,065 concept points + the intent classifier). **The embedder
> is the larger half of the lever; choosing it is an owner decision, not taken.**
>
> **All six verifiers pass** — X1 (cluster Nomic reproduces the LOCAL `NomicEmbedder`: doc cos
> **1.000000** prefixed / **0.937749** raw, query cos **1.000000** — §I62's prefix trap, confirmed
> live in the run that depends on it); **X2** (arm Q reproduces §I60's d=1024 row **all four k
> exact**); **X2b** (arm Q reproduces §I59's `new_fulldim` row **all four k exact**); X3 (identical
> chunk→page mapping); **X4** (A-vs-A at batch 64 vs 128 → **max_abs_diff 0.0**); X5 (0 errors).
>
> **⚠️ §I63 ALSO CORRECTS A PLAN PREMISE.** The plan's §5 says *"§I59's k is in PAGES, §I60's is in
> CHUNKS"* — **wrong in its mechanism**. Both apply `k` to a deduped **page** list; what differs is
> the **pool depth** feeding it: §I59's is the **top-1000 chunks** (production's prefetch depth,
> `store.py:416`), §I60's is **every chunk** (`max(KS)` = 5000). Identical at k=20/100 — so the
> pre-registered endpoint is convention-free — diverging at k≥500 (§I59 R@1000 **0.926563** vs §I60
> **1.0000**). X2 and X2b reproducing **both** rows exactly is what settles it; §I60's entry and the
> artifact both carry the correction.
>
> **2. ✅ §I55 — THE RERANKER'S SWALLOW IS FIXED** (counted, surfaced, and the run refuses to certify
> a reranked metric). `reranker.py` counts `fallbacks`/`last_fallback`; `evaluate_rag.py` takes a
> per-query **delta** (the reranker is a singleton), carries `reranker_fallback` onto each result, and
> `main()` writes `reranker.reranked_metrics_valid=false` + a Run-integrity warning + **exit 3**.
> `tests/test_reranker_fallback.py` (7); **both guards proven to discriminate by mutation** (removing
> the counter increment fails 1; neutering the delta fails 2; tree restored byte-identical).
> ⚠️ **Verifier dispatched, pending.** ⚠️ **Not done deliberately:** the fix does NOT exclude a
> fallback query from the metrics — that changes denominators. Registered as the follow-on.
>
> **3. ⚠️ THREE VERIFIERS DISPATCHED 2026-10-22 (session 10).** Reviewer `openai/gpt-oss-20b` for all
> three (resolved from `hermes config get delegation` — provider `custom` @ `10.0.10.70:8000`, empty
> fallback chain; independent of the author's DeepSeek family, and of the subject in each case):
> - ✅ **§I53a (the §G2 checkpoint) — `deleg_dd8d2c29` RETURNED: 8/9 confirmed, no silent wrong answer.**
>   C9 (a suite-wide test count) is `unverified` because the brief carried the diff, not the suite —
>   measured separately as 606/4/6. The verdict was cheap and its cited line numbers are fabricated,
>   so it was **not banked**: all five cited test names were confirmed to exist and **all four guards
>   were re-proven by mutation on my own run** (1/2/3/1 tests fail respectively, each on its own
>   assertion; tree restored byte-identical). **`[verified]` — commit it.**
> - ✅ **§I55 (the reranker swallow) — VERIFIED AS OF v2 (`deleg_297b66a3`, 7/8 confirmed).** v1
>   (`deleg_8c4afa8b`) explicitly dismissed the empty-`results` case as harmless; a probe showed a
>   clean HTTP 200 with `{"results": []}` (or no `results` key) returns **0 chunks**, moves no
>   counter, logs only at DEBUG, and is then **averaged in as a total miss** while the artifact says
>   `reranked_metrics_valid: true` — worse than the swallowed exception, which at least returns the
>   unranked pool. Guard added, 2 new tests, mutation-proven (removing it fails 2). **`[verified]` —
>   commit it.** (v2's `if not chunks: return []` observation was correctly judged unreachable.)
> - ⚠️ **§I63 (the cross-embedder probe and its numbers) — `deleg_ac1507f8` RETURNED: 8/8 confirmed.**
>   Cheap verdict (2 calls, 16 s) with pack-relative line numbers, so **not banked**: the endpoint
>   arithmetic was recomputed from the artifact's own per-query array (mean 0.139996, CI
>   [0.090737, 0.189255], W/L/T 26/60/47 — exact) and the query↔ranking ordering guarantee was
>   re-proven with a probe that CAN fail (shuffled server response, including across batches).
>   **`[verified]` — commit it.**
>
> Evidence packs: `~/.hermes/cache/scratch/{g2_checkpoint,i55,i63}_review_pack.md`. **Do not commit the
> two pending items on the author's own evidence if either returns UNVERIFIABLE or times out.**
>
> **4. Suite: 608 passed / 4 pre-existing fail / 6 skipped** (`logs/p1/step10/session10_suite_v2.txt`,
> 224 s; the earlier run in `session10_suite.txt` was 606/4/6, before §I55's second-path tests). The 4
> are the documented pre-existing set (`test_phase1` ×1, `test_phase2` ×1, `test_splade` ×2) — **none
> of those files imports `reranker` or `evaluate_rag`**, and `pyproject.toml`/`uv.lock` are untouched.
>
> **5. ⚠️ STILL OPEN, UNCHANGED:** §G5/§I2 (`hop_distance` is a constant 0); §I57's **Phase E** (the
> new index has NEVER had generation metrics — the only thing that can answer "is the new system
> better?"); the **V5 plan** is written and unsigned (`.hermes/plans/2026-10-22-p1-g2-v5-ablation-plan.md`,
> four signoff points in its §6); §I56's DA-lane disposition (owner decision, not taken); §I55's
> exclude-from-metrics follow-on; and §I57's registered durable fix (`evaluate_rag.py` should emit
> per-query JSON, not only `.md`).
>
> **Last updated: 2026-10-22, session 9. ✅ The §G2 monitoring gap is FIXED, the DA lane is MEASURED,
> and V5 has a plan. Read `IMPROVEMENTS.md` §I53a, §I55 and §I56 first.**
>
> ## ▶ NEXT SESSION — START HERE (written 2026-10-22, session 9)
>
> **1. ✅ §I53a — THE §G2 BUILD IS CHECKPOINTED AND LOGS PER CALL.** NEW
> `src/pdf_ingestion/summary_checkpoint.py` + `checkpoint=`/`on_call=` on `summarize_communities` +
> `--no-resume`/`--progress-every` on `build_community_summaries.py`; `data/summary_cache/` gitignored.
> The key is the **run** `(document, model, seed, resolutions, prompt budget, prompt digests)` and each
> entry is reused only on a matching **input digest** — so a re-attempted child invalidates its parent.
> A community whose calls returned empty is `ok=False` and is **re-attempted**. 18 new tests; **four
> guards proven to discriminate by mutation**. Suite **599 passed / 4 failed / 6 skipped** — the 4 are
> the documented pre-existing set. ⚠️ **NOT COMMITTED — the independent verifier has not run.**
>
> **2. ✅ §I56 — THE DA LANE IS MEASURED, AND THE ANSWER IS NOT UNIFORM.** First measurement on v2
> (133 queries, `logs/p1/step10/da_lane_ablation.py`). The lane answers on **every** query (100 hits),
> adds **+41.5 %** to the pool, and survives into the top-20 on **104/133** — so it is **not inert**.
> But on the product endpoint it **RESOLVES NEGATIVE**: top-20 R@20 0.4385 → 0.4123, Δ **−0.0262**,
> CI **[−0.0485, −0.0038]**, W/L/T **5/27/100**. The average hides a sign change: **overview RESOLVES
> POSITIVE** (+0.0449, CI [+0.0326, +0.0572]) and factual carries −0.0696 (unresolved).
> ⚠️ The "candidate set" number is **post-MMR**, not the raw union — DA can lower it by displacing
> dense candidates through MMR. **OWNER DECISION, NOT TAKEN:** keep as-is / gate by `query_type` /
> turn off. §A2 is now **closed**.
>
> **3. ✅ NEW §I55 — THE RERANKER SWALLOWS ITS OWN FAILURES.** `ClusterCrossEncoderReranker.rerank`
> catches everything, logs `RERANKER DISABLED`, and returns the pool **unranked** — while the eval
> artifact records `reranker.enabled=true`. Measured: **1/133** v2 queries rejected (500,
> `gold-004`), **deterministically per query**, and the trigger is **content token-density, not
> payload size** (a 50,773-char pool rejected while 78,187 passed). Any metric that depends on the
> reranked **order** carries this silently. **Not fixed** — it is a source change needing its own
> verifier.
>
> **4. ▶ V5 — THE PLAN IS WRITTEN, FOR SIGNOFF.** `.hermes/plans/2026-10-22-p1-g2-v5-ablation-plan.md`.
> Spine: **equal fixed slot budget** across arms (V3's two-population finding makes any recall race
> inflatable by construction), **generation metrics primary**, A-vs-B pre-registered with C/D as
> sensitivity, and a mandatory **A-vs-A negative control**. Four signoff points in its §6 — the level
> choice, the slot budget, whether C/D run, and confirming the null disposition. **Nothing is built.**
>
> **5. ⚠️ §G5/§I2 IS STILL OPEN — §G2 is NOT the last graph work.** `graph_search`'s `hop_distance`
> is a **constant 0**, so "multihop" is nominal. §G4 (global/local/drift modes) stays a brainstorm
> item. (An earlier statement in this session that V5 closed all graph work was **wrong**; the §G2
> plan's own §6 lists §G5 as remaining.)
>
> **6. ⚠️ THE COMMITTED §G2 ARTIFACT PREDATES THE CODE THAT MADE IT.**
> `logs/p1/step10/g2_summaries_2026-10-22.json` carries `prompt_chars_by_level: {}` and the **old**
> field name `planned_leaf_map_calls` — both changed by the §I54 fix in `84ee66f`. §I53 cites it as
> evidence. §I44's class; register or regenerate before quoting it.
>
> **7. ✅ §I57/§I58 — "IS THE NEW SYSTEM BETTER?" HAS NO VALID ANSWER YET.** The one cross-system pair
> (`knowledge_base` vs `knowledge_base_v2`, same 133 queries) is confounded **six** ways; scripted in
> `logs/p1/step10/compare_old_vs_new_index.py`. Paired: R@100/R@20/Hit@20/NDCG@20 **unresolved**,
> **MRR RESOLVES NEGATIVE (−0.0987)**, Ctx.Prec **+0.0263** and overview R@20 **+0.0283** both
> **RESOLVE POSITIVE**. ⚠️ **The new index has NEVER had generation metrics** — the only v2 run was
> retrieval-only. **Phase E is the missing run.**
> §I58: the gold set needs **no rebuild** — the labels are index-independent and **better served** by
> the new index (achievable max **0.8806 → 0.9545**). Ceiling-normalised, the old index captures
> **72.6 %** of its headroom and the new one **65.6 %** — the index improved and the retriever did not
> capture it. 3 labels re-pointed (see 10).
>
> **8. ✅ §I59/§I60/§I62 — THE BASE LANE, DECOMPOSED.** `dense_64 @1000` is the only stage facing the
> whole corpus. §I59: MRL-64 R@1000 ceiling-norm **0.9224 → 0.8151 (resolved −)**; full-dim **−0.0092
> (unresolved)**; full-dim **R@20 −0.2026 (resolved −)**. Two effects: a **64d truncation penalty 8.7×
> worse for Qwen3** (0.1115 vs 0.0128 — clean, measured within each index) and a **full-dim ranking
> loss that is NOT attributable** (embedder + chunking). §I60: the pool is **saturated at 1000 chunks
> at EVERY dimension (R@1000 = 1.0000)** → **128d is dead**, the width is irrelevant to coverage.
> §I62: ⚠️ **the cluster serves Nomic but does NOT apply its task prefixes** — unprefixed gives
> **cosine 0.949**, prefixed **1.000000**.
>
> **9. ▶ NEXT SESSION — THE CROSS-EMBEDDER EXPERIMENT.** Plan written, nothing run:
> `.hermes/plans/2026-10-22-p1-cross-embedder-experiment-plan.md`. Hold the corpus fixed, swap only the
> embedder (new corpus × Nomic vs new corpus × Qwen3, both already costed) to separate **"Qwen3 ranks
> worse"** from **"the re-chunk ranks worse"** — the only thing that can attribute §I59's Effect 2.
> **Under 10 minutes wall, no LLM, no writes.** Five verifiers, an A-vs-A negative control, and a
> pre-registered rule. **Everything needed is in the plan's §5 — do not re-derive the timing, the
> prefix trap, the k-units or the ceiling rule.**
>
> **10. ✅ §I58 — THREE LABELS RE-POINTED (re-point, not rebuild).** `gold-003` [30]→[34],
> `gold-009`/`gold-010` [99]→[98], each by an **exact text match in the re-ingested index**. Lives in
> `scripts/build_gold_v2.py` as a `_REPOINT` map so it survives a rebuild; a rebuild was verified to
> reproduce the file with **only** those changes (166 answerable + 34 negatives = 200, unchanged).
> ⚠️ `gold-003`'s answer is a **TOC line** and §I39 excludes TOC at ingest — the stored `is_content`
> predates §I39, so it is reachable today and **will die at the next re-ingest**. It should probably be
> dropped.
>
> ⚠️ **STILL UNCOMMITTED AND UNVERIFIED:** the §G2 checkpoint fix (§I53a — `summary_checkpoint.py`,
> `community_summaries.py`, `build_community_summaries.py`, 18 tests) has **not** had its independent
> verifier. Suite was clean (**599 pass / 4 pre-existing fail / 6 skip**) but per the standing rule a
> step with no verifier is not done. The reviewer is on the cluster, reachable while the tunnel is up.
>
> **Last updated: 2026-10-22, session 8. ✅ §G2 IS BUILT AND VERIFIED — V1/V2/V4/V6 ALL PASS, V3
> READ BY EYE. The one thing left in §G2 is **V5, the ablation — its endpoint — and it needs a
> retrieval path that does not exist yet.** Read `IMPROVEMENTS.md` §I52, §I53 and §I54 first — they
> carry the whole session.**
>
> ## ▶ NEXT SESSION — START HERE (written 2026-10-22, session 8)
>
> **WHERE §G2 IS NOW.** The summary tree is built: `logs/p1/step10/g2_summaries_2026-10-22.json`
> (**597 non-empty summaries**, 19 min 42 s wall, **597 LLM calls**, **0 empty returns**, 0 batched,
> 24 skipped). Harness `logs/p1/step10/run_g2_summaries.sh`; verifier
> `logs/p1/step10/g2_verify_summaries.py` → **ALL CHECKS PASSED** (14 checks, re-derived from the
> graph with a fake LLM, never read back off the artifact). The gate was re-run on the **post-§G3
> merged graph** and **PASSES**: res 1.0 Q=**0.687197** vs rewired null **0.349002**, surplus
> **+0.338195** (ratio 1.969), n=202, **Leiden connected at every resolution**, Louvain disconnected
> at 1.0; nesting 0.8911 / 0.8394. The builder reproduces the gate's Q and nesting **exactly**.
>
> **1. ▶ V5 — THE ABLATION. This is the next action, and it is §G2's ENDPOINT.** The plan's
> pre-registered rule (`2026-10-22-p1-g2-community-summaries-plan.md` §4): *G2 is built iff V1 passes
> **and** V2 holds **and** V5 shows a positive contribution on overview queries; if V5 is null or
> negative, G2 is recorded as measured-and-negative and the summaries are **not** wired into
> retrieval* — the disposition §G1 received. **The summaries are NOT wired into anything yet** — the
> artifact is a JSON file and no code reads it. So V5 is a BUILD (a retrieval path) plus a
> measurement, and it wants its own plan + owner signoff before it is written.
>
> ⚠️ **READ V3'S FINDING BEFORE DESIGNING V5 — it changes what a positive would mean.** The leaf
> partition is a **two-population mixture**: **166 of 218 leaves have ≤ 5 concepts** (76 %, ~4 % of the
> text — one passage each), while **34 have > 50 concepts** and **8 have > 200** (p90 = 108, max 336),
> holding 95 % of the text. The summaries themselves are good — factual, source-grounded, no phantom
> clusters — but the large ones read as *"most of mechanics"* / *"thermodynamics + kinetic theory +
> quantum statistics"*: accurate grab-bags, not topic units, and several overlap heavily. **The
> hierarchy has no middle granularity** (chapter/topic level), which is exactly the level community
> summaries exist to supply. So a naive page-level recall ablation would be **misleading**: a single
> 542-chunk summary covers hundreds of pages and would "win" on coverage alone — the §G1 ablation's
> equal-pool defect, in the other direction. Design the arms with a **fixed slot budget** and prefer
> the **generation** metrics (the judge's Faithfulness / Answer Relevance, which step 4 already
> measures) over a recall number the summaries can inflate by construction.
>
> **2. §G3's endpoint is NULL and the endpoint is INERT — recorded, not pending.** Owner disposition
> 2026-10-22: keep the merge, record as measured-and-null. The pre-registered median did not move
> (1.0 → 1.0) and **could not**: >100 of 200 queries would need a top-5 median ≥ 2 and **14** do.
> **Do not read this as "entity resolution does not help retrieval".** Re-pre-registering a sensitive
> endpoint is an owner decision, NOT taken.
>
> **3. Everything on the cluster needs the tunnel UP** (`10.0.10.65` Qdrant, `10.0.10.70`
> embed/LLM) — it was up this session (`utun4`).
>
> ⚠️ **Every §G3/§G2 command needs `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2`.**
> `.env` leaves `QDRANT_HOST` blank, so the default is the **LOCAL embedded** store — a run without
> the override silently targets the wrong store (§I49 Finding 1). `run_g2_summaries.sh` now asserts it.
>
> ⚠️ **§I52 — THE §G2 SUMMARISER IS NOT THE GRAPH BUILD'S EXTRACTOR.** `community_summaries._default_llm`
> → `call_llm` → **`cfg.openai_model` = `openai/gpt-oss-20b` (131,072-token context)**. The graph
> build's concept extraction runs **`Qwen/Qwen3-VL-8B-Instruct` (15,000)**. The first pre-flight
> measured the wrong one and a design decision was made on a false premise before it was caught. Both
> contexts are in `/v1/models`; real physics text is **4.49-4.53 chars/token** (filler text measures
> 6.23 — 40 % optimistic). **Measure the model the phase runs, not the one another phase runs.**
>
> ⚠️ **§I52 — TWO SILENT FAILURES WERE FOUND ON THIS PATH AND FIXED.** A failed LLM call wrote an
> **empty summary that still counted as a call** (§I25's class: a total loss that reads as a success) —
> now counted and the CLI exits non-zero; and the dry run reported **403 parent communities as "no
> source material"** when they are parents the dry run cannot generate. Both fixed with tests proven
> to discriminate (14 tests in `tests/test_community_summaries.py`).
>
> ⚠️ **REGISTERED, NOT FIXED — the §G2 build has no checkpoint and logs nothing per call.** 597
> sequential LLM calls; an abort at call 596 loses all of it, and nothing in the log could distinguish
> "healthy and slow" from "stalled" (§I23's lesson). It completed in 20 min, so it was not paid this
> time. Fix it before the next §G2-scale LLM phase.
>
> ⚠️ **§I54 — THE INDEPENDENT REVIEW FOUND A REAL DEFECT, AND THE FIRST TWO ATTEMPTS AT IT WERE
> WORTHLESS.** The §G2 diff was reviewed by `openai/gpt-oss-20b` (pin re-checked live). The defect:
> `planned_leaf_map_calls` counted leaf *prompts* but was compared to a real run's `map_calls` — which
> on the live corpus is **0** against a plan of **218** — so the test passed only because its fixture
> batched every community. Fixed (`planned_leaf_prompts` vs a level-scoped `leaf_prompt_calls`), and
> fixing it exposed a third wrong comparison of the same number. The reviewer's "infinite reduce
> loop" is **false as the code stands** (proved: the guard is load-bearing only when summaries do not
> shrink, and removing it hangs the new test). Two earlier dispatches returned UNVERIFIABLE ×10
> because the prompt lacked the artifact / the claims — **that is no verdict, never a pass**, and the
> rule for embedding them is now in Session hygiene.
>
> **Earlier in the file:** the session-7 §G3 block, the session-6 rebuild block, and session 3's
> "START HERE" list below it — all superseded by the above. `IMPROVEMENTS.md` §I49–§I54 are the
> authoritative record.
>
> **Last updated: 2026-10-21, session 6. ✅ THE GRAPH REBUILD IS DONE AND VERIFIED — item 3 is closed.**
> The document-keyed graph clear it needed is built, verified and **applied** (`f007f85`; the graph read
> back **0/0/0/0** from Bolt, independently of the script's own table), and the rebuild finished
> **22:54:37** — **1 h 6 m 21 s**, `failed_chunks = 0`, **3,533 chunk nodes** (§I21 confirmed in the
> OUTPUT: the 263 non-content chunks are gone), log `logs/p1/step10/graph_rebuild_2026-10-21.txt`. Read
> item 3 for the full outcome. Also this session: the derived collections moved onto the dense lane
> (`6773022`, §I12/§I13), which found and fixed **§I47 — the graph lane was dead on every multihop query
> in `evaluate_rag.py`**. The next graph steps are **§G3, then §G2** — and as of **2026-10-22 they are
> planned with per-step verifiers and an explicit parallelization order**:
> `.hermes/plans/2026-10-22-p1-graph-lanes-execution-index.md` (the index), plus
> `…-i12-derived-collections-dense-lane-plan.md`, `…-g3-entity-resolution-plan.md`,
> `…-g2-community-summaries-plan.md`. **§I12/§I47 EXECUTED AND CLOSED 2026-10-22 (both lanes on the
> dense lane, verified — §I49); §G3's lever and §G2's gate both re-measured on the rebuilt graph.**
> ⚠️ These four plan files are **untracked** — commit them or the pointer breaks on a fresh clone.
> Session 5 landed: §I23's checkpoint + the `resume` plumbing that makes `resume=False` reachable
> from the CLI, §I23(d)'s device selection, **§I23(c) — the extraction-model comparison (the
> single-chunk "10 vs 5 concepts" did NOT reproduce; the real difference is 3.2-3.6× latency)**,
> §G1 **closed** as measured-and-negative, and the standing rule that a verifier must differ from the
> author **and the subject, in model family** (`README.md` → "Verifier at every step"). Earlier: §G2
> (Leiden), §I21 (the Phase 3 E5 filter), and the §G1 ablation — which came back NEGATIVE.
> **▶ The extractor is `Qwen/Qwen3-VL-8B-Instruct`** (owner decision, item 2) and **the rebuild is
> LIVE** — §I21 is confirmed live inside it (3,533 chunks, not 3,796).
>
> ## ▶ NEXT SESSION — START HERE (written 2026-10-21, session 3)
>
> **0. ✅ DONE 2026-10-21 (session 4) — the `resume` plumbing is verified and committed.** It is what
> makes §I23's checkpoint reachable: `src/pdf_ingestion/store.py`
> (`generate_phase3_artifacts(..., resume=True)`, passed through to `build_graph`),
> `scripts/run_phase3.py` (`--no-resume`, plus a "Failed chunks" column and a loud warning when it
> is non-zero — parity with `run_phase2.py`), `tests/test_phase3.py` (the `Capturing` stub gains
> `resume`, plus `test_resume_is_threaded_to_the_graph_builder`). Without them the documented
> `resume=False` was **unreachable from the CLI**. Commit **`aaef7fe`**, verifier
> `openai/gpt-oss-20b` deleg `deleg_92c32542` **8/8 confirmed**, no findings; all three files
> byte-identical after the review. The new guard was proven to discriminate (deleting only the
> `resume=resume,` line fails it). Suite: **490 pass / 4 fail / 6 skip**.
> Deliberate: `force_graph` does NOT imply `resume=False` — a forced rebuild still reuses completed
> extractions, because the extraction is the expensive half.
>
> **0d. ✅ DONE 2026-10-21 (session 4) — §I23(d): the embedder's device selection is availability-
> checked** (commit `1fa94a3`; verifier `openai/gpt-oss-20b` deleg `deleg_f2fda5ec`, **8/8
> confirmed**, no findings). `NomicEmbedder` used `"cuda" if use_gpu else "cpu"` with no check, so
> `USE_GPU=true` on this Mac (measured `cuda False / mps True`) asked for a device that does not
> exist. NEW `resolve_device()`: CPU when `use_gpu` is false (early return, before `import torch`),
> else CUDA → MPS → CPU, and it cannot raise. `_load()` now passes the resolved device for any
> non-cpu value, where before only the literal `"cuda"` was passed. NEW `tests/test_embedder_device.py`
> (8 tests, offline); reverting the resolver to the old semantics fails 4 of them. Suite with it:
> **498 pass / 4 fail / 6 skip**. ⚠️ Registered, not fixed: `colpali_embedder.py:87` is the sibling
> site — it *does* check `torch.cuda.is_available()` so it cannot crash, but it has no MPS path.
> ⚠️ The first review attempt (`deleg_fb8151cc`) is **void** — interrupted, every shell call
> returned exit 0 with EMPTY stdout (the broken-terminal behaviour this session hit), so it burned
> 180 s on a full suite run and tripped the heredoc approval gate. The re-dispatch forbade
> `terminal` and embedded the evidence; that is the verdict above.
>
> **0a. ✅ DONE — §G1 + §G2 built, measured, INDEPENDENTLY VERIFIED** (commit `e78a7ef`; module
> `src/pdf_ingestion/graph_analytics.py`, 18 unit tests, two probes). Deps taken per the owner
> decision: `python-igraph` + `leidenalg`.
> - **§G2 — the gate re-run on LEIDEN, and it PASSES.** `logs/p1/step10/g2_leiden_gate.py`:
>   res 1.0 **leiden Q=0.601572** vs rewired null 0.286665 → surplus **+0.314907** (ratio 2.0985),
>   n=149, **connected at every resolution**. The Louvain comparison arm reproduces the §I33
>   before-arm number **exactly (0.589597)**, so Louvain→Leiden is a single-variable change — and
>   Louvain is disconnected at 1.0 (the same 75-member community §I33 caught) and at 2.0.
>   Hierarchy nesting 0.87 (0.5→1.0) / 0.74 (1.0→2.0). Two runs byte-identical.
> - **§G1 — PPR behaviour measured** (`logs/p1/step10/g1_ppr_probe.py`): seeded at the §I32
>   gold-062 top-8, of which **only 5/8 resolve — three are spelling variants of "kinetic energy"**,
>   i.e. the §G3 defect showing up live. Top-20 PPR vs top-20 degree overlap = **2** (the
>   personalization is not degenerating into global centrality); 95.9 % of the mass within two hops.
>   `sum(v) = 8.229619` and the output is **deliberately not normalised** — `W = D⁻¹A` is
>   row-stochastic, not doubly stochastic, so mass is conserved only on a regular graph. Pinned by
>   a test; do not "fix" it.
> - **Verifier: `openai/gpt-oss-20b`, deleg `deleg_c16ecc8d`, model confirmed from the run's
>   `manifest.json` (not from a note).** §G2: **7/7 confirmed**, and the reviewer re-ran the probe
>   itself and compared byte-for-byte. §G1: **6/7 confirmed**; C6 (byte-identity) returned
>   **unverified** because the child invoked the probe through `browser_exec` under Hermes's own
>   python 3.14 instead of the project venv — a tool-selection failure, not a disagreement. C6 was
>   then closed by my own re-run (three-way byte identity, sha256 `7ec42e40…`) — **mechanical
>   evidence, not a second opinion**; the record keeps those apart.
>   ⚠️ **Adjudicated 2026-10-21:** a later docs review REFUTED this record, on the grounds that the
>   raw transcript showed only 3 claims for §G1. **The refutation is void** — the transcript
>   truncates (`…(+1044 chars)`) and exposes only C1–C3; the delivered result carried all seven.
>   The record above is correct, and the reviewer's *concern* (that the record be checkable) is now
>   met by the Session-hygiene rule on transcripts.
> - ⚠️ **§G1's verifier 4 — the retrieval ABLATION — RAN 2026-10-21 and the answer is NO.**
>   Commit `50af094`; `logs/p1/step10/g1_ppr_ablation.py`. 40 multihop gold queries; both arms see
>   the same seeds and the same candidates, differing only in the ranking key. **PPR re-ranking does
>   not beat the fixed-hop ranking** — every metric UNRESOLVED, and the point estimates are
>   *negative* where the test can discriminate: MRR −0.0339 [−0.0877, +0.0199], R@3 −0.0484
>   [−0.1042, +0.0075], R@5 −0.0319, R@10 −0.0111; only R@20 is positive (+0.0097) and that is the
>   cut that bites on 7 of 40 queries. ⚠️ **The test is structurally weak and the artifact says so:**
>   the graph lane's candidate pool is median **7.5 chunks / 6.5 pages**, so a page-level Recall@k
>   above the pool is inert — both arms identical *by construction*. Quote `meta.power.cut_bites_at_k`
>   (k=3: 35/40 · k=5: 24/40 · k=10: 13/40 · k=20: 7/40) before trusting any k. **NOT tested:**
>   candidate *expansion* — §G1's verifier 4 specifies a ranking comparison, so a null here is not
>   evidence PPR cannot help the lane. This ran on the graph **before** the §I21 rebuild, so it is a
>   before-arm. Verifier: `openai/gpt-oss-20b`, delegs `deleg_2c9e024e` (9/9) and `deleg_96b9a464`
>   (5/5) — plus a **spot-check of my own**, because 4 of the 9 were confirmed from the probe's
>   *docstring* rather than its code.
> - **✅ §G1 CLOSED 2026-10-21 (owner) — measured-and-negative; the fixed-hop ranking stays.** The
>   ablation says re-ranking alone is not the lever, and every cut that can discriminate points
>   negative. The **expansion arm is NOT authorised** — it is recorded as the one untested lever, not
>   a pending task. `graph_analytics.personalized_pagerank` remains in the tree, unit-tested and
>   probed, but imported by **tests and probes only, never by `src/`** (checked). **Do not re-run this
>   ablation unchanged and expect a different answer.**
>
> **0b. ✅ DONE — §I21: the Phase 3 graph build now applies the E5 filter** (commit `1c0ed6d`).
> `generate_phase3_artifacts` filtered nothing, so TOC/index lines were extracted as physics content
> and their concepts entered the graph (measured: a TOC fragment yielded 4 concepts) and were matched
> by `graph_search` at query time. The fix mirrors `generate_phase2_artifacts`, and additionally
> **refuses to build an empty graph** when every chunk is non-content. 3 new tests in
> `tests/test_phase3.py`, all three proven to discriminate (removing the filter fails 2, removing the
> guard fails 1). Verifier `openai/gpt-oss-20b`, deleg `deleg_98d6a755`: **5/5 confirmed**.
> **Takes effect on a graph REBUILD — which is the next step in the D1 order and is not yet run.**
> Also in that commit: the "verifier at every step" rule in `README.md` + Session hygiene, and the
> README test count corrected from a stale "135" to the measured 464 / 4 / 6.
>
> **0c. ✅ DONE — §I23: the Phase 3 graph build is checkpointed, and its failures are counted**
> (commit `50af715`; verifier `deleg_5fd5575a`, **9/9 confirmed**). NEW
> `src/pdf_ingestion/graph_checkpoint.py` (side-car JSONL, keyed on document + model + **prompt
> digest**; a FAILED extraction is never resumed as done), `build_graph(..., resume=True)` now
> returns **`failed_chunks`** — the honest count, where the old local reported 44 failures as
> "0 failed" — and `_extract_concepts` distinguishes a failed call from a chunk that genuinely has
> no concepts. 25 new tests, both guards proven to fail against the defect they are for. Memgraph
> remains the single write point. **NOT done in §I23:** part (c) the extraction-model choice
> (needs an output-quality comparison — owner call) and part (d) the MPS path for concept-name
> embedding.
>
> **▶ THE NEXT STEPS, in the settled D1 order** (filter → Phase 3 filter → harden → **rebuild** →
> §G3 → §G2):
> 1. ✅ **DONE — the three uncommitted files are verified and committed** (`aaef7fe`, item 0 above).
> 2. **§I23 (c) — MEASURED 2026-10-21 (`c596940`); the OWNER DECISION is the only thing left before
>    the rebuild.** (d) is **DONE** (`1fa94a3`, item 0d). The comparison ran: 24 real chunks, both
>    arms on the production prompt, **three runs** to measure the instrument's own noise
>    (`logs/p1/step10/i23c_extraction_model_compare.{py,json}`). **The 10-vs-5 concept gap that
>    started this did NOT reproduce** — at n=24 both arms sit at ~4.3-4.6 concepts/chunk, inside the
>    prompt's own 3-7 rule. What separates: **p50 latency 3.4× (10.1 s vs 3.0 s)**, prereq edges ~2×,
>    off-enum types 0 vs ~9 per 24 chunks. ⚠️ **The two things gpt-oss-20b does better are read by no
>    code path** — `graph_search` is a MENTIONS-only single-hop lookup, `PREREQUISITE_OF` is only ever
>    written, and nothing branches on `type` — while the latency is paid on every rebuild.
>    ⚠️ **The swap is one-way**: the checkpoint key includes the model.
>    **Decide: keep `openai/gpt-oss-20b` or switch to `Qwen/Qwen3-VL-8B-Instruct`.** The cost side is
>    derived, not measured: scaling §I23's measured **16 h 25 m** build by the measured p50 ratio
>    (**10.11-10.31 s / 2.83-3.16 s = 3.2-3.6×**) gives **≈4.5-5.1 h** — and that is an **upper bound
>    on the saving**, because it scales the whole build although only the extraction half is
>    model-bound (the concept-name embedding and the Memgraph writes are not).
> 3. **THE GRAPH REBUILD — ✅ DONE AND VERIFIED 2026-10-21 (session 6).** Launched 21:48:16, finished
>    **22:54:37** — wall **1 h 6 m 21 s**, against the 4.5-5.1 h projection and the 16 h 25 m the
>    gpt-oss-20b build took. It WAS preceded by a graph clear, which is now built, verified and applied.
>    - **Outcome — the run's own report, then INDEPENDENTLY counted from Bolt:** **`failed_chunks = 0`**,
>      and `MATCH` counts of **1 Document / 3,533 Chunk / 907 Page / 7,427 Concept / 14,407 MENTIONS /
>      22,799 RELATES_TO / 3,295 PREREQUISITE_OF**. The counts are **persisted** at
>      `logs/p1/step10/graph_rebuild_verify_2026-10-21.txt` (probe:
>      `logs/p1/step10/verify_graph_cleared.py`) — they were session-only for one round, and a verifier
>      was right to mark them UNVERIFIABLE until they were on disk. This is §I44's rule again.
>    - ✅ **§I21 IS CONFIRMED IN THE OUTPUT, not just the log: 3,533 chunk nodes, NOT 3,796.** The 263
>      non-content chunks (72 TOC + 186 index + 5 front matter, §I39) are absent from the graph, so the
>      TOC concepts §I21 measured entering it no longer exist.
>    - ⚠️ The run reported "14407 concept nodes" — that is **MENTIONS edges, not concepts** (§I22 again:
>      the label lies). The distinct concept count is **7,427**.
>    - **What moved, old → new** (both counted from Bolt): Concept 7,834 → **7,427**; RELATES_TO
>      37,300 → **22,799** (−39 %; per chunk 9.83 → 6.45); PREREQUISITE_OF 11,892 → **3,295** (−72 %;
>      per chunk 3.13 → 0.93 — §I23(c) measured that gpt-oss-20b emits more of these, and nothing reads
>      them). Concept density per chunk is essentially unchanged: 2.06 → 2.10.
>    - ⚠️ **This build embedded its concept names with the LOCAL 768d Nomic**, because the process
>      imported `graph_builder.py` at 21:48, before `6773022` switched that to the dense lane. So it is
>      self-consistent (768d into the 768d collection) — and when §I12's move is applied, the
>      **checkpoint makes the re-run cheap**: all 3,533 extractions are reused and only the
>      embed + upsert + write phases repeat (minutes, not the 62 min extraction took).
>    - ⚠️ **An 18-minute, 58× throughput stall hit mid-run (22:26 → 22:44) and recovered** — recorded in
>      §I23. `0 FAILED` survived it because the bounded retry recovered all four timeouts. The lesson:
>      **a single-request liveness probe read all-clear throughout the stall** (a real completion: HTTP
>      200 in 0.16 s), so read the RATE and the checkpoint, not a status code.
>    - ✅ **THE CLEAR — DONE 2026-10-21 (session 6).** NEW `scripts/clear_graph_document.py` +
>      `tests/test_graph_clear.py` (13 tests, offline), commit **`f007f85`**, verifier
>      `openai/gpt-oss-20b` deleg `deleg_9cfbf8dd` — **7/7 SOUND, no defects**. `clean_stale_graph.py`
>      cannot do this job (it keys staleness on "no points in Qdrant", and `7ba61432` **is** the live
>      collection), so the clear is keyed on **document id**: `DETACH DELETE` scoped to the ids for
>      Chunk/Page/Document, then the Concept nodes that **no surviving chunk** mentions. Dry-run is the
>      DEFAULT, `--yes` applies, and a `--doc-id` that is not in the graph is refused (exit 2) rather
>      than silently deleting nothing. ⚠️ Orphan detection is two-phase and **by name** — **all four**
>      single-query Cypher forms fail on Memgraph 2.18.1 (probed live; see §I45's sibling notes in the
>      script's docstring). **Applied:** 1 document / 3,796 chunks / 933 pages / 7,834 concepts removed;
>      an **independent Bolt read-back** (`logs/p1/step10/verify_graph_cleared.py`) confirms every node
>      and edge count is **0**. Evidence: `logs/p1/step10/graph_clear_2026-10-21.txt`.
>    - ⚠️ **The clear does NOT touch Qdrant.** `concept_embeddings` still holds **15,276** points
>      against a graph that now holds none — it accumulates across ingests and its payload carries no
>      document id, so the rebuild **ADDS** to it. That is the confound §G1's ablation recorded;
>      clearing it is a separate owner decision and was deliberately **NOT** taken (open decisions).
>    - **The run:** `logs/p1/step10/run_graph.sh` → `uv run python scripts/run_phase3.py --doc-id
>      7ba61432-… --graph-only`. ⚠️ `run_graph.sh` redirects nothing, so it must be launched with a
>      **new** filename — log is `logs/p1/step10/graph_rebuild_2026-10-21.txt`. The 2026-10-19 build's
>      `graph_build.log` is the artifact §I22/§I23 cite, and `>` would have destroyed it.
>    - ✅ **§I21 IS LIVE IN THIS BUILD, measured at launch:** the log reads *"skipped 263 non-content
>      chunk(s) (front/back matter)"* → it extracts for **3,533 chunks, not 3,796**. 263 = §I39's
>      measured **72 TOC + 186 index + 5 front-matter** chunks, **exactly** — the filter is doing what
>      it was measured to do. This is the rebuild's whole purpose; before it, TOC lines were extracted
>      as physics content (§I21).
>    - **Checkpoint:** `data/graph_cache/7ba61432__9e758046e4a15115.jsonl`, opened **fresh** (0 resumed —
>      a new key, as expected: the model changed). Confirmed growing: **354 → 460 lines in 61 s**.
>    - ⚠️ **ETA — measure, do not plan off the projection.** Observed at launch: **450/3,533 chunks in
>      288 s ≈ 1.56 chunks/s ≈ 94 chunks/min**, i.e. **≈38 min of extraction IF the rate holds**. That is
>      **≈4.0×** the 2026-10-19 build's own *early* rate (its log reads **500/3,796 in 21 min ≈ 23.6
>      chunks/min**), consistent with §I23(c)'s measured **3.2-3.6×** p50 latency ratio.
>      ⚠️ But that old build finished 3,796 chunks in **16 h 25 m = 3.85 chunks/min averaged over the
>      whole run** — its rate **degraded ~6×** as it went (§I23's shared-GPU contention). So ≈38 min is a
>      projection from the first five minutes, and 4.5-5.1 h is the pessimistic bound; **neither is the
>      answer — read the log.**
>    - **When it finishes:** read **`failed_chunks`** (the `run_phase3.py` column), not the exit code;
>      then **count in Memgraph** (§I22: the reported `concept_nodes` is MENTIONS edges, ~2× the truth).
>      Expect **3,533 chunk nodes**, not 3,796 — the 263 non-content chunks are correctly absent.
>    - ⚠️ **`force_graph=True` does NOT clear anything** — it only bypasses the "Document node already
>      exists" skip. The flag lives in **`generate_phase3_artifacts` in `store.py`** (parameter at
>      `store.py:1676`, the skip it bypasses at `store.py:1790-1805`) — **not** in `build_graph`, whose
>      signature has no such parameter (a reviewer looked for it there and reported the flag as
>      unimplemented). `build_graph` has **no delete step** (no `DETACH DELETE` anywhere in
>      `graph_builder.py`), and its writes are `MERGE … ON MATCH SET r.weight = r.weight + 1`, so
>      rebuilding over an existing graph would (a) keep every concept the old model produced and
>      (b) **double the `RELATES_TO` weights** — the §I43 duplication class, in the graph this time.
>      That is exactly why the clear exists; measured on the live graph before it: **7,834 concepts,
>      37,300 `RELATES_TO`, 15,619 `MENTIONS`**.
>    - ⚠️ **The extractor is `Qwen/Qwen3-VL-8B-Instruct`**, set per stage in `config.yaml` under
>      `concept_extraction` (owner decision 2026-10-21, item 2). Changing it changes the checkpoint key,
>      so a mid-build swap re-extracts everything. `run_graph.sh`'s settings gate used to print
>      `openai_model` (`openai/gpt-oss-20b`) while the build called Qwen — **fixed** in `d4a596b`
>      (§I45), so the log now names the extractor that actually runs.
> 4. Then **§G3** (entity resolution — §I30's lever: 1,186 merge groups, 34.4 % of the vocabulary),
>    then **§G2** community summaries.
>
> **OPEN OWNER DECISIONS:** (i) ~~**§G1**~~ **✅ CLOSED 2026-10-21 — measured-and-negative; the
> fixed-hop ranking stays, and the expansion arm is NOT authorised** (it remains recorded as the one
> untested lever, not a pending task — `graph_analytics` is imported by tests and probes only, never
> by `src/`); (ii) **§I34** — a re-ingest transition reports the graph lane as SKIP:
> non-blocking or a hard blocker?; (iii) **§A3** — card volume vs quality; (iv) whether `e78a7ef`
> should be amended now that §G2 is fully verified (it still carries no `[verified]` prefix, on
> purpose: §G1's ablation was outstanding at the time and has since returned a null — with §G1 now
> *closed*, this is decidable); (v) **NEW 2026-10-21 — should `concept_embeddings` be cleared as part
> of the rebuild?** It holds **15,276** points and the graph now holds **none**; it accumulates across
> ingests, its payload carries no document id, and the rebuild only ADDS to it. So after this build the
> collection will hold this run's concepts *plus* every earlier ingest's, and `graph_search`'s ANN can
> return a name the graph no longer holds (it then matches no `Concept` node and contributes nothing —
> the confound §G1's ablation recorded). Clearing it is cheap and the rebuild re-populates it, but it
> was **not** authorised by item 3, so it was NOT done. **It must be decided before the next graph
> rebuild, not after.**
> **✅ ANSWERED AND DONE 2026-10-22 — the drop is REQUIRED, not optional, and BOTH LANES ARE MOVED.**
> Qdrant cannot resize a collection in place; both `concept_embeddings` and `derivative_artifacts` were
> 768d while the query side is 1024d, so the §I12/§I47 fix (which moved them to the dense lane in code,
> `6773022`) was only half-landed until the **data** was dropped and recreated. **Both lanes are now on
> the dense lane and VERIFIED** — see `IMPROVEMENTS.md` §I49. `derivative_artifacts` 81,837@768d →
> **73,406@1024d** (`search_da` returns 20 hits, was 0); `concept_embeddings` 19,719@768d →
> **7,427@1024d** (`_find_concepts_scored` returns 8, was 0). `preflight.py`: **2 BLOCKER(S) →
> All checks passed**. ⚠️ **The store trap:** `.env` leaves `QDRANT_HOST` blank, so the default is the
> LOCAL Qdrant — every §I12 command needs `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2`
> or it silently targets the wrong store (§I49 Finding 1).
> **▶ Next: §G3** — its gate (the rebuild) is discharged and its lever is re-measured (§I49 Finding 2:
> 1,059 groups / 33.0 %, superseding §I30's before-arm). §G2's gate has also been re-run and PASSES
> (§I49 Finding 3), so §G2 is un-gated behind §G3.
>
> **1. ✅ DONE (2026-10-21 session 2) — §I43 fixed and B5 PASSES.** `save_raptor_tree` now deletes the
> document's RAPTOR points (and rows) before the upsert, and the 73 orphaned points were removed by
> `scripts/dedupe_raptor_points.py` (dry-run → `--yes`). `knowledge_base_v2` = **3,869 points** =
> 3,796 chunks + **73** RAPTOR, **0 orphans**; B5 exit 0
> (`logs/p1/step10/b5_raptor_verify_2026-10-21_post_dedupe.log`). New regression test proven to
> discriminate (14 vs 7 with the fix disabled).
> **Independent review ran** (`openai/gpt-oss-20b`, a different model; pin confirmed live): 5 SOUND /
> 1 DEFECT → verdict FAIL on the write ordering. **Adjudicated and recorded in §I43 — the ordering is
> kept deliberately** (it fails into *absence*, which B5 counts, not into *duplicates*, which is the
> silent failure §I43 removes), and the reviewer's proposed corrections are a no-op and a regression.
> What the review did land: the upsert failure is now **loud** (ERROR naming the state + the
> `--raptor-only` recovery) — pinned by a second new test.
> **Suite: 439 pass / 4 fail / 6 skip** (`uv run pytest tests/ -q -m "not slow"`, 194 s) — the 4 are
> the pre-existing documented failures, **no new failure**. ⚠️ Two earlier attempts at this number
> were lost to session interruptions, and one stalled at ~64 % because my own killed runs were still
> competing — **that was not a hanging test**: `tests/test_phase2.py` alone completes in 57 s.
> **Still uncommitted** — see the "Uncommitted" line below. Detail: §I43, §I44 in `IMPROVEMENTS.md`.
>
> **2. NEXT — build §G1 (PPR) + §G2 (community detection) — OWNER DECISION TAKEN 2026-10-21: use
> LEIDEN, not Louvain, "as that's the improvement over louvain", with PPR and community detection
> "and all resolution as per the syllabus".** This closes §I33 (Louvain vs a Leiden dependency) —
> **take the dependency.** The syllabus spec, read from the course materials:
> - **Deps:** `uv add python-igraph leidenalg`. Both are required: `leidenalg` operates on `igraph`
>   objects, and networkx's own `leiden_communities` is a backend-dispatch stub that raises
>   `NotImplementedError` (§I33). Write the `nx_to_igraph()` translation the course's Lab 2 uses.
> - **Resolutions: 0.5, 1.0, 2.0** — the loop in `Labs/Week_5/ms_graphrag_tutorial/docs/
>   graph_analysis.md` §1 ("Loop over Resolutions 0.5, 1.0, 2.0") and its finite-zoom section
>   (0.5 = few broad communities, 2.0 = many tight ones).
> - **Hierarchy: 2–4 levels** (`Week_Plan/week-5-summer-lesson-plan.pdf`: *"Microsoft GraphRAG's
>   hierarchy is typically 2–4 levels deep precisely because that is how many levels of genuine
>   structure a real entity graph holds. Ask for more and you are summarizing noise."*).
> - **The modularity gate, per Lab 2:** *"Measure modularity at each level and compare against a
>   degree-preserving random rewiring of the same graph — structure is a surplus over chance, so
>   compute the chance."* Report **both** numbers at every resolution.
> - **Assert every community is connected** — Leiden's guarantee over Louvain, and the reason the
>   owner chose it.
> - **PPR (G1):** seed at the query's concepts and iterate `v(k+1) = (1−λ)·W·v(k) + λ·v(0)` with
>   **λ = 1/2 for 10 iterations** (HippoRAG / MemGraphRAG, `Week_Plan/week-5-…` §"The Honey and the
>   Springs"; `W = D⁻¹A` over the `RELATES_TO` adjacency). The syllabus also says to sweep λ
>   (*"at λ = 0.1 the honey wanders; at λ = 0.9 it never leaves home"*) — report the sweep, use 1/2.
> - **Syllabus sources:** `Week_Plan/week-5-summer-lesson-plan.pdf` (Labs 1–5),
>   `Labs/Week_5/ms_graphrag_tutorial/docs/graph_analysis.md`,
>   `Labs/Week_11/text2sql_firstprinciples/src/labs/lab2_network_theory/README.md`.
> - ⚠️ **§I21/§I39 are prerequisites for good communities** — TOC concepts are exactly the noise
>   that fragments them. Decide D1 before spending summary budget.
> - ⚠️ The existing §G2 before-arm measurement (§I33) is on **Louvain** and must be **re-run on
>   Leiden** before it is quoted again.
>
> **3. ✅ DONE (2026-10-21 session 2) — §I39 / §E5 filter extended, and the register's band table was
> CORRECTED.** Two signals added to `content_filter.py`, both measured with **zero body collateral**:
> `is_toc_layout` (a dot-leader **run** + a section number → **72/77** TOC chunks) and
> `is_index_density` (≥34 % of lines are "term, page-ref" → **186/187** index chunks). End-to-end on
> doc `7ba61432`: TOC 72/77, index 186/187, front 5/65, **body 0/3,467**. ⚠️ **The previous session's
> numbers did not reproduce and are superseded:** the TOC is **pages 22-34 = 77 chunks**, not 19
> chunks on pages 20-26 — ~55 TOC chunks were being counted as *body*, which is why "0 body false
> positives" looked true (the FP count included the TOC). Also measured: **signals 2 and 3 fire on
> ZERO chunks of this corpus** — the index passed as content because both are dead here. Rejected:
> a bare dot-leader run (fires on p661's ratchet prose and the preface) and a bare `N-N, N =`
> literal (15/77 TOC, 133/187 index — an index signal, not a TOC one). **Still not caught:
> front-matter prose** (60 of 65 front-matter chunks) — the remaining §E5 gap. Tests 4 added
> (`tests/test_content_filter.py`, verbatim corpus rows); filter suite **27 passed**, full suite
> **443 pass / 4 fail / 6 skip** (the same 4 pre-existing). **Takes effect
> on a re-ingest** — `is_content` is written at ingest, so the 5,100 junk cards are not removed by
> this change. Detail + evidence: §I39 outcome.
>
> **4. Owner decisions.** **✅ D1/§I21 SETTLED 2026-10-21 (owner): the filter fix comes first, §G3 does
> NOT run on the current graph.** Order: extend the filter (**done**, item 3) → apply `is_content` in
> the Phase 3 path → harden the graph build (§I23) → rebuild → *then* §G3, then §G2. The gate that
> releases §G3 is the rebuild landing. **§G1 (PPR) is the one graph item not gated** — it is a
> traversal change and does not care which concepts are in the graph. Full reasoning: §I21's
> "D1 SETTLED" block. **Still open:** **§I34** (a re-ingest transition reports the graph lane as SKIP
> — non-blocking as built, or a hard blocker?); **§A3** (card volume vs quality). ~~**D3** (commit the
> untracked graph-analytics plan)~~ — **STALE, corrected 2026-10-21: the plan is already tracked**
> (`.hermes/plans/2026-10-18-p1-graph-analytics-plan.md`, `git ls-files` returns it). **B1 (the §G3
> merge) is still NOT authorised.**
>
> **Uncommitted when this was written:** `scripts/preflight.py`, `src/pdf_ingestion/store.py`,
> `logs/p1/step10/verify_phaseb_{cards,raptor}.py`, `IMPROVEMENTS.md`, `HANDOFF.md`.
>
> ---
>
> **Step 10
> §0 pre-registration is written**; §1's preflight gate failed and was registered as **§D14**. Owner
> chose fix (c) — rebuild the graph (Step 9's *graph half*; cards / DA / ColPali still deferred).
> **Phase A is complete:** A3 built doc `7ba61432`'s graph (16 h 25 m, verifier PASS), **A4 applied**
> (old document's graph retired — `graph.matches-qdrant` 100 % → **0.0 %**), **A5 `preflight.py` exit
> 0**, **§2 the reranker ablation RAN** (Δ **+0.0099**, CI **[−0.0140, +0.0339] → UNRESOLVED**, §D13
> updated), and **§3 is done** — §3a verified the deployed page numbering, §3b audited the labels,
> §3c(B) clamped 4 unreachable pages, §3d ran retrieval-only as a smoke test (**§D15**). **Next:
> Phase B — planned at `.hermes/plans/2026-10-19-p1-step9-phaseB-plan.md`.** Branch
> `feat/p0-9-gold-dataset-v2`. **Read `RETROSPECTIVE.md`** for the project-wide lessons.
>
> **🟢 NON-LLM PARALLEL WORK — EXECUTED 2026-10-20 (A1–A4), STOPPED AT THE PLAN'S STOP LINE.**
> Plan: `.hermes/plans/2026-10-20-p1-nonllm-parallel-work-plan.md`. Register: **§I32–§I38**.
> Ran beside the in-flight card run without disturbing it (1,007/3,791 at the time of writing).
>
> | stage | state | artifact |
> |---|---|---|
> | **A1** | query-side `matched_concepts` measured: **97.86 %** tie at 1 (mean 1.0219) — §I29's missing number, now §I32. 2 runs byte-identical. Reviewer 1 **voided** (protocol error); re-review **VERIFIED 9/9** (re-ran, recomputed the aggregate, checked degeneracy, the anchor and parity) | `logs/p1/step10/g3_query_side_baseline.{py,json,log}` |
> | **A2** | §D14 fix (b) landed (§I34): PASS/SKIP/FAIL verdict + scope gate. Reviewer **VERIFIED** 4/4 | `logs/p1/step10/a2_preflight_{before,after,negative,negative_before}.log` |
> | **A3** | §I28 over-fetch fixed (§I35): 195.1 s / +5,010 MB → 12.9 s / +616 MB, contract byte-identical. Reviewer 1 REFUTED on field misattribution **and left `store.py` reverted** (restored); reviewer 2 interrupted by the approval gate; reviewer 3 **VERIFIED** 6/6 and re-ran the head-to-head itself | `logs/p1/step10/a3_fetch_probe.{py,json,log}` |
> | **A4** | §G2 gate, before arm: Q 0.589597 vs rewired null 0.280330 → PASS (one-sided). **Leiden is NOT runnable** in networkx 3.6.1 (§I33) — ran on Louvain | `logs/p1/step10/g2_modularity_gate.{py,json,log}` |
>
> **⚠️ TWO PLAN PREMISES WERE WRONG, both now registered.** (1) A2's "today: exit 1, 1 BLOCKER" was
> stale — preflight has exited 0 since A5 (§I36). (2) A4's "Leiden … no new dependency" is false —
> `leiden_communities` is a backend-dispatch stub that raises `NotImplementedError`, and the Louvain
> substitute produced **1 disconnected community**, so the gate's connectedness verifier is **unmet**
> (§I33). **Open owner decisions:** the §I34 SKIP-vs-blocker question, and whether to add a Leiden
> backend dependency. **B1 (the §G3 merge) was NOT started** — separate gate, not authorised.
> Uncommitted: `scripts/preflight.py`, `src/pdf_ingestion/store.py`.
>
> **PHASE B — where it actually stands (2026-10-20).** It was **run on 2026-10-19 and ABORTED** at
> B2/B3: cards for 74 of 3,791 chunks in 60 minutes (~97 s/chunk, 16 timeouts, ETA ~51 h), killed by
> hand. The abort was **clean** (0 cards, 0 RAPTOR nodes, `knowledge_base_v2` still 3,796 points, the
> old doc's 82,164 active cards untouched). Three findings came out of it, all now registered:
> **§I24** (`src/core/llm.py` had no total-request deadline and no retry — a 41-minute silent hang),
> **§I25** (the per-card-type swallow made a *total* card loss invisible: zero `Failed:` rows,
> exit 0), **§I26** (the concurrency knee). **§I24, §I25 and §I27 are FIXED in code, and the card run
> HAS since been relaunched and completed** (2026-10-21 03:59:39 — see the block below).
>
> **✅ THE CARD RUN FINISHED — 2026-10-21 03:59:39, wall 534 min 29 s (~8.9 h). B4/B5/B6 HAVE RUN.**
> `run_phaseb.sh 4` (card_gen_workers 4 = **32 effective**, qdrant `10.0.10.65`, no stubs).
>
> | | |
> |---|---|
> | cards | **75,645** for **3,791 / 3,791** chunks (19.95 cards per content chunk — top of the ~16-20 family) |
> | failure counters | **2 chunks with a failed card type, 2 failed card-type calls, 2 LLM failures of 30,328 calls** — `formula`×1, `question`×1 |
> | log | `logs/p1/step10/phaseb_run.log`, **preserved as `phaseb_run_2026-10-21.txt`** (`*.log` is gitignored) |
>
> | stage | verdict | evidence |
> |---|---|---|
> | **B4** cards | **PASS** (exit 0) after the §I42 retry — closing line `0 / 0 / 0`, **75,662** active cards, 3,791/3,791 chunks used, 0 orphan, 0 foreign-doc, all 8 types, `question` 29,321 / `factoid` 30,635, old document untouched at 82,164. *(The original run was FAIL on 2 failed card types — see the §I42 note below.)* | `logs/p1/step10/b4_cards_verify_2026-10-21.log` |
> | **B5** RAPTOR | **PASS** (exit 0) after the §I43 fix + de-dup — `knowledge_base_v2` = **3,869 points** = 3,796 chunks + **73** `raptor_summary`, 0 orphans, 0 zero vectors, chunk lanes intact. *(Was **FAIL**: the Phase 2 re-run duplicated the points — 3,942 / 146 — §I43. ⚠️ The FAIL's own log is **not on disk**: the file previously cited for it holds a PASS from the pre-retry run — §I44.)* | `logs/p1/step10/b5_raptor_verify_2026-10-21_post_dedupe.log` |
> | **B6** card read | **22 cards read** — body cards are good (a p545 `formula` card is exemplary); the junk is all from non-body bands: **5,100 cards (6.7 %) come from TOC/index chunks the E5 filter passes as content** → **§I39** | `logs/p1/step10/b6_card_samples_2026-10-21.txt` |
>
> **⚠️ The 2026-10-21 retry (to clear B4's 2 failed card types) found and fixed a blocker — §I42.**
> `save_cards` could not write for a document that already had cards (`UNIQUE constraint failed:
> cards.id`: the checkpoint replays the original card ids and the old rows were only *deactivated*).
> Fixed by deleting the document's rows before insert. **This had made §I27's own retry path unusable
> and it blocked every Phase 2 re-run** — including §A1 and §A3. **Its sibling path is now fixed
> too: §I43, the RAPTOR upsert appended** (the 146-vs-73 duplication above) — `save_raptor_tree` now
> deletes the document's points and rows before the upsert, and the 73 orphans were removed
> 2026-10-21 (session 2).
>
> **⚠️ B5 must be run with `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2`** — it now
> **refuses** (exit 2) rather than silently scanning the local embedded store (**§I40**, fixed).
>
> **If it ever needs relaunching, the checkpoint resumes** (only chunks since the last checkpoint are
> redone), but note `>` overwrites the log:
> ```bash
> tmux new-session -d -s phaseb "cd '$PWD' && bash logs/p1/step10/run_phaseb.sh 4 > logs/p1/step10/phaseb_run.log 2>&1"
> ```
>
> **⚠️ The card phase takes several minutes to log its first line.** `generate_phase2_artifacts`
> calls `get_chunks_with_embeddings` first, which does `qdrant.retrieve(ids=[3,796 ids],
> with_vectors=True)` — **all named vectors, including the ColBERT token matrices nothing here
> needs (~200 MB over the tunnel)**. Expect "Processing …" to sit for a few minutes before
> `Generating cards for 3791 chunks …` appears. That is pre-existing behaviour, not a hang. **New
> finding, worth its own register entry: the retrieve is unfiltered and over-fetches by ~6×.**

> **✅ THE NETWORK BLOCKER IS RESOLVED — and my first diagnosis of it was wrong.** The lab is
> reachable over the **Fall** tunnel (`utun4` = `192.168.20.24`), **not** the Summer one I named
> earlier: with Fall active, `route -n get 10.0.10.70` → `interface: utun4` and the port answers.
> The earlier claim that Fall "does not claim `10.0.0.0/16`" is **withdrawn** — it was inferred from
> a routing table sampled while the tunnel was dying (utun4 vanished minutes later), which is exactly
> the kind of inference the "verify against the live system" rule exists to catch. **B0b now passes
> end to end** (`logs/p1/step10/b0b_preconditions_w4.log`, exit 0): Qdrant 3,796 points, LLM 200,
> embed 200, doc clean-start 3,796/3,791/0/0.
>
> Still true and still useful: `en0` is `/8`, so macOS treats all of `10.0.0.0/8` as on-link — a
> tunnel route is more specific and wins, so **do not "fix" the netmask and do not use `route add`**.
> The "internet is slow with a tunnel on" cause (the tunnel pushing DNS `10.0.10.96`) is unchanged;
> note `DNS[0]` is `10.0.10.96` right now and browsing is fine, so the lab DNS is not always slow.
>
> **⚠️ COMMITTED AND PUSHED, BUT NOT REVIEWED.** The 2026-10-20 source changes are in **`151cb1f`**
> plus **`597e7b9`** (the `run_phaseb.sh` VM-portability fix), branch `feat/p0-9-gold-dataset-v2`,
> **pushed** to `origin` on 2026-10-20 (upstream now set; `origin/…` == HEAD). The independent review
> **has not run** — see the "Verifier model" row in Verified facts: the recorded reviewer is
> (a) on the cluster, reachable only when the tunnel is up, and (b) **no longer pinned in
> `config.yaml`**, so a `delegate_task` child would now inherit the parent's own model, i.e.
> self-review. **The commits deliberately do not carry the `[verified]` prefix.** Do not treat any
> child's `passed: true` as verification until the pin is restored.
>
> **⚠️ CORRECTION — `151cb1f`'s message overstates what it folded in, and an evidence artifact was
> lost.** The message says it folds in `logs/p1/step10/`. It folded in the **32 non-log files**
> (harness, probes, verifiers, JSON); **zero `.log` files**, because **`.gitignore:68` is `*.log`**.
> Consequence: the **2026-10-19 aborted run log** — the artifact §I25 cites ("16 `LLM CALL FAILED`,
> 16 card-type failures, 0 `Failed:` rows") — was **never in git**, and the 2026-10-20 launch
> overwrote it on disk with `>`. **No APFS local snapshots exist** (`tmutil listlocalsnapshots /` is
> empty), so it is **unrecoverable**. §I25's *numbers* are recorded in the register and were derived
> from the log while it existed; the raw artifact is gone. Two lessons, both now in the traps:
> (1) `git add <dir>` silently drops `.log` files under this `.gitignore` — use `git add -f` or a
> non-`.log` name for anything that is evidence; (2) never let a run's `>` redirect destroy the
> previous run's log without checking whether a verifier cites it.
>
> **Still uncommitted in the working tree** (another session's in-flight work — deliberately left
> alone): `ARCHITECTURE.md`, `data/eval_queries_v2.json`, `scripts/build_gold_v2.py`,
> `src/pdf_ingestion/embed_cache.py`, `src/pdf_ingestion/late_chunk_embedder.py`,
> `tests/test_embed_cache.py`, `data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md`,
> `logs/p1/step8-run/probe_cache_hit*`, and the older `.hermes/plans/2026-10-18-*` plans that
> HANDOFF and the backlog reference.
>
> **This session (2026-10-21, session 2) added:** `scripts/dedupe_raptor_points.py` and
> `logs/p1/step10/i43_raptor_{dup_probe.py,dup_probe.json,rows_probe.py,dedupe.json}`; modified
> `src/pdf_ingestion/store.py` (the §I43 fix), `tests/test_phase2.py` (the new regression test) and
> `logs/p1/step10/probe_phaseb_scope.py` (a comment §I42/§I43 made false). The B5 run log
> `logs/p1/step10/b5_raptor_verify_2026-10-21_post_dedupe.log` is a **`.log` — gitignored**, so
> `git add` skips it silently; `git add -f` if it should be committed.
>
> **THE CARD RUN IS THE ONLY THING LEFT BEFORE B4 — AND THE WORKER COUNT IS NOW MEASURED.**
> The 2026-10-20 sweep (two sweeps, six cells, control-verified) **refutes §I26's original
> conclusion**: throughput scales with concurrency and never collapses — 3.18 chunks/min at
> `workers=1`, 6.52 at 2, **9.39 at 4**, with **zero failed chunks and zero LLM failures** at up to
> **32 in-flight calls**, and `workers=1` re-measured at the end of the session to rule out drift.
> **ETA for 3,791 chunks: ~19.9 h at 1 · ~9.7 h at 2 · ~6.7 h at 4.** The sustained per-chunk cost is
> **~64-105 s at p50**, not the 10.1 s the plan's 10.6 h estimate was built on. Relaunching needs:
> (1) `CARD_GEN_WORKERS` set in `.env` (currently **2**; **4 recommended, 1 no longer**);
> (2) `run_phaseb.sh <workers>` (its B0 gate asserts what is actually in force); (3) B4/B5/B6 the
> verifiers. **⚠️ `workers=8` was NOT tested** and the trend was still rising at 4 — the knee is
> above 4 or not reached, but `.70` is a shared cluster and 32 in-flight is already a real load.
> **The checkpoint makes this restartable** — see below.
>
> **What 2026-10-20 changed in the code (uncommitted at the time of writing):**
> - `src/core/llm.py` — read the body in chunks against a **300 s wall-clock deadline**, raised as
>   `httpx.ReadTimeout` so a **bounded retry** (3 attempts, jittered backoff) catches it; retries
>   transport/429/5xx, never other 4xx. The `""` + ERROR contract is unchanged, and failures are now
>   **counted** (`llm_call_stats()`). **Scope limit:** this covers the *raw* path only — with
>   `use_instructor: true` four card types bypass it (config.yaml currently says `false`).
> - `src/pdf_ingestion/card_checkpoint.py` (**new**) — the card phase is now **checkpointed and
>   resumable**. Each completed chunk is appended to `data/card_cache/<doc8>__<key>.jsonl`
>   (`flush`+`fsync`); a re-run skips what is done and **still returns those cards**, so
>   `save_cards` remains the single write point. A chunk whose card types **failed** is *not* treated
>   as done — it is re-attempted. `run_phase2.py --no-resume` discards it. **This is what makes a
>   multi-hour card run restartable instead of all-or-nothing.**
> - `generate_cards_for_chunks` now reports `failed_card_types` / `failed_chunks` through
>   `generate_phase2_artifacts`, and `run_phase2.py` prints a **"Card types failed"** column.
>   **That count, not the absence of a `Failed:` row, is the exit criterion (§I25).**
> - New tests: `tests/test_llm_deadline_retry.py` (14), `tests/test_card_checkpoint.py` (15);
>   `tests/test_fallback_chains.py` rewritten to the new transport boundary (its old
>   `llm.httpx.post` patch was silently inert and the tests were making **real network calls**).
>
> **Where the re-ingest stands.** Goal: `scripts/ingest_base_textbook.py --pdf …feynman…
> --collection-name knowledge_base_v2 --reindex` with `QDRANT_HOST=10.0.10.65` and
> `SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings`. Five attempts:
>
> | # | result |
> |---|---|
> | 1 | **no retry** — one transient read timeout discarded 86 min at parent 260/341 (§I16) |
> | 2 | retry worked (600 attempts) but the **endpoint went down**; no checkpoint, 53.6 min lost |
> | 3 | reached **339/341** parents, then unreachable endpoint; 63.8 min lost (§I19) |
> | 4 | **reached the final write** — late-chunk 341/341 with **0 retries**, SQLite + SPLADE + ColBERT all done — then Qdrant rejected the upsert: **34.7 MB payload vs a 32 MiB cap** |
> | 5 | **SUCCEEDED** — 58.6 min (12:14:54 → 13:13:28), **0 errors**. Late-chunk 36.1 min, SPLADE 5.4, ColBERT 10.2, upsert 2.3. `knowledge_base_v2` = **3,796 points, all four lanes on every point**, `verify_collection.py` exit 0. The cache delivered nothing (§I19a) |
>
> **What is fixed and committed:** bounded retry + jittered backoff and per-path read timeouts
> (`9215de8`); a **total-request deadline** for the trickling-body case that no read timeout bounds;
> **`late_chunk_workers = 4`** (8 measured *slower* under sustained load — §I18); a **resume cache**
> (`ed218f9`, `bf54a93`, `f0098a1`, plus the §I19a fix) — **now proven to hit: 341/341 parents with
> zero embeddings issued, verified read-only against a dead endpoint**;
> **byte-budgeted
> Qdrant upsert batching** (`5675cb6`); and a launch-time **resolved-settings gate** in
> `run_step8.sh` that prints and asserts the settings actually in force (attempt 3 ran at 8 workers
> while everyone believed 4 — `.env` overrode the config default).
>
> **IMMEDIATE NEXT STEPS (in order)**
> 1. **Attempt 5 is DONE — it SUCCEEDED** (see the table). Steps 1 and 3 of the previous version of
>    this list are both discharged; the log is `logs/p1/step8-run/run_feynman.log` (753 lines, ends
>    `=================== RUN COMPLETE ===================`, finished 13:13:28).
> 2. **Verify the collection — DONE, exit 0.** `uv run python logs/p1/step8-run/verify_collection.py
>    knowledge_base_v2 --sqlite data/synapse.db`: 3,796 points reported == 3,796 scrolled,
>    `all_lanes_on_every_point: true`, `missing: {}`, dims `colbert 128 / dense_1024 1024 / dense_64
>    64`, sparse on all 3,796, and points == SQLite chunks **scoped by `document_id`** (the old
>    deployed doc `6d55c52b`, 5,048 chunks, is intended, not a mismatch). Two things it reports
>    without judging: **3,795 of 3,796** points carry a `parent_id` (1 does not) and `is_content` is
>    true on 3,791.
> 3. ~~Prove the cache actually hits~~ **DONE 2026-10-18 — and without a second ingest.** The
>    read-only probe `logs/p1/step8-run/probe_cache_hit.py` mirrors `process_pdf` lines 95–104 and
>    stops before `save_document`; run against the live cache with the dense lane pointed at a
>    **dead port**, it reports **341 hits / 0 misses / 0 stale / 0 rejected / 0 embeddings issued /
>    0.8 s**, `VERDICT: HIT`. Attempt 5's zero-hit run was the digest-width defect — **§I19a, now
>    FIXED** (the digest scheme is named in each entry and checked on read; a hit is counted only
>    after `rebuild()` validates). The `_CACHE_SCHEMA_VERSION` bump that §I19a first proposed was
>    rejected on evidence: it would have discarded 341 entries that work.
> 4. **Step 10 — IN FLIGHT. RESUME HERE.**
>    - **§0 DONE** — `.hermes/plans/2026-10-18-p1-step10-preregistration.md`. It corrects three plan
>      numbers: the text lane is **133** (not 135); the endpoint is the final top-20 (**B6**), not
>      B5b (B5b is arm-invariant by construction — it is the control); and the §D9 **R@20** ceiling is
>      `mean(min(20,|rel|)/|rel|)` = **0.8016**, *not* the funnel's printed "Precision@20 ceiling" of
>      0.4861. `required_n.py` prints **no CI**; the CI is `mean ± 1.96·SD/√n`.
>    - **§1 FAILED → §D14.** The graph holds only the OLD document (`6d55c52b`); `knowledge_base_v2`
>      is the new one (`7ba61432`). 5,051/5,051 graph chunk ids dangle (**100%**). Chunk ids are
>      `uuid4()` per ingest, so **no environment action clears this**.
>    - **Memgraph now runs locally**: Docker Desktop + `docker compose --profile phase3 up -d memgraph`.
>      ⚠️ The container reports **`unhealthy` permanently** — its healthcheck runs `mg_client`, absent
>      from `memgraph/memgraph:2.18.1`. **Check Bolt on 7687, never `.State.Health.Status`.**
>    - **Owner decision: build the graph** (§D14 fix (c)) — but **"minimal first": ONLY the graph.**
>      Cards / DA / ColPali stay deferred. Plan:
>      `.hermes/plans/2026-10-18-p1-step9-downstream-pulled-forward-plan.md`.
>    - **Phase A:** A1 settings gate ✅ · A2 before-snapshot + one-chunk LLM probe ✅
>      (`logs/p1/step10/graph_before.json`) · **A3 build ✅ DONE, VERIFIER PASS** (2026-10-19 09:47:04).
>      `logs/p1/step10/graph_build.log`, `graph_after.json`. **Took 16 h 25 m, not the 2 h I
>      estimated** (§I23) — do not budget Phase 3 runs in hours on this shared cluster.
>      Doc `7ba61432` now has **3,796 chunk nodes (== SQLite), 933 pages, 7,834 distinct concepts**,
>      density **2.064/chunk** (old doc 1.547; floor 0.774). Old document verified **untouched**.
>      ⚠️ The run reported "15619 concept nodes / 0 failed" — both wrong (§I22: that field is MENTIONS
>      edges, ~2× the truth; and 44 real LLM timeouts were swallowed, §I23). **Count in Memgraph.**
>    - **A4 ✅ APPLIED 2026-10-19 18:01** (dry-run re-verified live first — read-only — then `--yes`;
>      **never `--force`**). Removed **1 document / 5,051 chunks / 757 pages / 4,664 orphaned
>      concepts**. Verified from Bolt: graph now holds **1** document (`7ba61432`, 3,796 chunks ==
>      SQLite, 933 pages, 7,834 concepts, 73,336 edges, density 2.064), old-doc residue **0/0**.
>      `logs/p1/step10/{a4_dryrun.log,a4_apply.log,a4_verify.log,graph_after_cleanup.json}`.
>      ⚠️ The deleted graph belonged to the **deployed** `knowledge_base` — the deployed app's multihop
>      lane has no graph until cutover. Accepted consequence of fix (c) (§D14).
>    - **A5 ✅ PASS 2026-10-19 18:02** — `preflight.py` **exit 0**, every check PASS,
>      `graph.matches-qdrant` **0/3,796 absent (0.0 %)** (was 100 %). `logs/p1/step10/a5_preflight.log`.
>    - **§2 ✅ RAN 2026-10-19 18:02–18:17 — verifier PASS, result UNRESOLVED.** n=**133** both arms,
>      same collection + HyDE cache + `dense_1024`; §D10 check: `B5b_retriever_top20` moved on **0**
>      queries → valid. **Δ = +0.0099** (rerank − no-rerank), SD_d **0.1411**, 95 % CI
>      **[−0.0140, +0.0339]** → **UNRESOLVED** (33 worse / 36 better / 64 identical). R@20 raw 0.4153
>      vs 0.4054 → ÷0.8016 = 0.5181 vs 0.5057. **SD_d fell 0.2315 → 0.1411** and required N for
>      δ=0.05 fell **169 → 63** — n=133 now exceeds the pre-registered requirement. The §D13
>      factual-lane loss (−0.0469, resolved on the old index) **did NOT reproduce**: now +0.0026,
>      CI [−0.0440, +0.0493], unresolved. Evidence `logs/p1/step10/{run_step10_v2.log,
>      v2_rerank.json,v2_norerank.json,ab_verifier.log,ab_verdict.json}`; §D13 updated.
>    - **§3 ✅ DONE 2026-10-19 (a–d).** **§3a** — the deployed index's `page_number` re-measured
>      against the PyMuPDF oracle (helpers imported from the Step 6 probe, so they cannot drift):
>      new doc `7ba61432` **2150/2151 = 0.9995** offset 0 (1.0000 first-per-page), old doc `6d55c52b`
>      **0.7154** as the baseline. Reproduces Step 6 chunk-for-chunk → **the deployed index speaks
>      PDF-page coordinates**. **§3b** — label provenance audited (`logs/p1/step10/audit_gold_labels.py`):
>      factual 53 generator + 453 scan-only labels; multihop 86 generator (17 single-chunk + 23
>      **multi-page**) + 89 scan-only; overview/visual carry **no** generator page by construction.
>      **§3c (option B, owner-approved)** — `build_gold_v2.py` gained `_clamp_unretrievable()`; the 4
>      multihop pages in 22–24 (below `min_content_page` 30, all **multi-page generator** pages =
>      §D4's defect as a §D6 one) were clamped. Diff verified to be **exactly** those 4 pages.
>      Unreachable label pages **4 → 0**; text-lane achievable max **0.9910 → 1.0000**; §D9 ceiling
>      unchanged (0.8016). `tests/test_gold_schema.py` 7 passed.
>    - **§3d(ii) ✅ RAN — a SMOKE TEST, not a measurement (§D15).** R@20 0.452 · Hit@20 0.910 · MRR
>      0.728 · abstention 0.824; per lane factual 0.570 / multihop 0.543 / overview 0.206.
>      **Not comparable to §D12's 0.465** — four independent differences (see §D15).
>    - ⚠️ **NEW FINDING (§I12 update): the DA lane is DEAD on every `evaluate_rag.py` query.**
>      `derivative_artifacts` is 768d while the query side is 1024d → `search_da` returns `[]` for all
>      152 non-visual queries, and the report says nothing. `preflight.py` misses it because it checks
>      a point count, never issuing a query. §I12's "no silent degradation" holds for the UI only.
>    - **NEXT: RELAUNCH Phase B's card run — ATTEMPTED 2026-10-19, ABORTED, blockers now FIXED.**
>       Plan: `.hermes/plans/2026-10-19-p1-step9-phaseB-plan.md` (B0–B7, each with its verifier).
>       **B0 gate ✅ PASS, B0b live preconditions ✅ ALL PASS, B1 one-chunk probe ✅ PASS ×3.** B3 was
>       run and **killed by hand** at 74/3,791 chunks (see the Phase B banner above). **The harness and
>       both verifiers are written and smoke-tested** (`run_phaseb.sh`, `verify_phaseb_cards.py`,
>       `verify_phaseb_raptor.py`); the before-snapshot is measured
>       (`logs/p1/step10/phaseb_before.json`).
>       **The shape of it:** 3,791 content chunks × 8 card types ≈ **30,328 LLM calls** → ~60–76k cards.
>       **What is different now:** the run is **checkpointed and resumable** (§I27) and every LLM call
>       is **bounded and retried** (§I24), so an abort costs the chunks since the last checkpoint rather
>       than the whole run, and exit 0 is no longer evidence — read `failed_card_types` (§I25).
>       **⚠️ `verify_phaseb_cards.py` check [1] ("no `Failed:` row") is vacuous** — §I25. The real
>       guards are checks [3] (distinct card-type set == the 8 in `CardType`) and [4] (cards/chunk
>       ratio), plus the new `failed_card_types == {}` from `run_phase2.py`'s output.
>       Then **C (DA re-index) → D (ColPali) → Phase E** (the authoritative `evaluate_rag.py` run).
>       Phase C is what makes the DA lane live again (§I12).
>    - **§2 harness**: `logs/p1/step10/run_step10_v2.sh` (steps 1–3; step 4 deliberately absent)
>      + `logs/p1/step10/check_ab_arms.py` (verifier: same n, §D10 B5b-stability, ceilings, CI,
>      per-type). **§4 is deferred** — it reads the DA/graph/visual lanes, still the old document's.
>    - **RESOLVED — the owner question is closed.** §2 did **not** need §D14 fix (b): fix (c) cleared
>      the gate, so §2 ran on the clean index as intended. Fix (b) is still the durable fix for the
>      next re-ingest (§D14) and is still **not done**.
>    - **§I20** is decided **after** Step 10, not during.
>
> **New register entries this session:** §D15 (the §3d retrieval-only run — a smoke test, and the run
> that exposed the dead DA lane), §D14 (the preflight gate cannot pass for a re-ingested collection —
> now discharged by fix (c), with fix (b) still open), §A3 (card volume vs quality — owner's question,
> curriculum-grounded), §I21 (the Phase 3 graph build ignores the E5 content filter), §I22
> (`graph_stats["concept_nodes"]` is really MENTIONS edges), §I23 (the Phase 3 graph build has no
> checkpoint/retry, burns a reasoning model, and its throughput collapsed 8× under shared-GPU
> contention — measured). **Updates to existing entries:** §D4 and §D6 (the deployed page-numbering
> verification, the label-provenance audit, and the §3c clamp), §I12 (the DA lane is dead in
> `evaluate_rag.py` — 768d collection, 1024d query). **§G (graph analytics: PPR, entity
> resolution, community detection) is planned and SIGNED OFF but NOT started** —
> `.hermes/plans/2026-10-18-p1-graph-analytics-plan.md`; **no new deps needed** (networkx 3.6.1 has
> `leiden_communities`; Memgraph has `nxalg.pagerank`). **The SupportVectors course materials are at
> the repo root** (`Week_Plan/`, `Week_Summary/`, `Slides/`, `Labs/`).
>
> **Register entries added 2026-10-20 (all four from the aborted Phase B run):** **§I24** FIXED —
> `src/core/llm.py` had no total-request deadline and no retry (41-minute silent hang); **§I25**
> FIXED — the per-card-type swallow made a total card loss invisible (0 `Failed:` rows, exit 0);
> **§I26** — the card concurrency knee, and the standalone probe that replaced the structurally
> unmeasurable ramp; **§I27** FIXED — the card phase had no checkpoint/resume, so a ~10.6 h run was
> all-or-nothing.
>
> **Cleanup that is NOT automatic** — a failed run leaves a half-written state: delete the orphaned
> `documents` row and its `chunks`, and delete the partially-written collection, before re-running.
> Attempt 4 needed exactly this (128 orphan points + a 3,796-chunk orphan row). Registered in §I20.
> Attempt 5 needed none of it — it recreated the collection at launch and left no orphan rows.
>
> **Open register items blocking or adjacent:** §I16 (checkpointing done; the deadline is done;
> nothing left blocking), **§I19a (FIXED 2026-10-18 — the cache hit nothing in the run it was built
> for: a digest-width change with no `_CACHE_SCHEMA_VERSION` bump, plus a counter that reported 341
> hits for 0 usable ones; the scheme is now named and checked and hits are counted after
> validation)**, §I17 (ColBERT batch 4 / SPLADE batch 32 remain serial — measured on attempt 5 at
> **15.6 min combined**: ColBERT 10.2, SPLADE 5.4), §I18 (probes must sweep payload size AND be
> sustained, not bursts), §I19 (cache: built, and now proven to hit), §I20 (atomicity).
> **§I14 is resolved** — `SV_EMBED_URL` is now in `.env`.
>
> Detail lives in `IMPROVEMENTS.md` §E6–§E7 and §I14–§I20; the procedure for the next action is
> `.hermes/plans/2026-10-18-p1-step10-remeasure-plan.md`; the evidence is `logs/p1/step8-run/`.
>
> **Steps 2–3 went through independent review 2026-10-17** (verifier = `openai/gpt-oss-20b`, a
> different model from the author's). It found one genuine defect — a parent with no provenance
> silently gave every child `page_number=None` — now fixed with a loud warning + test. Two of its
> three "logic errors" were diff-only artifacts (a helper defined outside the diff; a guard
> misread), and its C2 refutation rested on a flawed check of the author's own. Adjudicated with
> evidence: **page-map agreement is 0 mismatches / 169 elements and 0 / 5555 sampled characters**
> against Docling's per-element provenance as an independent oracle. See "Verified facts" for the
> verifier's model and its one hard limit (no multi-turn tool sessions).
> If this date is old, re-check `git log --oneline -5` and `git status --short` first.

---

## Scope decision (settled)

**Single-user now.** The `tenant_id` plumbing exists but is **not enforced** — there is no auth,
and the UI takes the tenant from a text box. Deliberate deferral: **multi-tenancy is the final
stage, after metrics are solid.** Do not "fix" auth or tenant isolation while working on metrics,
and do not add new `tenant_id` defaults.

---

## Current focus — P0-9, the gold-set rebuild (Sessions 1–3c built; run 3c + 3d next)

Gates all of P1. **Required-`N` is now measured** (Session 1, below). Two documents, both committed:

| Doc | Purpose |
|---|---|
| `.hermes/plans/2026-10-06_174001-p0-9-gold-dataset-v2.md` | Full plan: tasks 0–8, decisions D1–D10, power analysis. **Read only your task's section** — do not load all 1044 lines. |
| `.hermes/plans/p0-9-SESSIONS.md` | The session split: which tasks belong in which fresh session. |

### Session 2 delivered 2026-10-12 — the tools exist (no large LLM spend)

| Tool | What it does now |
|---|---|
| `scripts/generate_gold_dataset.py` | + `--multipage-count`: overview/multihop questions from distant page triples (`min_gap` 60). D10 applied — `max_tokens` 512→2048, and an empty generation batch retries, logs the raw response and **raises** instead of silently returning `[]`. |
| `scripts/validate_eval_calibration.py` | Parallelized (Task 4a): one open PDF + per-page image/text cache, disk verdict cache keyed by (query_id, page, model, prompt-hash), thread pool (`--workers`, default 8), one shared `httpx.Client`. D9 — each page judged from its rendered **image** plus full text, not `text[:800]`. New `--ramp-probe`. |
| `scripts/expand_gold_labels.py` | Widens `relevant_pages` to every page that answers the question, via the two-pass scan. `--dry-run` / `--limit N`. |
| `scripts/generate_negatives.py` | Three-tier negatives, accepted only if a full scan finds no YES page. `--dry-run` / `--n N`. |

Verified: each tool passes `--dry-run` and a stubbed `--limit`/`--n` probe; the hot pages are
judged once, not twice; a re-run makes zero judge calls. **D9 verified live** against the cluster
VLM (p254 → YES "½mv² is kinetic energy", p3 → NO copyright page, ~0.8 s/call). Suite at the
floor: **211 pass / 5 fail / 5 skip**.

### Session 3 delivered 2026-10-13 — the scan ran (all three steps, exit 0)

Judge `Qwen/Qwen3-VL-8B-Instruct` @ `http://10.0.10.70:8000`, `--workers 8` (ramp-probe knee:
4.21 calls/s, 0 errors; 16/32 collapse to ~1.2/s from queueing). Commits `1870dc9`, `8e81572`.

| Artifact | Content |
|---|---|
| `data/eval_queries_gold.json` | 103 questions — 55 factual / 8 overview / 40 multihop |
| `data/eval_queries_gold_expanded.json` | 66/103 queries widened to >1 page (max 134), scan-expanded |
| `data/eval_negatives.json` | 24 negatives, 8 per tier — **see caveat** |

**Four blockers had to be fixed first** (Session 2 only ran `--dry-run`/stubs, so they survived):
the run-order command omits `--judge-backend openai` (defaults to Anthropic → 401); `call_llm_raw`
posted to `{base}/chat/completions` (gateway serves only `/v1/...` → 404); 2048 `max_tokens` was
still too small for `gpt-oss-20b`'s reasoning trace (content came back null/truncated → raised to
8192); and the model's LaTeX (`\(m v\)`, `\frac`, `\theta`) is not valid JSON (`\f`,`\t`,`\n`,`\b`
even decode to control characters) → `_extract_questions` now escapes every backslash but `\"`/`\\`.

> ✅ **Negatives re-verified (Session 3b) — resolved.** The term-bearing re-scan now covers every
> page carrying a negative's key terms (±2) — the pages the stride-15 scan never reached. Result:
> **1 definitively invalid** — `neg-nea-004` (carbon-14 half-life) is answered on **p107** →
> **dropped**; `neg-in_-001`'s only YES was on **p944, the index** → now capped to PARTIAL by the
> back-matter gate (below), so it stays. **6 kept but flagged `needs_review`** because the judge
> returns content PARTIALs (the book *discusses* the topic): `in_-001, in_-002, in_-005, in_-007,
> in_-008, nea-008`. **17 clean.** The plan's fear that near_miss would "mostly be rejected" did
> **not** materialise once the term pages were actually scanned.
> Evidence: `logs/p0-9/report_negatives.py`, `logs/p0-9/prune_negatives.py`, `logs/p0-9/session3b/`.

### Session 3d delivered 2026-10-13 (code landed; the queries followed as 3d-ii)

Commit `4697961` on `feat/p0-9-gold-dataset-v2`. **§B4a fork settled on option (a)**, on evidence:
the cluster colpali endpoint was re-probed and is **still down** (HTTP 500 on all five request
shapes, ~3.1 s; the **colbert** endpoint on the same host returns 200 in 0.15 s), so option (b) /
ColQwen3 is blocked on the cluster. Option (a) verified end-to-end **offline** — `process_queries`
gives an `(N, 128)` matrix whose patch_dim matches the stored pages, L2-normalised, no re-ingest.

| Deliverable | State |
|---|---|
| (1) text-query path | ✅ `ColPaliEmbedder.embed_query_text` + stub |
| (3) visual metric | ✅ `evaluate_rag.run_visual_retrieval` — text → MaxSim over `visual_knowledge_base`, page-level metrics reused; visual queries now score instead of being skipped |
| (2) visual queries + labels (30–40) | ✅ **done as 3d-ii** — 33 usable of 40 (see "Session 3d-ii" below) |

Tests: +4 stub text-path, +3 visual-lane. Suite **225 pass / 5 fail** (same 5 pre-existing).

**Found and registered (`IMPROVEMENTS.md` §B4b):** the local `visual_knowledge_base` holds
**2,835 points for 945 pages — every page exactly 3×**, one doc id (`b2d9fb56`); top-20 held only
**7 distinct pages**, capping the whole lane's Recall@20. `clean_stale_visual.py` cannot catch it
(keys on `document_id`), and the visual doc id ≠ the text doc id (`5fcc9006`). Nothing was deleted;
the eval lane dedupes by page meanwhile. Root fix folded into the E1/E2/E3 re-ingest pass.

### Session 3d-ii delivered 2026-10-14 — the visual queries and their labels

Commit `3a18da4`. Three deliverables, all built: (1) the **visual generation path**
(`generate_gold_dataset.py --visual-count` — text-only generator, one figure question per
`<!-- image -->` page in the content region) → `data/eval_queries_gold_visual.json` (**40**,
source pages 37–915); (2) the **D8 visual judge variant** (`_VISUAL_JUDGE_PROMPT`, strict) plus the
anchor window, in `validate_eval_calibration.py`; (3) the **book-wide scan** →
`data/eval_queries_gold_visual_expanded.json`.

| Result | Value |
|---|---|
| Generated | 40 visual questions |
| **Usable after hygiene** | **33** (23 single-page, 7 two-page, 2 three-page, 1 four-page) |
| Uncalibrated (no YES page) | **6** — `vis-004, 009, 016, 017, 023, 025` |
| Dropped as non-specific | **1** — `vis-024` (71 YES pages — "the diagram of the wave signals") |

**The 6 uncalibrated are a scan/judge gap, not generator hallucinations** — the source pages carry
the figures the questions describe. Two causes (§B4d): `vis-004/025` found the *correct* page but
the strict VLM graded it **PARTIAL**, and `expand_gold_labels.py:88` keeps **YES only**;
`vis-009/016/017/023` got NO everywhere, even in the ±4 anchor window. A re-scan that credits a
correct PARTIAL, or a specificity-gated generator, would recover them — **deferred** (needs cluster
VLM calls). Tests: `tests/test_visual_queries.py` (8, passing); suite **236 pass / 5 fail** (the
same 5 pre-existing).

### Session 4 delivered 2026-10-14 (partly — the harness, blocked on the cluster)

Commit `e69c347`. **`data/eval_queries_v2.json` is assembled** by the new `scripts/build_gold_v2.py`:
**95 text** (55 factual + 40 multihop) + **40 overview** (3c) + **33 visual** (3d-ii, calibrated
only) + **34 negatives** = **202** (16.8% negatives). The 8 pre-3c overview entries inside
`gold_expanded` are dropped (superseded); v1 is not merged (D6). `tests/test_gold_schema.py` passes
(6). The **abstention metric is wired** into `evaluate_rag.py`: a negative
(`answerable: false`) measures `abstained` (a declining answer OR a top-1 score below the
threshold), negatives are excluded from the by-type retrieval averages, and an `abstention` block
prints under the summary table. Suite **242 pass / 5 fail** (same 5).

**The decision is pre-registered** before any numbers exist:
`.hermes/plans/2026-10-14-p0-9-4-preregistration.md` — reranker stays iff it beats no-reranker on
R@20 by more than the 95% CI on the paired difference; abstention must beat the majority baseline.
Scope decided there: the **text-lane funnel runs on 135 queries and excludes the 33 visual**
(the funnel has no ColPali lane, so visual queries would dilute the delta); the visual lane and the
negatives are measured by `evaluate_rag.py`. `funnel_boundary_recall.py` gained `--include-visual`
(default: excluded).

> ✅ **UNBLOCKED AND RUN 2026-10-14 18:03–18:06.** The router came back mid-afternoon.
> `logs/p0-9/run_session4_v2.sh` (written 17:55) ran **steps 1–2** on the cluster index
> (`QDRANT_HOST=10.0.10.65`, 5,135 points), **133 text queries**, one shared HyDE cache.
> **Steps 3 and 4 did not run** — §D7: `required_n.py`'s `--queries` default is **v1** →
> *"0 shared queries"*, exit 1; `evaluate_rag.py` wrote no artifact. Full numbers:
> pre-registration → "Outcome".

### Session 4 — the v2 A/B result (2026-10-14)

| boundary | rerank | no-rerank | reading |
|---|---|---|---|
| B1_dense64_1000 | 0.7924 | 0.7924 | precedes the reranker — identical, as it must be |
| B2_dense768_500 | 0.7415 | 0.7415 | " |
| B3_sparse_250 | 0.6743 | 0.6743 | " |
| B4_rrf_union_100 | 0.5943 | 0.5942 | " (§D10 — not bit-reproducible) |
| B5_colbert_100 | 0.6007 | 0.6007 | " |
| **B5b_retriever_top20** | **0.4495** | **0.4495** | the 100→20 cut costs **0.15** of recall |
| **B6_rerank_20** | **0.4389** | **0.4495** | the reranker alone: **−0.0107**, CI **[−0.0304, +0.0091]** |

**Verdict: unresolved at n=133** — the CI straddles 0, so the pre-registered rule (§4) is not met.
30 queries worse / 37 better / 66 identical — churn, not a uniform loss. Exploratory per-type:
**factual −0.0469, CI [−0.0787, −0.0152] → resolved (the reranker hurts factual)**, multihop
+0.0091 and overview +0.0176 both unresolved. The factual result survives a Bonferroni correction
for 3 subgroups, but it is a **subgroup, not the pre-registered endpoint**.

**Why v2 looks worse than v1's 0.636 — and mostly is not** (§D9): R@20 is divided by the label
count, and v2's overview labels average **73.8** pages (max 314) against v1's **3.4** (max 13).
v1's mean ceiling was 1.0000; v2's text lane is 0.8016 and its overview lane only 0.3992. On v2's
88 text queries with ≤20 labels — structurally v1-like — B5b scores **0.6037** vs v1's 0.636.
**v1 and v2 R@20 numbers are not comparable; never put them in the same table unnormalised.**

**Two harness defects found while reading the result:** the funnel ignores `max_content_page` and
so does not mirror deployed retrieval — arm-asymmetrically (2.15% of the rerank arm's top-20 slots
are back-matter pages the app never serves, vs 0.95%) — §D8; and RRF fusion is not
bit-reproducible at the pool level even with HyDE pinned (7/133 queries at B4, 2/133 at B5; the
top-20 was stable) — §D10.

### UI — text-query visual search (2026-10-14)

The visual tabs — admin **Visual Search** and student **Find a Figure** — now accept a **typed
description** as well as an uploaded image: a `Describe it / Upload an image` radio drives the same
ColPali MaxSim search via `embed_query_text` (local, no re-ingest). Duplicate pages no longer appear:
`store.visual_search` collapses by page, and `save_colpali_embeddings` now replaces a document's
pages instead of accumulating another copy (**§B4b**, both halves fixed in code; the existing 2,835
points are still 3× until a re-ingest/cleanup). A text query **ranks, not filters** — the 0.58
threshold is image-calibrated (**§B4e**). Tests: `tests/test_visual_index.py` (4).

### Next actions before Session 4 (ordered — do in a FRESH session)

1. ✅ **DONE (3b) — Prune + re-verify the negatives.** Dropped `neg-nea-004`; `neg-in_-001` kept
   (its only YES was the index, now gated); 6 flagged `needs_review`. `data/eval_negatives.json`
   now holds 23 negatives. Residual uncertainty (content PARTIALs) → Session 5.
2. ✅ **DONE (3b) — Stop index/back-matter pages counting as hits.** Two layers: (a) the judge gate
   caps index pages at PARTIAL (scanner, deterministic — not prompt-only, since the VLM is
   inconsistent on the index); (b) `max_content_page` excludes back matter from retrieval. The gold
   labels were checked and carry **no** back-matter pages. See "Index-page false hits" below.
3. ✅ **DONE (3c) — the overview lane.** **40 overview queries**, topics from the book's section
   headings, every one scan-labelled over the whole book (stride 4 + term sweep, ~36k judge
   calls). Round 1 produced 40 topics of which 1 (`ovw-026` Energy-Momentum Tensor) was absent
   from Vol 1 and 8 were narrow (≤15 pages); **round 2 replaced those 8 with 9 new book-spanning
   topics** (min 22 / median 58 / max 314 pages). Negatives 23 → **34** (2 dropped as answerable
   by the term-bearing re-scan, 9 flagged `needs_review`).
   Assembled: **135 answerable + 34 negatives = 169 → 20.1% negatives**.
   Artifacts: `data/eval_queries_gold_overview_expanded.json`, `data/eval_negatives.json`.
   Targets + deviations: `.hermes/plans/2026-10-13-p0-9-3c-preregistration.md` (Outcome + Round 2).
4. ✅ **DONE (3d-ii) — visual queries + labels.** Built the **visual generation path**
   (`generate_gold_dataset.py --visual-count`, text-only generator, one figure question per
   `<!-- image -->` page in the content region) → `data/eval_queries_gold_visual.json` (**40**,
   pages 37–915); the **D8 visual judge variant** (`_VISUAL_JUDGE_PROMPT`, strict) + the anchor
   window in `validate_eval_calibration.py`; the book-wide scan →
   `data/eval_queries_gold_visual_expanded.json`. **33 usable** of 40 (6 uncalibrated, `vis-024`
   dropped as non-specific) — **§B4d**. Commit `3a18da4`.
5. **⛔ STILL OPEN — Normalise the gold labels' page numbering** (`IMPROVEMENTS.md` §D4).
   `relevant_pages` mixes DB page numbers (from the generator) with PDF page numbers (from the
   scan); measured, they differ by 0/−1 on ~45% of pages (and up to +2, §D4's visual note). It was
   to be done **before** Session 4 assembled v2 and **was not** — so the A/B numbers above carry
   about a page of label noise, which is also the floor under how finely the reranker delta can be
   read (pre-registration §6).

### Next — the Session 4b plan (ordered; do in a FRESH session)

> **Session 4b, not "Session 5"** — `p0-9-SESSIONS.md` already assigns Session 5 to human
> verification (Task 7). This is a follow-on to Session 4, named per the 3b/3c/3d-ii convention.

**Scope decision (2026-10-14, Bharath):** tasks 1 and 2 below are done **together** — fixing the
funnel changes the numbers and normalising the labels changes them again, so both land before the
re-run, which then yields **one** clean number instead of two moving ones.

0. ✅ **DONE (`12e0dd5`).** `logs/p0-9/v2_{rerank,norerank,hyde}.json` + `run_session4_v2.sh` are
   tracked; the A/B evidence is in git.
1. ✅ **DONE (`769e60d`).** The three harness defects fixed:
   a. `required_n.py` — `--queries` is now **required** (§D7). Verified: reproduces n=133, SD_d
      0.1163, required N 43.
   b. `funnel_boundary_recall.py` — `max_content_page` applied in `build_filter` **and** `post()`,
      mirroring `store.py` (§D8).
   c. `logs/p0-9/run_session4_v2.sh` — step 3 passes `--queries`; `set -e` + `ERR` trap abort on a
      failed step.
2. ✅ **DONE — REFRAMED, no labels changed (§D4).** Re-measured: the DB `page_number` and the PDF
   page index are **one coordinate system** with inherent ±1 chunk-boundary fuzz (`SentenceChunker`
   merges across page boundaries), not two numberings; `chunks` stores no PDF-page field, so there
   is nothing to reconcile. No label edit can remove the fuzz, and it is **symmetric across the A/B
   arms** → a known noise floor, not an open defect. Durable fix folds into the E1/E2/E3 re-ingest.
3. ✅ **DONE (2026-10-15, `logs/p0-9/session4b_rerun.log`).** Funnel re-ran post-fix, same 133
   queries, HyDE cached (**no LLM calls**). **Δ −0.0101, 95% CI [−0.0299, +0.0097] → still
   UNRESOLVED at n=133.** The §D8 fix raised every pre-reranker boundary (B1 0.7924→0.7999, B5b
   0.4495→0.4492) and moved the headline delta by **0.0006** — inside the noise. Full table +
   per-type: pre-registration → "Session 4b re-run".
4. ✅ **DONE (2026-10-16, 20:13–21:22) — step 4 (`evaluate_rag.py` on v2) ran.** `--skip-visual`,
   `logs/p0-9/session4b_step4.log` → `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md`. Measured
   the *other half* of the pre-registered decision: **abstention 17/34 = 0.500** (> the 0.0 majority
   baseline → **met**) and the text-lane generation metrics (Faith 0.661 · Ans.Rel 0.852 · Citation
   1.000, n=133). The **visual lane** (33 q) was measured **separately**: **R@20 0.960**
   (`p0-9-gold-v2-visual_2026-10-17_0410.md`). §B4f and §D11 resolved. Outcome: pre-registration →
   "Step 4 outcome"; registered `IMPROVEMENTS.md` §D12.
5. ✅ **DECIDED (2026-10-16, owner) — keep the reranker enabled for now.** The observed 0.011 needs
   **n≈934** to resolve while the pre-registered δ=0.05 needed only **43**, so "extend in blocks of
   30" (§5) reaches δ≈0.026 at n=163 and can never resolve 0.011. Decision: **do not drop it and do
   not extend the query set** — settle it with a **fresh ablation / A-B after the re-ingest**
   (E1/E2/E3 + §E5 + §D4), when the label fuzz and chunk-boundary noise that currently swamp the
   effect are removed. Keep the **factual-lane** loss (−0.0469, resolved) as the hypothesis to
   re-check. Rejected: (i) drop now (cost is small, effect unresolved not proven-negative);
   (ii) extend (0.011 needs n≈934; §5 forbids extending until an arm wins). Registered `§D13`.
6. **Only then P1 item 10** (ranking) — and drive it off the **ceiling-normalised** numbers (§D9),
   not the raw overview R@20 of 0.14.
7. **Runnable NOW, no cluster — Session 5 (human verification, Task 7).** Prepared 2026-10-16:
   fill in `data/gold_v2_review.md` (**30 queries, 6 per stratum**), then
   `uv run python scripts/score_review_sheet.py`. Protocol (sample, verdicts, the ±1 window
   rule, pre-registered consequences):
   `.hermes/plans/2026-10-16-p0-9-5-verification-protocol.md`. This is the productive thing to do
   while step 4 is blocked on the outage — it is the only P0-9 task that needs nothing but you.

### Index-page false hits (why + where)

**✅ FIXED (Session 3b).** (a)+(b) done as one deterministic gate in
`scripts/validate_eval_calibration.py`: `back_matter_start()` walks the trailing index run
(structural — heading marker or ≥35% of lines are "Term, <page-ref>" entries; start = **p937** for
Vol 1) and `apply_page_gate()` caps a YES there at PARTIAL. It is applied to the **verdict**, not in
the prompt, so the 12k-entry verdict cache stays valid — and it does not trust the 8B VLM, which
said NO on the index for one question and YES for another. (c) done as a retrieval bound:
`max_content_page` (config + `store.py`), set to **936** in `.env`. (d) `tests/test_backmatter_gate.py`.
Still open, and the durable fix: page bounds cannot be exact — the payload `page_number` is offset
from the PDF page index by 0/−1 on ~45% of pages, and DB page 936 holds **both** content and index —
so the real fix is **chunk-level classification at ingest: `IMPROVEMENTS.md` §E5**, folded into the
E1/E2/E3 re-ingest pass. The interim bound leaves ~15 index chunks (0.3%) retrievable; do not chase
the remainder with page arithmetic.

Original analysis (why): retrieval excludes front matter but **not** back matter: `store.py` filters on
`min_content_page` as a **lower bound only** (`page_number >= min_content_page` — lines 193, 228),
so the index/bibliography at pages ~940–968 stays retrievable. A `_NON_CHAPTER` keyword list
already exists in `store.py` (`"## subject index"`, `"## index\n"`, `"bibliography"`, …) but is
wired **only** into the RAPTOR rebuild path, not retrieval or the scan. Layered fix, cheapest first:
(a) judge criterion — YES means "this page contains the answer", index/contents/cross-reference
pages are PARTIAL at most (fits D8's graded 0/1/2, so the strict YES-only primary is unaffected);
(b) deterministic backstop — detect index pages by structure and gate them, don't trust an 8B VLM
(it said NO on the index for one question and YES for another); (c) corpus hygiene — an upper bound
(`max_content_page`) or exclude non-chapter pages at ingest, which removes the false-hit surface for
the product too (needs a re-ingest — its own item, honour the `clean_stale_*` ordering); (d) make it
visible — an index-page probe in the test suite, and/or a "fraction of retrieved pages that are
back matter" metric.

**✅ REFUTED 2026-10-16 (§B4g) — the index is NOT polluting the overview lane.** Back-matter pages
(`page >= 937`) occupy **0.32%** of the overview top-20 slots in the pre-fix funnel artifacts
(2/625) — the **lowest** of any type (factual 1.66%, multihop 0.68%); only 2 of 40 overview
queries touch one. P1 item 10 therefore need **not** wait on a back-matter fix. (The 0.191 MRR is
from the superseded v1 run and is not re-testable from disk — re-check on v2's per-type MRR after
step 4.) Original hypothesis, kept for the record:

Overview queries are the
ones an index page looks superficially good for, and overview MRR **0.191** is the one genuinely bad
number (P1 item 10). Cheap test: count back-matter pages (≥ ~940) in the retrieved sets for the
overview queries — if they are over-represented, the index is polluting the metric and the ranking
work in item 10 should not start until it is excluded.

### Decisions settled 2026-10-12 (do not re-litigate)

| # | Decision |
|---|---|
| **D1** | **Sequential design** — start at 40, extend in blocks of 30. **Recompute σ_d per comparison** (it differs: reranker 0.2315 vs merge 0.118). Do **not** stop naively at the first CI that excludes 0 — pre-register the stopping rule. |
| **D6** | **Fresh file** `data/eval_queries_v2.json`; **do not reuse v1's queries** — v1's provenance is mixed (early labels were retriever-derived → circular). Consequence: **all historical artifacts become non-comparable**; re-run the whole A/B series on v2. Do **not** carry v1's visual queries over — regenerate or calibrate them. |
| **D8** | **Graded 0/1/2** (NO/PARTIAL/YES). Report **Recall@k on YES-only as the strict primary**, graded nDCG as the secondary. D6 removes the v1-comparability constraint that forced a binary choice. |
| **D9** | **Scan the page as an IMAGE** (`Qwen/Qwen3-VL-8B-Instruct` on the cluster) **plus full text** — not the current `text[:800]`. Prerequisite for Task 4. |
| **D10** | Raise `max_tokens` (512 → 2048); make an empty generation batch **loud and asserted**, not a silent `[]`; bounded retry; log the raw response on failure. |

Also settled (2026-10-06): **3-way RRF *with* the cross-encoder stays**; the reranker decision is
deferred to the powered test (F4b). The ColBERT `is_query` fix (`b4cb637`) is correct regardless
of its unresolvable effect, and **needs no re-ingest**.

### Why P0-9 blocks everything — five conclusions, all unresolvable at n=23

σ_d = 0.2315 (reranker comparison, **measured** — `IMPROVEMENTS.md` §F4b) → SE ≈ 0.05 at n=23.
Paired-power **`N = 0.4206/δ²`** for the reranker: **62** to detect the observed 0.083, **169** at
δ=0.05, 43 at δ=0.10. The merge comparison is quieter (σ_d = 0.1184 → 45 at δ=0.05). Recompute σ_d
per comparison — do not reuse one number across comparisons.

| # | question | measured | verdict |
|---|---|---|---|
| 1 | does the cross-encoder help? | 0.651 → 0.569 (**−0.082**) | blocked |
| 2 | ColBERT better as voter or judge? | 0.598 vs 0.651 | blocked |
| 3 | did the ColBERT `is_query` fix help? | −0.022 / −0.049 | blocked |
| 4 | abstention precision | **unmeasurable** — zero negatives | blocked |
| 5 | any per-query-type claim | ~5 queries/type | blocked |

**Do not run another A/B on the 23-query set.** More measurements there generate more
unresolvable numbers, not more knowledge.

---

## P0 status

| # | Item | Evidence |
|---|---|---|
| 1–6 | baseline committed; silent fallbacks killed; sklearn pinned + classifier schema-checked; config-invariant tests; doc drift fixed; eval gate + CI | `6381f7b`, `c3a8727` |
| 7 | metric set fixed (`Precision@k` → `Recall@k` + `Hit@k`) | `1dad73f` |
| 8 | judge lane measured — **1040 judge calls, 0 failures** | `dce5efd`, `data/eval_results/p0-judge-canonical_2026-10-06_0010.md` |
| 9 | **gold-set rebuild** | Sessions 1–3c done — `ca3324e`, `52d2179` (measure) + `5cbf564`, `4f112b0`, `fffc3b3`, `c9d8d0c`, `668cd0f` (tools) + `1870dc9`, `8e81572` (scan) + 3b (negatives pruned, index gate) + 3c (`871a5a4` tools, `a6971f3` 40 overview questions, then the book-wide scan) + **3d code (`4697961`)** + **3d-ii (`3a18da4`, `18250f1` — 33 usable visual labels, §B4d)** + **Session 4 (`e69c347`, `f109379`)** + **Session 4b (`769e60d` harness fixes; §D4 reframed; funnel re-run) + step 4 (2026-10-16)** — v2 = 200 (166 answerable + 34 negatives); **abstention 17/34 = 0.500 (met), Faith 0.661, visual lane 33 q R@20 0.960** (`p0-9-gold-v2_2026-10-17_0422.md`). **✅ P0-9 is MEASURED — both halves of the pre-registered decision now have numbers (reranker unresolved; abstention met).** Reranker decision deferred to a post-re-ingest ablation (§D13). on `feat/p0-9-gold-dataset-v2` |

Test suite: **361 pass / 4 fail / 6 skip** (`uv run pytest tests/ -q -m "not slow"`, re-measured
2026-10-17 after Step 7b — 356/4 before it, +3 `test_config_invariants.py` dense-lane tests and
+2 `test_cluster_embedder.py` normalisation tests). The 4 are **pre-existing** and were
**re-confirmed on a clean `HEAD` worktree** (so they are not regressions from the query switch):
`tests/test_splade.py` (×2) hardcode a missing `tests/data/sample_physics.pdf`, and
`test_phase1.py::TestStore::test_hybrid_search_includes_global` +
`test_phase2.py::TestPhase1Regression::test_search_still_works_after_phase2` return 0 results.
The 6 skips are the live-E2E tests (they need `SV_EMBED_URL`). **Do not "fix" the 4 here.**

---

## Session hygiene

Start each P0-9 stage in a **fresh** session (`/new`) and read only that stage's section of the
plan. The previous long session reached ~271k tokens/call with 2 lossy compactions behind it —
**do not continue P0-9 inside a compacted session.** See `p0-9-SESSIONS.md` for the split and the
handoff steps.

**⚑ VERIFIER AT EVERY STEP — standing rule (owner, 2026-10-21).** Every logical step or diff
gets an independent verifier **before it is committed** — not one review at the end of a
project or a phase. Source changes, measurement probes *and the numbers they produce*, and any
doc or plan that asserts a measured number are all in scope. A step with no verifier is **not
done**, and is **not committed**. If the reviewer cannot run — it is pinned on the lab cluster,
and it is unreachable whenever this Mac is not on the home wifi — the step **waits**; it is
not merged on the author's own evidence. An unreachable reviewer, an empty response, or
`finish_reason=length` is **no verdict — never a pass**. Mechanical evidence (tests passing,
byte-identical re-runs, a probe's own output) is required but is **not** a second opinion, and
the record must keep the two apart. Full rule: `README.md` → "Verifier at every step".

**Read a verdict from the DELIVERED RESULT, never from the child's live transcript.** The
transcript truncates a long message (`…(+N chars)`), and nothing else on disk carries the full
verdict — the delegation directory holds only `manifest.json` (model, provider, status) and the
truncated `.log`. Measured 2026-10-21: the §G1 review's transcript exposed only **C1–C3 of seven**
claims before cutting off at `…(+1044 chars)`, and a later reviewer that trusted the transcript
reported a false mismatch against this file. Wait for the consolidated result before judging what
a reviewer did or did not check.

**⚠️ EMBED THE ARTIFACT UNDER REVIEW *AND* THE CLAIMS — a reviewer without them is no verdict
(§I54, 2026-10-22).** Two dispatches for the §G2 diff came back **UNVERIFIABLE × 10**: the first
carried a *description* of the change instead of the diff, the second carried the diff but not the
claim list. Both looked like cautious verdicts and were worth nothing. So: (i) paste the diff/source
and the numbered claims into `context` — never a summary of either; (ii) if the answer says it could
not see the thing, **re-dispatch — do not re-interpret it as a weaker verdict**; (iii) a review of a
600-line diff that returns in 10–25 s has not read it; (iv) a reviewer's *volunteered* findings must
be checked against the source, not accepted — the code-less round invented three defects, and the
round that had the code found a real one.

**Independent verification is a step, not a nicety.** Run `requesting-code-review`'s Step 5 on
every commit that changes source. `delegate_task` already runs on a different model
(`openai/gpt-oss-20b` — see "Verified facts"), so the independence costs nothing, but it is only
real if it is invoked: Steps 2 and 3 shipped unreviewed on 2026-10-17 and the reviewer immediately
found a genuine defect (a parent with no provenance silently gave every child `page_number=None`).
Budget `max_tokens` ≥32k for the reviewer — on a 300-line diff the hidden reasoning trace alone
exceeded 16k output tokens and the verdict came back empty. **Step 4 re-measured the ceiling:
32k is not always enough either** — one round ran 216 s, produced 126,818 characters of hidden
reasoning, hit `finish_reason=length` and returned empty content; trimming the prompt (drop the
test source) got a verdict. Treat an empty round as **no verdict, never a pass**, and expect two
rounds to be needed when the first one finds a defect (fix → re-ask on the fixed code).

---

## Priority plan (agreed)

**P0 — make the numbers trustworthy.** 1–8 ✅ · **9 ✅ gold set — MEASURED (2026-10-16); both
halves of the pre-registered decision now have numbers (reranker unresolved; abstention met).**

**P1 — then improve metrics.** The re-ingest is now the gating item:
 0. **Re-ingest (E1/E2/E3 + §E5 + §D4)** ⚠️ requires re-ingest — semantic chunking, parent/child
    hierarchy, late/contextual chunking, chunk-level front/back-matter classification, and
    per-PDF-page numbering. It removes the ±1 label fuzz (§D4) and the chunk-boundary noise that
    currently swamp the reranker effect; **the reranker ablation (§D13) and every metric below
    re-measure on the rebuilt index.** Honour the `clean_stale_*` ordering (§B4b, §E5).
    **Steps 0–7b done (2026-10-17)** — code, schema, write path *and* the query-side dense-lane
    switch. **Step 8 attempt 1 FAILED at 86 min (transient endpoint stall, nothing written) —
    §E7; the re-run is blocked on the §I16 retry/checkpoint fix.** Then Step 9 (Phase 2/3
    re-index, which also releases §I12/§I13).
10. **Ranking** — overview MRR is the one genuinely bad number (report it ceiling-normalised, §D9,
    not the raw 0.14). Cheapest first: config (MMR λ / RRF) → the cross-encoder → hard-negative
    fine-tuning. **The index-page hypothesis is REFUTED (§B4g)** — nothing gates item 10 on a
    back-matter fix. Run the **reranker ablation (§D13)** here, on the re-ingested index.
11. ✅ **SUPERSEDED** — v2 carries **33 calibrated visual queries** (§B4d); the old "7 uncalibrated
    visual queries" belong to v1. Re-check the visual lane after the re-ingest.
12. Per-lane attribution in the eval report (which lane moves which query type).
13. ✅ **DONE 2026-10-16** — Test the fallback chains. `tests/test_fallback_chains.py` (8
    tests) drives the real classes with a broken backend. Revealed §I9 (a failed embedding
    silently degrades to zero vectors). Not actually gated on P0-9.
14. ✅ **DONE 2026-10-16** — `render_math()` golden-file test.
    `tests/data/formula_split_golden.json` + `tests/test_frontend_formula_render.py` (10
    tests). Done as part of fixing §B1 (formula cards rendered prose as maths), which this
    test now pins. Not actually gated on P0-9.

**Also done 2026-10-16 (Group 2 UI/backlog pass, no cluster needed):** §B1 (formula
render), §I3 (Admin Status now shows store vs SQLite counts), §I5 (Topic/Difficulty fully
removed), §B2 half (already done in code), §B4g (index hypothesis refuted). Registered:
§B5 (Unicode maths in formula expressions is not valid LaTeX) and §I9 (zero-vector
embedding fallback).

**P2** abstention · guardrails · PPR · semantic caching · OKF cards

**P6 — kept, deferred to the very end:** NiceGUI migration. **Explicitly wanted — do not drop
it from the plan, and do not start it early.** Frontend stays Streamlit until then.

Full backlog, categorised by why each item is not done yet (queued / fix / deferred-by-decision /
gates), with cost classes and re-ingest ordering: [`IMPROVEMENTS.md`](IMPROVEMENTS.md).

---

## Verified facts — trust these over any doc

| Thing | Truth |
|---|---|
| Feynman Vol 1 PDF | **968 pages** (`mdls kMDItemNumberOfPages`) — README now correct; `Docs/synapse_full_report.pdf` still says 940 |
| Cluster `knowledge_base` | 5,135 points (5,051 chunks + 84 RAPTOR nodes), doc `6d55c52b` |
| SQLite `chunks` | 5,048 — the 5,135−5,048 gap is **unexplained; re-measure, don't trust** |
| Dense lane (query + `knowledge_base`) | **Qwen3-Embedding-0.6B, 1024d + 64d MRL** (`dense_model`/`dense_dim` in `config.py`), cluster `:8123`. The endpoint returns **unnormalised** vectors (norm ≈ 70–131) — normalised client-side for the pooled paths only. The query instruction IS applied (cos vs the same text as a passage = 0.8436) |
| Legacy dense embedder | **Nomic 768d + 64d MRL** (`embedding_model`) — **retired from the query path and from `knowledge_base`** (2026-10-17, §E6). Still builds `derivative_artifacts` + `concept_embeddings` and `reembed_chunks.py` until Step 9 (§I12/§I13) |
| Intent classifier | **Retrained at 1024d 2026-10-17** (`--train-only`, 1,158 queries, **96.6 %** held-out acc, macro F1 0.96). The router's schema check compares `n_features_in_` against `dense_dim`; a stale 768d model is rejected loudly → prototype fallback. 768d model recoverable via `git show 161e01b:data/models/intent_classifier.pkl` (the local `.bak` is gitignored) |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Chunker | `chonkie.SentenceChunker` (class named `SemanticChunker`) |
| Intent classifier (versions) | `LogisticRegression` on `dense_dim` features, pinned `scikit-learn~=1.9`, schema-checked at load |
| Card types | **8** in `CardType` (single source for `DA_CARD_TYPES`) |
| Eval queries (v1) | 30 = 23 calibrated non-visual + 7 uncalibrated `visual` — **superseded by v2; do not use** |
| Baseline (v1, 23 q) | Recall@20 **0.636** · Hit@20 1.000 · MRR 0.361 · NDCG@20 0.432 (`p0-judge-canonical_2026-10-06_0010.md`) — **not comparable to v2** (§D9) |
| Gold v2 | `data/eval_queries_v2.json` — **200** = 166 answerable (53 factual + 40 multihop + 40 overview + 33 visual) + 34 negatives (17.0%). The funnel's text lane is the **133** |
| v2 label sizes | text lane mean **22.2** pages (factual 9.5 · multihop 4.4 · overview **73.8**, max 314) → R@20 ceiling **0.8016** overall, **0.3992** on overview (§D9) |
| v2 funnel (133 text q) | pre-fix (2026-10-14): B1 0.7924 · **B5b retriever top-20 0.4495** · **B6 reranked 0.4389** · Δ **−0.0107**, CI [−0.0304, +0.0091]. **post-fix (2026-10-15, `769e60d`):** B1 0.7999 · **B5b 0.4492** · **B6 0.4391** · Δ **−0.0101**, CI [−0.0299, +0.0097] → **still unresolved** |
| v2 step 4 (133 text q, 2026-10-16) | R@20 **0.465** · Hit@20 0.947 · MRR 0.827 · NDCG@20 0.540 · Faith **0.661** · Ans.Rel 0.852 · Citation 1.000 (n=133; factual 0.564 / multihop 0.619 / overview 0.178). **Abstention 17/34 = 0.500** (> the 0.0 majority baseline → **met**). 164/200 synthesis, **4876 judge calls, 0 failed**, 3565.7s — `data/eval_results/p0-9-gold-v2_2026-10-17_0422.md` |
| Visual lane (v2, 33 q) | **R@20 0.960** · R@100 0.836 · Hit@20 1.000 · MRR 0.914 · NDCG@20 0.891 — **first measurement** 2026-10-16 (cluster `visual_knowledge_base`, ColPali text-query path; `data/eval_results/p0-9-gold-v2-visual_2026-10-17_0410.md`). §B4f resolved (base model cached); §I10 fixed the per-query 5.5 GB reload that OOM-killed the first try |
| Judge lane (v1, 23 q) | Faithfulness **0.701 (a floor)** · Ans.Relevance 0.927 · Citation 1.000 |
| Judge gateway | **`http://10.0.10.70:8000`** — serves `Qwen/Qwen3-VL-8B-Instruct` (the D9 VLM) among 6 models; ~0.8 s per page judgment at concurrency 1. The P0-9 plan's `10.0.10.51:8000` is **dead**. |
| Cluster LLM catalogue (probed 2026-10-17) | **Listed ≠ serving.** `/v1/models` returns 6 ids, but only **2 text models answer**: `openai/gpt-oss-20b` (200, ~0.3 s on a trivial prompt) and `Qwen/Qwen3-VL-8B-Instruct` (200). **`openai/gpt-oss-120b` is listed and 502 ×3** ("Backend inference unreachable"), as is `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (backend `10.0.50.71` down). Same trap class as §B4a's ColPali endpoint — re-probe, never trust the catalogue. |
| Verifier model | ✅ **CORRECTED 2026-10-20 (evening) — the pin IS in force; the previous version of this row was wrong and had it backwards.** Verified against the **live resolved config**, not against a note: `hermes config get delegation` returns `model: openai/gpt-oss-20b`, `provider: custom`, `base_url: http://10.0.10.70:8000/v1`, `fallback_providers: []`. In the raw `~/.hermes/config.yaml` the values sit at **lines 1942-1946, inside the `delegation:` block** — a long comment block is interleaved between `delegation:` and them, and the *template* lines above them are commented out. That is why it read as unset to anyone skimming: **the commented template line and the live value are adjacent and look alike.** So `delegate_task` children run a **different model from the parent** (`deepseek/deepseek-v4.1-flash`), and the fallback chain is `[]` (fail loudly, no silent degradation to the author's model). A child's `passed: true` is therefore a **real second opinion**, subject to the two limits below. **How to check what a child actually ran on (do this, do not infer it):** every delegation writes its resolved model to `~/.hermes/cache/delegation/live/<deleg_id>/manifest.json` — read `model` and `provider` there. Corroborated 2026-10-20: **every** manifest on disk back to 2026-10-15 (the oldest) reads `"model": "openai/gpt-oss-20b", "provider": "custom"`, including both children spawned that evening. `hermes config get delegation` gives the same answer for the next run. **Re-check with `hermes config get delegation` before relying on this row** — a pin recorded in a document ages silently, which is exactly how this row went wrong once. **Limits that still apply:** (i) the reviewer is on the cluster, so it is **unreachable whenever the lab network is down** — that is *no verdict*, never a pass; (ii) the historical record below still holds — a long **tool-using** session on that endpoint dies mid-run, so prefer a single-turn reviewer with the evidence embedded. **Historical record (2026-10-17), kept because its limit still applies to any cluster reviewer:** children then ran `openai/gpt-oss-20b` (cluster, alias `sv-gptoss`); it **cannot sustain a multi-turn *tool* session** — after 25 API calls the provider rejected the request as malformed because the model's own harmony control tokens (`<\|channel\|>commentary`) had leaked into message content. Single-turn tool calling works, so that verifier ran **single-turn with the evidence embedded**; a mid-run protocol failure is *no verdict*, never a pass. |
| Phase 2/3 LLM caller (2026-10-20) | `src/core/llm.py` — **300 s total-request deadline** (body read in chunks against a wall clock, raised as `ReadTimeout` so the retry catches it) + **3-attempt bounded retry** (jittered doubling backoff) on transport errors / 429 / 5xx, never on other 4xx. Failure contract unchanged (`""` + ERROR). Counters via `llm_call_stats()`. **⚠️ Covers the RAW path only** — with `use_instructor: true` in `config.yaml`, 4 of 8 card types go through the instructor/openai SDK and bypass it. `config.yaml` currently sets `use_instructor: false` (confirmed in `phaseb_run.log`), so all 8 are covered today. §I24 |
| Card-generation checkpoint (2026-10-20) | `data/card_cache/<doc8>__<key>.jsonl`, append-only + `flush`/`fsync` per chunk, keyed on `(document_id, card types, model)`; entries validated against the current chunk list on read. A chunk with a **failed** card type is re-attempted on resume. `run_phase2.py --no-resume` discards. `save_cards` is still the single write point. §I27 |
| Card-phase exit criterion (2026-10-20) | **`failed_card_types == {}`** in `run_phase2.py`'s output — NOT the absence of a `Failed:` row, which is vacuous (§I25). Still keep `verify_phaseb_cards.py` checks [3] (8 distinct card types) and [4] (cards/chunk ratio). |
| **Card throughput, measured (2026-10-20)** | Sweep + control sweep, 6 cells, ~40 min, 103 chunks, **zero failed chunks / zero LLM failures**: **3.18 chunks/min at `workers=1` (measured 3×: 3.77/3.02/2.74 — the last one at the END of the session, so no drift), 6.52 at 2, 9.39 at 4 (32 in-flight)**. **ETA 3,791 chunks: ~19.9 h / ~9.7 h / ~6.7 h.** Sustained p50 chunk wall time **64-105 s** — NOT the 10.1 s the plan's 10.6 h estimate used. **`workers=8` untested; the trend was still rising at 4.** §I26 |

---

## Traps

**→ `ARCHITECTURE.md` §8 (invariants and traps) and §11 (environment notes).** Read §8 before
your first change. The three that matter most for P0-9:

- **ColPali MaxSim is not 0-1** — scores run to ~1031; the configured threshold is 600.
- **Re-run `clean_stale_visual.py` after every Phase 3 re-ingest** (and `clean_stale_graph.py`
  after every re-ingest), or every page returns twice.
- **Retrieval is not bit-reproducible** (HyDE at temperature 0.3) — nothing below ~0.07 is
  measurable until HyDE is pinned. Pin it before any P0-9 A/B.
- **The judge must be a VLM, and `JUDGE_MODEL` is unset in `.env`.** The D9 scan sends the page
  **image**, so `--judge-from-env` alone judges with `openai/gpt-oss-20b` — text-only, it cannot
  see the page. Pass `--judge-model Qwen/Qwen3-VL-8B-Instruct` (and `--judge-api-base
  http://10.0.10.70:8000`) explicitly for the Session 3 scan.

---

## Unrelated to this project

The `reliability-lab` plugin injects a "[Reliability lab — pipeline A]" banner into the user turn
when this profile is armed (`mode: "A"`). It is **profile-wide**, so it leaks into unrelated chats.
Disarm with `/lab off`.
