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
| **G1** | **arm C reproduces T0's `ce` row EXACTLY** — coverage 0.4553, R@20 0.4442, P@20 0.2398, F1 0.1911, nDCG 0.4946, MAP 0.2789, MRR 0.6668, Hit 0.9173. Tolerance **1e-6**. ⚠️ **`R@100` is EXCLUDED from this comparison** — see §11 |
| **G2** | ⚠️ **THE STRONG ONE — arm N reproduces T0's `fusion` row EXACTLY** — coverage 0.6845, R@20 0.4491, R@100 0.6706, P@20 0.2447, F1 0.1968, nDCG 0.5506, MAP 0.3421, MRR 0.7687, Hit 0.9323. Tolerance **1e-6**. With no CE the top-20 *is* the pool's top-20, and the pool is **page-deduped**, so the two conventions coincide — the reproduction should be exact |
| **G3** | **133 scored / 0 errors** in every arm |
| **G4** | **determinism: arm C run TWICE is bit-exact** on every metric of every query (§I68 landed) |
| **G5** | ⚠️ **arm Q's instrumentation TOOK EFFECT** — Q differs from C on **at least one** query. A silent no-op would make Q a duplicate of C and the run's central question unanswerable |
| **G6** | **the pools are IDENTICAL across C, N and Q** — same lane set, same `fetch_k`; the treatment is the **ordering only**. Asserted per query |
| **G7** | the **reachable-pages set is identical to T0's** (888 pages, set equality) — the denominator did not move |

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
