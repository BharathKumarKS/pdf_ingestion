# P1 — LANE INCLUSION: does making a lane a first-class RRF participant change its sign? (pre-registration)

> **Written 2026-10-29, BEFORE any number of this run exists.** Per **D6.1** it is **committed ALONE**.
> Plan of record: `.hermes/plans/2026-10-29-p1-lane-inclusion-plan.md` (steps S1–S5).
>
> Read first: `IMPROVEMENTS.md` **§I96** (the silent lane dropouts, now counted), **§I97** (T4), the plan
> above, `logs/p1/step10/nomic_gap_report.md` §6, `store.py` (`search_with_das`, `search_fused`),
> `evaluate_rag.py:218-246`.

---

## 1. The question

Three lanes are wired so they **cannot displace a fused hit** (plan §0): the **DA** lane is appended
after the vector fusion; the **graph** lane is appended by the caller **after dedup/MMR**, with a
fabricated `score` that passes any threshold; **RAPTOR** is absent from the index and never called on
the eval path. Measured today: **DA is a harm** (−0.0262, §I56); the **graph lane lowers MRR**
0.781 → 0.667; **overview** is the worst type (R@20 0.1882, ceiling 0.3992).

⚠️ **The registered question is NOT "does this improve things".** It is: **does making a lane a
first-class RRF participant change its sign and its ordering, versus appending it?** For DA and graph
a null — or a continued harm — is a real, recordable outcome.

## 2. Arms (one index — `knowledge_base_v3` + RAPTOR, nomic-768 — HyDE frozen, read-only)

| arm | what it is | isolates |
|---|---|---|
| **F0** | **today's wiring** — DA appended post-fusion, graph appended post-MMR, RAPTOR absent | the reference; anchors on T0/T4's rows |
| **F1** | **DA into the fusion** (`search_fused(lanes=("da",))`) | the DA lane's placement |
| **F2** | **graph into the fusion** (`lanes=("graph",)`) | the graph lane's placement |
| **F3** | **RAPTOR added** (`lanes=("raptor",)`, overview queries) | the missing overview lane |
| **F4** | **all three fused** + optional lane weights | the combined placement |

⚠️ **ONE lane change per arm** — they are mutually confounding otherwise.
⚠️ **F4's weights are EXPLORATORY** and are not a ship candidate on their own (§E2).

## 3. The unit, and the ceilings

Page-level, the product's convention — *pages of the top-k chunks*, page-deduped — **with both
ceilings** (§I93): `P-ceil@k = min(n,k)/k`, `R-ceil@k = min(k,n)/n`, both properties of the labels.

**Reported per arm:** coverage of a query's reachable labelled pages, `R@20`, `P@20`+`P-ceil`,
`F1@20`, `nDCG@20`, `MAP`, **`MRR@20` (endpoint — `mrr_at_20`, NOT the pool `mrr`, §I95)**, `Hit@20`
— overall and per type.

## 4. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **lane health per query** — the ColBERT, DA, RAPTOR and graph counters (§I96) must show **no dropout survived into any accepted call**, in every arm. ⚠️ An arm scored on a reduced lane set is not that arm |
| **G2** | **F0 reproduces T0/T4's rows** — the anchor that makes the comparison meaningful (tolerance 1e-4) |
| **G3** | **the pool is a SUPERSET of F0's** for the arms that only ADD a lane (F3), and the pool changes ONLY where the treatment says it should |
| **G4** | **no reranker fallback** on any query in any arm (§I55) — otherwise that arm's top-k is unranked |
| **G5** | **the lane actually fired**: each fused arm's artifact records a **non-zero count of candidates contributed by its lane**, per query. ⚠️ A fused arm whose lane returned nothing is a copy of F0 |
| **G6** | **133 queries, 0 errors** in every arm |

## 5. Predictions (registered BEFORE the numbers, so they can be falsified)

1. **F3 (RAPTOR) > F0 on overview** coverage and R@20 — the lane targets the worst type. **The largest
   expected movement**, because the lane is currently absent entirely.
2. **F1 (DA fused) does NOT reverse the DA lane's measured harm** — the lane is a harm for reasons of
   content, not placement; fusing it changes its rank, not its relevance. **A null is the expected
   result** and is reported as one.
3. **F2 (graph fused) ≥ F0 on MRR** — the graph lane's measured MRR cost comes from appending
   unordered candidates with a fabricated score; RRF gives it a rank. **If F2 does not recover MRR,
   the placement was not the cause and that is the finding.**
4. **F4 does not exceed the best single-lane arm** — lane weighting is not expected to be a free win.
5. **Coverage never falls** for an arm that only adds a lane (F3) — adding candidates cannot lower
   coverage of reachable pages.

⚠️ **A prediction that fails is the finding.**

