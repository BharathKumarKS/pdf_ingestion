# P1 — Stage F, RE-REGISTRATION: the DA lane is OFF in both arms, and E8 is re-pointed to §3d

> **Written 2026-10-25, session 20 (S5 continued), BEFORE the A/B run.** This restates **two clauses**
> of the pre-registration (`.hermes/plans/2026-10-25-p1-stageF-product-endpoint-preregistration.md`,
> committed alone as `51de3f2`): **§3's "the DA lane (ON)"** and **§7's E8** (arm A reproduces Phase E).
> Everything else in the pre-registration stands, unchanged. Per §I67 (E4 → E4′) and §I71 (C2 → C2′),
> a re-registration is legitimate when it is **restated by measurement** and **committed before the
> run** — and it is **not** a relaxation: it removes a confound the run would otherwise carry silently.

## 1. What the run found, and why the pre-registration cannot be run as written

The pre-registration (§3) pins **the DA lane ON in both arms** and (§7, E8) requires **arm A to
reproduce Phase E's v2 retrieval row**. A smoke test of arm A (3 queries) showed **both are
unachievable**, and the reason is structural, not incidental:

* **`search_da` queries with the DENSE query vector.** `store.search_da` (`store.py:722`) sends
  `query_vector.tolist()` to `cfg.da_collection` — and that vector's **dimension IS the arm's
  `dense_dim`** (1024 for A, 768 for B). A single `derivative_artifacts` collection can therefore
  serve **only one arm**.
* **`derivative_artifacts` is a single 768d collection** — re-created at 768 by §I83 (S4's preflight
  work, to match the nomic config). Measured this session on `10.0.10.65:6333`:
  `derivative_artifacts` = **73,406 points, VectorParams size 768** (unnamed vector).
