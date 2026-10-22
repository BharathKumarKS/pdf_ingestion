# HANDOFF.md — current work state

> **Living document — where we are *now*, not what the system is.** The durable map is
> `ARCHITECTURE.md` (read **§8 Invariants and traps** before your first change); the backlog is
> `IMPROVEMENTS.md`. Keep this file short — it loads into every session.
>
> **Last updated: 2026-10-21, session 4. Landed and verified: §I23's checkpoint + honest failure
> count, the `resume` plumbing that makes its `resume=False` reachable from the CLI, and §I23(d)'s
> device selection. Earlier this day: §G1 (PPR) + §G2 (Leiden), §I21 (Phase 3 applies the E5
> filter), and the §G1 ablation — which came back NEGATIVE. The standing rule is
> **verifier at every step** (`README.md` → "Verifier at every step"; Session hygiene below).
> ⚠️ **The tree is CLEAN — the three in-flight files are committed, see item 0 below.**
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
> - **§G1's remaining decision (owner):** the ablation says re-ranking alone is not the lever.
>   Either **keep the fixed-hop ranking** and close §G1 as measured-and-negative, or authorise the
>   **expansion arm** (PPR to *select* candidates, not just order them) — that is the experiment the
>   null result leaves open. Do not re-run this ablation unchanged and expect a different answer.
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
> 2. **§I23 (c) — the one thing left before the rebuild, and it is an OWNER decision.** (d) is
>    **DONE** (`1fa94a3`, item 0d). (c) is the extraction-model choice, and it must be settled
>    **before** the rebuild rather than during it: the checkpoint key includes the model, so a
>    mid-build switch re-extracts everything. Measured on one realistic 2,000-char chunk:
>    `openai/gpt-oss-20b` (a *reasoning* model on a JSON extraction task) **12.9 s, 1,244 completion
>    tokens of which 4,495 chars were hidden reasoning, 10 concepts / 10 prerequisites**;
>    `Qwen/Qwen3-VL-8B-Instruct` **3.2 s, 166 tokens, 0 reasoning chars, 5 concepts / 3
>    prerequisites**. Both valid JSON. ~4× build time at a real quality cost — the numbers are in
>    §I23, and the comparison §I23 asks for has not been run.
> 3. **THE GRAPH REBUILD** — the gate that releases §G3, and the only remaining prerequisite. It
>    needs `QDRANT_HOST=10.0.10.65`, the cluster up, and **days not hours**: budget from §I23's
>    measurement, not the plan's 2 h estimate. The new checkpoint makes it restartable; read
>    `failed_chunks`, not the exit code.
> 4. Then **§G3** (entity resolution — §I30's lever: 1,186 merge groups, 34.4 % of the vocabulary),
>    then **§G2** community summaries.
>
> **OPEN OWNER DECISIONS:** (i) **§G1** — close it as measured-and-negative and keep the fixed-hop
> ranking, or authorise the **expansion arm** (the ablation's null leaves that open; do NOT re-run
> the ablation unchanged); (ii) **§I34** — a re-ingest transition reports the graph lane as SKIP:
> non-blocking or a hard blocker?; (iii) **§A3** — card volume vs quality; (iv) whether `e78a7ef`
> should be amended now that §G2 is fully verified (it still carries no `[verified]` prefix, on
> purpose: §G1's ablation was outstanding at the time and has since returned a null).
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
> — non-blocking as built, or a hard blocker?); **§A3** (card volume vs quality); **D3** (commit the
> untracked graph-analytics plan). **B1 (the §G3 merge) is still NOT authorised.**
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