## 6. Reading rule

* **n = 133**; floor ≈ **0.020** overall, ≈ **0.04 per type**. **Only the per-type effects are likely
  to resolve**, and the entry states `SD_d` and the `n` required for `δ = 0.05`.
* **Statistic, pinned:** paired difference per query; CI = **`mean ± 1.96·SD/√n`** over the per-query
  differences.
* ⚠️ **`unresolved` means KEEP THE STATUS QUO** — not a prompt to extend the sample.
* **Quote every recall against its ceiling**; **every precision with `P-ceil`**; **`mrr_at_20`, never
  the bare `mrr`**.
* **No causal claim beyond this index, corpus, CE model.**

## 7. Verifier — independent, stdlib only

`logs/p1/step10/lane_inclusion_verifier.py`, reading **only the written JSON**, re-deriving from the
raw per-query arrays: G1–G6, the per-arm aggregates, every paired delta with its CI, and every ratio
quoted. ⚠️ **Mutation-proved BEFORE the run**: each mutation reddens **exactly** its own check, and
**every check is reddened by at least one mutation** (no inert check).

## 8. Cost

**Read-only.** No writes, no re-ingest. **5 arms × 133 queries** at the measured ~2.5 s/query ≈ **28 min**,
plus the verifier and the mutation proof. ⚠️ Serialize against other cluster work.

## 9. Preconditions