* **So arm A's DA lane fails:** `search_da` returns HTTP 400 (`Vector dimension error: expected dim:
  768, got 1024`), `store.py:748` logs a **warning** and returns `[]` — the lane is **silently
  skipped**. Arm B's DA lane (768) is live. That is **arm B with an extra lane and arm A without it**:
  a **non-single-variable** A/B, and exactly the §I56 unattributability hazard the pre-registration's
  §5 was written to avoid.
* **And arm A no longer matches Phase E.** Phase E (2026-10-23) ran when `derivative_artifacts` was
  **1024d** and the arm was Qwen3/1024, so its DA lane was **live**. §I83 re-created that collection
  at 768 on 2026-10-25. So E8 as written fails **by construction**, not by drift.

⚠️ **This is a RECURRENCE of a registered defect, not a new one.** §D15 / §I12 already recorded the DA
lane dying on **"768-vs-1024"** in the §3d run (2026-10-19: *"the DA lane is absent — dead on every
query (§I12 update: 768-vs-1024)"*, 152 DA-lane skips across 166 non-visual queries). The mechanism is
the same; only the direction of the mismatch has flipped (then the index was 768 and the query 1024;
now the DA collection is 768 and arm A's query is 1024).

## 2. The re-registration — three changes

**(a) The DA lane is OFF in both arms** (`DA_ENABLED=false`, exported by `run_stageF.sh` and
**asserted** in the harness — a run that forgets it aborts, E2′). With the lane off, the arms differ
**only** in the dense lane and the index it queries — the treatment.

⚠️ **This NARROWS the question, and it is stated, not hidden.** The pre-registration's §1 asked
whether nomic/`v3` beats qwen3/`v2` **at the product retrieval endpoint**. With the DA lane off, the
run is a **dense-lane** A/B (`dense(low→full) + sparse + colbert → RRF → page dedup → MMR →
cross-encoder`) — the product funnel **minus one recall lane**. It is the honest, single-variable
version of the question the environment can actually pose today. The full-funnel comparison remains
**unmeasured** and is named as such.

**(b) E8 is re-pointed from Phase E (DA ON) to §3d (DA OFF).** The new anchor is the registered
**DA-off retrieval-only v2 row** — `data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md`
(§D15):

| scope | R@100 | R@20 | Hit@20 | Ctx.Prec | MRR | NDCG@20 | n |
|---|---|---|---|---|---|---|---|
| **§3d overall (anchor)** | 0.626 | **0.452** | 0.910 | 0.261 | 0.728 | 0.508 | 133/133 |
| factual | 0.746 | 0.570 | 0.868 | 0.148 | 0.704 | 0.447 | 53 |
| multihop | 0.633 | 0.543 | 0.875 | 0.104 | 0.615 | 0.504 | 40 |
| overview | 0.459 | 0.206 | 1.000 | 0.568 | 0.873 | 0.592 | 40 |

**E8′:** arm A's aggregate **R@20 must land within ±0.020 of 0.452**. The tolerance is the **n = 133
resolution floor** (`1.96·SD/√133 ≈ 0.020`, §0's doctrine) — a **pre-existing, derived** quantity,
**not** a number chosen to fit this run. **Arm A is the control and the instrument check**; if it does
not reproduce §3d, the harness has drifted from the registered instrument and the run is **VOID**.

**(c) The GRAPH lane is OFF in both arms** (the harness patches `graph_builder.get_graph_builder` to
a no-op; asserted in `meta.graph_lane`). ⚠️ **The same defect class as (a), found the same way — by
running.** `graph_search` (`graph_builder.py:504`) ranks concepts through `_find_concepts_scored`,
which queries **`concept_embeddings`** — and §I83 re-embedded **that** collection at **768d** too. So
arm A's 1024d query 400s, `_find_concepts_scored` catches it and returns `[]`
(`graph_builder.py:686`), and the lane is **dead in A, live in B** — the DA-lane asymmetry again, on
the multihop path. ⚠️ Measured: the failure **does not** call an LLM (the warning text *"falling back
to LLM"* is misleading — the handler returns `[]`), so it introduces no nondeterminism; it is an
**asymmetry**, not a noise source. Off in both arms.

⚠️ **Together (a) and (c) mean the whole DERIVED layer (DA + graph) is nomic-only right now** — both
collections are 768d after §I83. That is a fact about the environment, not a choice: a 1024d arm
cannot query either. The base lanes (dense + sparse + colbert) are what this A/B measures.

⚠️ **§3d's own confounds are carried, and they are small but real** (§D15 lists four; the two that
bear here): §3d **predates §I68's funnel swap** — which §I84 proved **endpoint-identical** (ΔR@20 =
0.0 on all 133 queries), so it cannot move R@20 — and it **predates the §I58 label re-points** (1–3
queries: `gold-003` [30]→[34] and two ±1 queries). Both are named; neither is expected to exceed the
floor, and the residual is **reported**, not assumed away.

## 3. What is NOT changed

* Arms **A = `knowledge_base_v2` / `Qwen/Qwen3-Embedding-0.6B` / 1024 / 64** and **B =
  `knowledge_base_v3` / `nomic-ai/nomic-embed-text-v1.5` / 768 / 64** (§3's table), the per-arm
  prefixes, and the E1/E2 assertions.
* **HyDE ON and frozen** (§4) — served from `data/hyde_cache/` by monkeypatching `call_llm`; a miss
  raises.
* The **product retrieval path**: each arm calls the product's own `evaluate_rag.run_retrieval`
  verbatim (embed → HyDE → `store.search_with_das` → [graph lane, now patched off, §2c] → shipped
  cross-encoder) and scores with the product's own `evaluate_rag.compute_retrieval_metrics`.
* The **endpoints** (§5): **P1** = paired Δ cR@20 ceiling-normalised (§I58), **P2** = paired Δ R@20
  raw, both **B − A**; S1 secondaries; S2 per-type. ⚠️ The **page convention is the PRODUCT's — pages
  of the top-k CHUNKS** (`evaluate_rag.py:333-341`), not §I70's top-k PAGES. ⚠️ The **ceiling
  convention is §I58's** — `cR@k = mean(R@k) / mean(achievable_max)`, a **global divisor** (this is
  what reproduces §I64's 0.4453 = 0.4250/0.9545 and 0.5275 = 0.465/0.8806) — **not** the per-query
  top-k-slot normalisation §I84's `cr20` uses (≈4.44). The two are not interchangeable.
* The **reading rule** (§6), the **power** reporting (§8), and the **verifier** (§9).
* The other guards: **E4** (negative control: an arm run twice is bit-exact — legitimate now that
  §I68 landed), **E5** (aggregates re-derive from the per-query array), **E6** (§I55 fallbacks named),
  **E7** (pool > 20). **E3** (133 in every arm).

## 4. Added: the DA-gap diagnostic (informative, not a guard)

Because the DA lane is off in arm A while **Phase E** measured it **on**, the artifact reports
`DA_gap = mean R@20(A, DA-off) − Phase E's 0.4250`. §I56 measured the DA lane at **−0.0262** on top-20
R@20 (§I64's consistency note is consistent), so the gap is **expected ≈ +0.026** — removing a lane
that hurt. It is a **cross-check on the re-registration's premise**, reported either way.

## 5. Preconditions (all hold)

1. ✅ §I68's fix is **committed** (`939beae`) — the funnel is deterministic, so E4 is a real control.
2. ✅ `knowledge_base_v3` is populated (3,796 points, four lanes, §I81).
3. ✅ The HyDE cache resolves for this run (§4 of the pre-registration).
4. ✅ The per-arm environment is exported **and asserted** (§3; the A2 `.env` flip is not applied).
5. ✅ **This file is committed ALONE, before the run.** Nothing measured is in it.

## 6. Stated — the confounds this design does NOT remove

* **The DA lane is off**, so the run is not the full product funnel (§2a). **Named.**
* **RAPTOR is not in v3** (73 nodes are a separate step, §I81). ⚠️ This path
  (`search_with_das` → `search()`) **does not read RAPTOR at all** (`search()` excludes
  `raptor_summary`; the RAPTOR lane is a separate `search_raptor`), so its absence **does not touch
  this A/B** — recorded so it is not mis-attributed later.
* **The graph lane is off** too (§2c), for the same reason as the DA lane. So the multihop numbers are
  measured **without** the concept-graph lane; per-type numbers are reported.
* **One document, one day, one funnel.** No causal claim beyond these two indexes.
