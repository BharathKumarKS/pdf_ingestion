# P1 — T4: the ENDPOINT ATTRIBUTION — is the pool → top-20 loss the cross-encoder, the 20-slot cut, or the CE's query text? (pre-registration)

> **Written 2026-10-27, BEFORE any number of this run exists.** Per **D6.1** it is **committed ALONE**, and
> nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 24), `IMPROVEMENTS.md` **§I90** (T0, the reference table this anchors
> on), **§I91** (T1 — the endpoint null), **§I92** (the fusion attribution), **§I93/§I94a** (metric
> provenance and the label question), `logs/p1/step10/nomic_gap_report.md` (the FINAL report this run
> exists to sharpen), and `evaluate_rag.py:189-258`.

---

## 1. The question

**T0 measured the funnel's largest single loss at the pool → top-20 step: coverage 0.6845 → 0.4553
(−0.2292).** ⚠️ **And its artifact already shows the cross-encoder making the top-20 WORSE than doing
nothing** — the `fusion` row is the pool's own RRF order and the `ce` row is the CE's order, and every
metric falls:

| metric | fusion (the pool's own order) | cross-encoder (the product) | Δ |
|---|---|---|---|
| R@20 | 0.4491 | 0.4442 | **−0.0050** |
| nDCG@20 | 0.5506 | 0.4946 | **−0.0560** |
| MAP | 0.3421 | 0.2789 | **−0.0631** |
| MRR | 0.7687 | 0.6668 | **−0.1018** |
| Hit@20 | 0.9323 | 0.9173 | −0.0150 |
| coverage | 0.6845 | 0.4553 | **−0.2292** |

⚠️ `R@100` is **not** shown: at the `ce` stage the list holds only 20 chunks, so `R@100` there equals
`R@20` **by construction** (T0's own note). The pool-recall figure is the `fusion` row's **0.6706**.

**⇒ Three candidate causes, with different fixes, and nothing has separated them:**

1. **The cross-encoder reorders badly** — it demotes the right page. *Fix: a better/additional re-ranker.*
2. **The 20-slot cut discards pages** — the CE's order may be fine but only 20 survive. *Fix: a wider cut.*
3. ⚠️ **The CE is fed the HyDE HYPOTHETICAL as its query, not the user's question.** `evaluate_rag.py:206`
   sets `rerank_query = hyp` for factual/overview — a hypothetical *passage* is used to score passages.
   *Fix: rerank against the raw query.* ⚠️ **This candidate has never been tested.**

## 2. Arms (one index — `knowledge_base_v3` / nomic-768 — T0's lane set, HyDE ON and frozen, read-only)

| arm | what it is | how | isolates |
|---|---|---|---|
| **C** | **the product** — CE reranks against the HyDE hypothetical, top-20 | `reranker_enabled=True`, `reranker_top_k=20` | the reference; anchors on T0's `ce` row (G1) |
| **N** | **no cross-encoder** — the pool's own RRF order, top-20 | `reranker_enabled=False` | **cause 1**; anchors on T0's `fusion` row (G2) |
| **Q** | the CE reranking against the **RAW query** instead of the hypothetical, top-20 | a recording wrapper substitutes the raw text at `reranker.rerank`'s query argument | **cause 3** |
| **W50** | the CE as in C, but the cut is 50 | `reranker_top_k=50` | **cause 2** |

⚠️ **Arm Q's instrumentation is a wrapper around the reranker call that replaces its query argument; it
changes no other behaviour.** It must be **proved to take effect** (G5) — otherwise Q is a copy of C.

⚠️ **Arm W50's k differs**, so its `R@50` is not comparable to `R@20`. **Report it against its own k and
its own ceiling**, and use it only to ask *"does a wider cut recover the pool's pages?"* — never as a
like-for-like endpoint.

## 3. The unit, and the ceilings

**Page-level, the product's convention** — *pages of the top-k chunks*, page-deduped — **with both ceilings
beside every number** (§I93): `P-ceil@k = min(n, k)/k` and `R-ceil@k = min(k, n)/n`, both **properties of
the gold labels**, identical in every arm.

**Reported per arm:** coverage of a query's reachable labelled pages, `R@k`, `R@100`(pool), `P@k` +
`P-ceil`, `F1@k`, `nDCG@k`, `MAP`, `MRR`, `Hit@k` — **overall and per query type**, and **R-ceil**.

## 4. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **arm C reproduces T0's `ce` row EXACTLY** — coverage 0.4553, R@20 0.4442, P@20 0.2398, F1 0.1911, nDCG 0.4946, MAP 0.2789, **endpoint MRR 0.6668**, Hit 0.9173. Tolerance **1e-4** — ⚠️ **not 1e-6 as first written**: every metric is `round(..., 4)`, so the values are quantised to 1e-4 and equality is exact; the tolerance is 1e-4 only so a legitimate future change to the rounding does not silently pass. (Independent review, item 4 — the document and the code disagreed.) |
| **G2** | ⚠️ **THE STRONG ONE — arm N reproduces T0's `fusion` row EXACTLY** — coverage 0.6845, R@20 0.4491, **pool** R@100 0.6706, P@20 0.2447, F1 0.1968, nDCG 0.5506, MAP 0.3421, **pool** MRR 0.7687, Hit 0.9323. Tolerance **1e-4**. With no CE the top-20 *is* the pool's top-20, and the pool is **page-deduped**, so the two conventions coincide — the reproduction should be exact |
| **G3** | **133 scored / 0 errors** in every arm |
| **G4** | **determinism: arm C run TWICE is bit-exact** on every metric of every query (§I68 landed) |
| **G4b** | ⚠️ **the same, on the METRIC DICTS** — G4 compares page lists, which implies metric equality only if the metric function is deterministic, i.e. the thing being asserted (independent review, item 2) |
| **G5** | ⚠️ **arm Q's instrumentation TOOK EFFECT** — Q differs from C on **at least one** query. A silent no-op would make Q a duplicate of C and the run's central question unanswerable |
| **G5b** | ⚠️ **the override FIRED on every Q call** — a counter inside the wrapper must equal the number of scored queries. "Q differs from C somewhere" is not the same claim (independent review, item 1) |
| **G6** | **the pools are IDENTICAL across C, N and Q** — same lane set, same `fetch_k`; the treatment is the **ordering only**. Asserted per query |
| **G6b** | ⚠️ **the same on pool CONTENT** — a hash of the pool's page list, not merely its length: two arms could return different pools of equal size and satisfy G6 (independent review, item 3) |
| **G7** | the **reachable-pages set is identical to T0's** (888 pages, set equality) — the denominator did not move |
| **G8** | **`fetch_k` is 100 in every arm** — which is what makes `recall_at_100` the POOL field G2 compares (independent review, item 7) |

⚠️ **G1 and G2 together are the instrument proof**: two *different* T0 boundaries reproduced by two
*different* arms. If both hold, the harness is T0's and the comparison between them is meaningful.

## 5. Predictions (registered BEFORE the numbers, so they can be falsified)

1. ⚠️ **N > C on nDCG, MAP and MRR** — **the cross-encoder is a net harm at the top-20.** T0's rows already
   imply it; this run is the paired test on one instrument. **A confirmed P1 is a PRODUCT-PATH finding.**
2. **Q > C on the same three** — part of the harm is the CE being scored against a hypothetical passage
   rather than the question.
3. **W50's R@50 recovers toward the pool's coverage 0.6845** — the cut accounts for the coverage loss.
4. **C > N on nothing** — if the CE helps no metric at the top-20, that is the honest headline and the
   "cross-encoder" stage is currently a cost, not a benefit.

⚠️ **A prediction that fails is the finding.** These are registered so the run can falsify them.

## 6. Reading rule

* **n = 133**; the resolution floor is **≈ 0.020** overall, **≈ 0.04 per type** (n = 40). The entry states
  the observed `SD_d` and the `n` required for `δ = 0.05`.
* ⚠️ **This run ships nothing on its own** — it **attributes**. But a confirmed **P1 or P2 is a
  product-path defect** (the CE is costing us, or its query text is wrong) and **licenses its own
  before/after**, pre-registered separately.
* **Quote every recall against its ceiling** (§I93) and **every precision with `P-ceil` beside it**.
* **Report per query type**, because the pool → endpoint step moves the three types in **opposite
  directions** (factual loses ordering while recall holds; multihop improves; overview is retrieval-bound).
* **No causal claim beyond these two indexes.** One corpus, one document, one day, one funnel.

## 7. Verifier — independent, stdlib only

`logs/p1/step10/t4_verifier.py`, reading **only the written JSON**, re-deriving from the **raw per-query
arrays**: G1, G2 (both anchors, field by field), G3, G4 (the repeat), G5 (Q≠C), G6 (pool identity), G7; the
per-arm aggregates; the paired C-vs-N, C-vs-Q and C-vs-W50 deltas with CIs; and every ratio quoted.

⚠️ **Mutation-proved BEFORE the run** (`t4_mutation_log.txt`): each mutation must turn **exactly** its own
check red, and **every check must be reddened by at least one mutation** (no inert check). ⚠️ **An
over-strict check is worse than no check, and a check that cannot fail is not a check** (§I90's lesson,
both directions).

⚠️ An independent cross-family reviewer (`openai/gpt-oss-20b`, read-only) on a **compact extract**, never
the full artifact.

## 8. Cost

**Read-only.** No writes, no re-ingest, no `src/` change. 4 arms × 133 queries at the measured ~2.5 s/query
plus arm C's repeat ≈ **22 min**, plus the verifier and the mutation proof. ⚠️ **Serialize against other
cluster work**; `socket.setdefaulttimeout(90)` + 3 retries per product-path call — ⚠️ **note that the
socket default did NOT bound a hang in T1 (a 979 s stall), so a multi-minute stall is possible and the run
should be watched rather than assumed.**

## 9. Preconditions

1. ✅ `knowledge_base_v3` holds the pooled nomic index (3,796); both derived collections are 768d, so the
   DA and graph lanes are **live** on this index (T0's lane set).
2. ✅ The HyDE cache resolves under the registered digest.
3. ✅ The cluster is reachable (Qdrant `10.0.10.65:6333`, router `10.0.10.70:8000`).
4. ⏳ **This file is committed ALONE, before the run.**

## 10. Stated — what this run does NOT do

* **It does not measure the generator stage** — retrieval only.
* **It does not test the fusion width** as a ship candidate (§I67 owns that, and its answer was a null);
  W50 exists to **attribute** the cut, not to recommend it.
* **It does not change the cross-encoder or its model.** If P1 confirms, the *fix* is a separate,
  pre-registered before/after.
* **It does not touch the labels** (§I94a: the 3 pointer labels are unrepaired and their effect is below
  the floor).

## 11. ⚠️ AMENDED before the run — `R@100` is a CONVENTION TRAP in this run's anchors

**Found while building the harness, and corrected here before anything was measured.** §4's G1 first
listed **`R@100 0.4442`** among the fields arm C must reproduce. **That number cannot come from this
harness**, and comparing against it would have been a check that fails on correct data:

* **T0's `ce` row computes `R@100` over the ce page list** — which holds only the **20** reranked pages —
  because T0 scores each boundary from that boundary's own ranked page list (`_metrics_from_pages`). So
  T0's `ce` `R@100` is **equal to its `R@20` by construction** (0.4442), as T0's own note says.
* **The product's `compute_retrieval_metrics` computes `R@100` over the POOL** (`retrieval["hits"]`), which
  the cross-encoder does not change. So arm C's `R@100` is the **pool recall**, which is **T0's `fusion`
  row's 0.6706** — *not* 0.4442.

⇒ **The corrected anchor set:**

| arm | `R@100` must equal | why |
|---|---|---|
| **C** | **0.6706** (T0's `fusion` `R@100`) | the CE reorders, it does not change the pool |
| **N** | **0.6706** | same pool |
| **Q** | **0.6706** | same pool |
| **W50** | its own `k` — report `R@50`, never as `R@100` | the cut differs |

⚠️ **And `R@100` is not an endpoint in this run at all** — it is a **pool** measurement, which is exactly
why T0's `fusion` row carries it and its `ce` row cannot. Registered here rather than silently fixed, since
a convention mismatch of this shape voided a run once (§I72).

## 12. ⚠️ CORRECTION — §11's conclusion was WRONG, and the smoke test found a SECOND, REAL trap in its place

**Written after the 8-query smoke test, before the full run.** The smoke's job was to prove the two anchors
before spending 22 minutes; it did that, and it caught two things.

**(a) §11 was wrong.** It claimed arm C's `R@100` must be **0.6706** and that comparing against T0's
**0.4442** would "fail on correct data". **The opposite is true, and the original G1 was right as first
written.** The harness scores each arm's **ENDPOINT page list** with **T0's own boundary convention** — the
same call shape `t0_baseline._metrics_from_pages` uses (`hits = hits_above = that boundary's list`,
`reranked = list[:k]`). Under that convention T0's `ce` row's `R@100` **is** its `R@20` (0.4442), and arm C
reproduces it. §11 reasoned from the **product's** `run_retrieval` shape (where `hits` is the pool) and
assumed the harness would inherit it. It does not.

**(b) But the product's shape hides a real trap, and §11 walked past it.** `compute_retrieval_metrics`
computes **`mrr` from `retrieval["hits"]` — the POOL** — and `recall_at_{fetch_k}` likewise. **Both are
therefore POOL metrics that are IDENTICAL in every arm and cannot answer this run's MRR question at all.**
⚠️ **The smoke proved it: the `P1_N_minus_C` and `P2_Q_minus_C` MRR deltas came back exactly `0.0` with
`ci95 [0.0, 0.0]` — a registered prediction that the harness could not have falsified.**

**⇒ The corrected structure, which is now the harness's:**

| row | `mrr` | `recall_at_100` | the rest (`ndcg@20`, `map`, `recall@20`, `precision@20`, `hit@20`) |
|---|---|---|---|
| T0's **`ce`** row | **endpoint** (scores the ce list alone) | endpoint (= `R@20`) | endpoint |
| T0's **`fusion`** row | **POOL** | **POOL** | endpoint (the pool's top-20) |

⇒ **G1 now compares the ENDPOINT fields only** (`ENDPOINT_KEYS`), and **G2 compares those plus the two POOL
fields** — which are valid for arm N precisely because its pool *is* T0's fusion pool. And the harness
**adds `mrr_at_k`, computed over the endpoint list**, so the MRR question is answerable; **arm C must
reproduce T0's `ce` `mrr` (0.6668) with it.**

⚠️ **A product-path finding falls out of this and is registered separately (§I95):** the product's own
evaluation reports **the pool's MRR under the name `mrr`**, so its endpoint MRR is **overstated by ~0.10**
(0.7687 reported vs 0.6668 actually achieved at the endpoint).

⚠️ **Two convention traps in one guard, found by an 8-query smoke that cost one minute.** Neither would
have been visible in the full run's aggregate — (b) would have silently produced "the hypothetical does not
affect MRR" from a metric that never measured the endpoint.

## 13. INDEPENDENT REVIEW — `openai/gpt-oss-20b` (a different model family) read this document and the harness's guard logic and returned **SPECIFIC CONCERNS**

**Method (§7):** a compact extract — this document verbatim (13.4 k chars) plus the harness's arms, guards,
delta and `_cov`/`_endpoint_mrr` sections (14.9 k chars) — sent read-only with an adversarial brief:
find guards that cannot fail, metrics that do not measure what is claimed, arms that are not different,
predictions the harness cannot falsify, and unit/convention mismatches. **Run before the full run, after the
smoke.** Log: `logs/p1/step10/t4_independent_review_log.txt`.

⚠️ **The review's value is that 5 of its 8 items were acted on — and that 2 were WRONG, which is recorded
rather than quietly dropped.**

| # | the reviewer's claim | verdict | action |
|---|---|---|---|
| 1 | **G5 is over-strict** — if the hypothetical equals the raw query, the guard fails on a benign coincidence | **weak in principle, adequate at n=133** — but a *direct* proof is strictly better | **FIXED** → **G5b**: a counter inside the wrapper must equal the number of scored queries, i.e. the override was *read*, not merely set |
| 2 | **G4 does not match its description** — §4 says "bit-exact on every metric" but only page lists are compared | ✅ **VALID** | **FIXED** → **G4b** compares the metric dicts too |
| 3 | **G6 checks pool SIZE, not pool CONTENT** — two arms could return different pools of equal length | ✅ **VALID** | **FIXED** → **G6b** compares a 16-hex-char hash of the pool's page list per query per arm |
| 4 | **G1/G2's 1e-6 tolerance will fail on rounding noise** | ✅ **PARTLY VALID** — the noise claim is wrong (the metrics are `round(..., 4)`, so equality is exact), **but the document said 1e-6 while the harness used 1e-4** | **FIXED** → §4 now says **1e-4** with the reason |
| 5 | **nothing proves the cross-encoder ran** — a mis-configured CE would still pass | ❌ **WRONG** — **G1 is that guard**: if the CE no-op'd in arm C, arm C would equal arm N and G1 would fail against T0's `ce` row | recorded, no change |
| 6 | the aggregate still carries the pool `mrr` under the bare name | ✅ **VALID as a labelling hazard** | **FIXED** → the artifact's `meta.field_conventions` now names every ENDPOINT field and every POOL field, with the ~0.10 gap stated |
| 7 | **`recall_at_fetch_k` is a pool metric and nothing asserts `fetch_k`** | ✅ **VALID** | **FIXED** → **G8** asserts `fetch_k = 100` in every arm |
| 8 | **`coverage_reachable` uses the corpus-wide denominator**, so drift would be masked | ❌ **WRONG** — it is `\|pages ∩ (rel ∩ reach)\| / \|rel ∩ reach\|`, per query; ⚠️ **the reviewer misread because the compact extract cut the call site and showed only the generic `_cov(pages, reach)` signature** | recorded, no change |

⚠️ **Item 8 is the method's own limitation and is worth keeping:** a **compact** extract hides call sites,
and a reviewer that cannot see the caller will infer the unit from the signature. **The extract traded
token cost for a false positive — and the false positive was cheap to adjudicate, which is the right trade,
but it must be stated rather than hidden.**

⚠️ **Consequence for the run:** the full run was **killed ~5 minutes in** and restarted, so the committed
artifact carries the strengthened guards (G4b, G5b, G6b, G8) and the labelled field conventions. **Cost:
one five-minute run. Benefit: four guards that can now fail where three previously could not, and one
document/code disagreement removed.**

## 14. ⚠️ THE FIRST FULL RUN **FAILED FOUR GUARDS** — its deltas are NOT reportable. Three causes, one of them a SILENT LANE FAILURE the artifact could not see

**Artifact `9fa21d6cf641199f…`, 133/133 scored, 0 errors, and `GUARD FAILURE: G1, G2, G6, G6b`.** ⚠️ **A
run that fails its anchors does not get to report an effect**, so none of its numbers are quoted anywhere.
The three causes are separable and all three are fixed:

**(a) G1 failed on ONE field, and it was a HARNESS BUG.** Arm C reproduced T0's `ce` row **exactly on all
seven comparable fields (Δ 0.0000)** — coverage, R@20, P@20, F1, nDCG, MAP, Hit. It failed only on
`mrr_at_20`, because **T0's `ce` row names its endpoint MRR `mrr`** and the harness's key list compared the
names instead of mapping them. §12 had fixed exactly this mapping **in the verifier and not in the
harness** — the same fix applied to one of two call sites, which is the defect pattern this project keeps
re-learning. ⇒ **G1_PAIRS/G2_PAIRS now carry explicit `(arm_field, T0_field)` pairs**, so a convention
difference cannot hide behind a matching key name.

**(b) G2 failed on coverage by 0.2251 — a CONVENTION error in the anchor.** T0's `fusion` row reports the
**POOL's** coverage (0.6845); the harness compared it against the arm's **ENDPOINT** coverage (0.4594).
Both numbers are correct; they are different quantities. ⇒ **a new `{arm}_pool_cov` field** is measured from
the pool pages, and **G2 pairs `pool_cov` against T0's `coverage_reachable`** while G1 keeps the endpoint
coverage. Verified per query on the smoke: arm N's `pool_cov` equals T0's `cov_fusion` **8/8 exactly**.
⚠️ **G2's residual differences (nDCG −0.0028, MAP −0.0038, pool-MRR −0.0038) all traced to cause (c).**

**(c) ⚠️ G6/G6b failed on ONE query — `gold-029`, arm N: 86 pages against 92 in arms C, Q, W50 AND T0 —
and the cause is a SILENT LANE FAILURE.** The run log held it:

```
ERROR | store:_qdrant_search:606 - ColBERT query FAILED (timed out);
                                     the colbert lane is inactive and results use dense+SPLADE only
```

**The store CATCHES that exception, logs it, and fuses from a REDUCED LANE SET** — so the pool is built
differently and is no longer the treatment. ⚠️ **Unlike the reranker (`reranker.fallbacks`) there is NO
COUNTER for it: nothing outside the log text can see it, and the harness could not.** A probe re-ran
`gold-029` under arm N's config four times: **92, 92, 92, 92 — stable**, confirming the 86 was a transient
dropout and not structural. ⇒ **three fixes:** the harness now **counts ColBERT query failures at the
embedder**, **retries the call** (bounded, 3) because such a call is not the treatment, and **records both**
(`{arm}_colbert_drop`, `{arm}_lane_retries`). **New guards: G9** (no dropout in any accepted call),
**G9b** (the arm C repeat had none — otherwise G4's determinism claim is void) and **G10** (the reranker did
not fall back in a CE arm, which would leave that arm's top-k unranked, §I55).

⚠️ **What this says about the whole run-integrity story:** the anchor that mattered most — arm C against
T0's `ce` row — **was exact**, and the guard that failed most informatively was **G6, a guard added two
hours earlier at an independent reviewer's request.** Without G6b the confounded query would have entered
the deltas silently, and **its bias runs AGAINST the finding**: a lane-reduced arm N is a *handicapped* arm
N, and it still out-ordered arm C.

⇒ **The full run was relaunched on the fixed harness.** The artifact this document's results come from is
the one that passes all thirteen guards.

## 15. ⚠️ THE ONE LEGITIMATE UNIT DIFFERENCE — the product's metric function scores CHUNKS, our re-derivation scores PAGES

**Found by the verifier on the PASSING artifact: 4 of 5,852 re-derived fields disagreed** — `gold-068` and
`gold-072`, arm **W50**, `ndcg_at_50` and `map`, by **≤ 0.0011**.

**The mechanism, measured.** For `gold-068` the pool holds **83 chunks but only 80 distinct pages**, and the
cross-encoder's top-50 contains **one chunk with no `page_number`**. The product's
`compute_retrieval_metrics` builds its **gains list over the CHUNK list**, so that page-less chunk
**contributes 0 but still consumes a slot**, shifting every later gain by one position. Our verifier
re-derives from the **PAGE list** (`_pages_of`, which drops it) — which is **T0's convention**
(`_metrics_from_pages` passes a page list).

⇒ **Both are correct; they are different units.** It cannot bite at k=20 on this corpus (the page-less
chunks are appended by the graph lane and never enter the top-20 — which is why all 133 queries of arms C,
N and Q re-derived **exactly**), and it bites only in the k=50 arm, whose `nDCG@50`/`MAP` **enter no
registered prediction** (P3 uses coverage).

**Three things done about it, and none of them is to call a correct artifact wrong:**
1. ⚠️ **The harness now records `{arm}_slots`** — the endpoint chunk list **with page-less entries preserved
   as `None`** — so the verifier can reconstruct the gains list exactly. *This artifact predates the change,
   so its 4 fields are deferred rather than exact; a future run verifies them exactly.*
2. ⚠️ **The verifier DEFERS those fields explicitly** (with the mechanism named and the gap bounded at
   5e-3), rather than reporting a false failure — the same false-positive failure mode as the independent
   reviewer's item 8, and treated the same way: stated, not hidden.
3. ⚠️ **Registered here rather than silently tolerated**, because it is the **third** time in this run that
   the product's metric function turned out to mix units (§I95's pool `mrr`, §14's pool coverage, this).

⚠️ **The honest summary of this artifact's verification: 5,848 of 5,852 fields re-derived exactly, 4
deferred as a stated unit difference in a field no conclusion uses.**