1. `knowledge_base_v3` carries the RAPTOR lane (S2's carry-over) — verified by `raptor_v3_verify.py`.
2. `search_fused` exists and its tests pass (S4).
3. The lane counters exist (S1) and the ColBERT counter is live (§I96).
4. RAPTOR is wired onto the eval path (S3).
5. The HyDE cache resolves under the registered digest.
6. ⚠️ **This file is committed ALONE, before the run (D6.1).**

## 11. ⚠️ AMENDED BEFORE THE RUN — two findings from S2/S3, and the control arm they require

> ⚠️ **Placed here, immediately after §4/§5, because it CORRECTS them** — §10 follows below.
>
**Written 2026-10-30, BEFORE any number of this run exists.** Both findings come from the LIVE
probe `logs/p1/step10/lane_inclusion_s3_live_probe.{py,txt}`, not from a run.

**11a. The RAPTOR lane was wired and contributed NOTHING — a defect, now fixed.**
`store.search_raptor` returned `{"score": h.score, **h.payload}`: a RAPTOR summary's payload has **no
`chunk_id`**, and `_rrf_merge` keys a candidate on `chunk_id` falling back to `qdrant_point_id`
(§I84 — the fallback was added precisely because keying on `chunk_id` alone silently dropped the 73
chunk_id-less summary nodes). So **every RAPTOR candidate vanished inside `search_fused`**, and arm
**F3 as originally registered would have been a copy of its control** — a null by construction, not a
finding. Measured live before the fix: **0 of 2** RAPTOR candidates survived the fusion; after it:
**2 of 2** (`lane_inclusion_s3_live_probe.txt`). Fixed in `store.py` (`qdrant_point_id` carried
explicitly), pinned by `tests/test_lane_inclusion_eval.py::test_the_real_search_raptor_returns_a_key_the_fusion_can_use`
(mutation MV7). ⚠️ **This is G5's exact case** — *"a fused arm whose lane returned nothing is a copy
of F0"* — found before the run rather than by it.

**11b. ⚠️ The RAPTOR lane CANNOT add page coverage, and that is structural.**
A RAPTOR summary carries **no `page_number`** (measured: `page_number: null` on all 73 nodes). The
unit of this run is page-level, so a RAPTOR candidate can only ever **DISPLACE a page, never add
one**. §5's prediction 1 — *"F3 (RAPTOR) > F0 on overview coverage and R@20"* — therefore **cannot
hold through coverage as written**, and reading its failure as a finding about RAPTOR would be wrong:
it is a property of the unit and the lane's payload. **Restated by measurement (D6.2), not relaxed:**
F3's registered question is *"does the lane, as a first-class RRF participant, change the pool's
ORDER — and does the cross-encoder's top-20 move?"*, reported through `nDCG@20`/`MAP`/`MRR@20` and
through the **displacement count** (how many page-less candidates enter the pool and the top-20),
with coverage reported as a **predicted non-increase**. ⚠️ §5 prediction 5 (*"coverage never falls for
an arm that only adds a lane"*) is likewise restated: adding a page-less candidate **can** lower page
coverage by consuming a slot.

**11c. The arms are REPLACEMENTS, so §4's G3 as written cannot hold — and it needs a control.**
Each arm's lane set replaces today's wiring rather than adding to it: F3 is `lanes=("raptor",)`, which
**excludes the DA lane that F0 appends** (measured: F0's pool 88, F3's 75 on one overview query). So
F3's pool is legitimately *smaller* than F0's, and **G3's superset claim against F0 is false by
construction** — the over-strict-check class (§I90, and this pre-registration's own §13). **Corrected
to:** a new control arm **F0f = `search_fused(lanes=())`** — the vector lanes only, fused, no DA, no
graph, no RAPTOR. Then:
* **G3 is asserted against F0f**: `F0f ⊆ F1`, `F0f ⊆ F2`, `F0f ⊆ F3` (each arm adds exactly one lane
  to the same fused base), and the pool changes only where the treatment says it should;
* **every arm is now a SINGLE-VARIABLE contrast against F0f** (`F1−F0f` isolates DA's placement,
  `F2−F0f` graph's, `F3−F0f` RAPTOR's), which is what the plan's §1 "one toggle" intended;
* **F0 stays the product reference** and keeps its anchor (§4 G2), because it is today's wiring.
⚠️ `F4 − F0f` is the combined placement; it is **exploratory** and ships nothing.

**11d. The lane vectors are pinned, so the arms isolate PLACEMENT.** Dense and RAPTOR lanes get
`search_vec` (the HyDE vector the dense lane already uses); the **graph** lane gets `q_vec`, the raw
query vector the append path gives it today (`evaluate_rag.py:231`) — otherwise F2 would confound
placement with the vector. Pinned by
`tests/test_lane_inclusion_eval.py::test_fused_arm_passes_the_graph_lane_the_raw_query_vector`
(mutation MV3).

**11e. ⚠️ The graph lane's Cypher has NO stable `ORDER BY`, so a pool that includes it is NOT
reproducible — G3 is asserted only on the graph-free arms.**
Measured this session on one overview query, three IDENTICAL calls in one process:
`lanes=("da","graph","raptor")` returned pool sizes **90, 88, 90** (the page SET was stable here; the
candidate set was not), while `lanes=()` was **73, 73, 73** bit-identical. The code says so itself:
*"Without any ORDER BY this returned an arbitrary LIMIT — Memgraph's storage order"*
(`graph_builder.graph_search`), and `policy_confirm_RESULT.md` already recorded it as the cause of its
one L2 miss. ⇒ **G3 is asserted for F1 and F3 only** (graph-free, and only where the 100-slot cut does
not bind — `search_fused` calls `_mmr_select` only when `len(deduped) > fetch_k` and it DROPS
candidates); **F2 and F4's pool relation is REPORTED**, never asserted. ⚠️ Asserting a superset on an
arm whose lane is order-unstable is the over-strict-check class (§I90) with a measured mechanism.

**11f. ⚠️ F2's scope, stated: the graph lane fires for EVERY query type inside `search_fused`.**
Today's wiring appends the graph lane **only for `query_type == "multihop"`** (`evaluate_rag.py:224`),
while `search_fused` calls it whenever `query_text` is set. So `F2 − F0f` measures **placement** on
multihop (the type the lane targets — the registered primary read) and **INCLUSION** on factual and
overview, where today's product never calls the lane at all. Both are real questions; they are
**different** questions, and the per-type table is what separates them.

**11g. ⚠️ §4's G2 anchor cannot be asserted on OVERVIEW — S2 changed the index the queries search.**
G2 was written as "F0 reproduces T0/T4's rows". The correct reference today is the **live shipped
product run** (`policy_confirm.json`, one day earlier, same env, the shipped per-type rerank policy),
re-derived from **its own** per-query page lists. The smoke (5 queries) measures F0 reproducing it
**exactly on factual and multihop** and **diverging on overview in BOTH directions** — ovw-001 nDCG
**0.4068 vs 0.5909**, ovw-003 **0.4583 vs 0.2669**, aggregate MAP |Δ| 0.0202. ⚠️ **The mechanism is
S2's own write:** 73 RAPTOR points were added to the collection these queries search, so yesterday's
pool is not today's. **Corrected to:** G2 is asserted **per type on FACTUAL and MULTIHOP only**
(tolerance 1e-4); **OVERVIEW is reported** (`G2_overview_REPORTED_not_asserted`) with the mechanism
named. The instrument's determinism is separately evidenced: F0 is **bit-stable across two smoke
runs** on all six arms (`lane_inclusion_smoke.json` vs `lane_inclusion_smoke2.json` — pages, pool sha
and nDCG identical on 4/4 queries).

---

## 10. Stated — what this run does NOT do

* **It does not measure the generator stage** — retrieval only.
* **It does not ship lane weighting** — F4 is exploratory.
* **It does not change the embedder, the index or the labels.**
* **It does not re-open the fusion width** (§I67: measured inert at the endpoint) or the rerank-query
  policy (a separate change, already measured, and never in the same arm as a pool change).
