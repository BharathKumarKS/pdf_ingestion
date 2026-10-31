# P1 — THE FUSION'S ORDER: does the pool's ORDER cost the endpoint, per type, and where? (pre-registration)

> ⚠️ **This file is committed ALONE, before the run (D6.1).** No arm has run when it is written.

## 1. The question

`IMPROVEMENTS.md` §I99 decomposes the endpoint's top-20 loss per type and finds that the loss is
**not** the pool's coverage and **not** the cross-encoder:

| type | R_ceil@20 | pool-oracle | pool order (N) | product (C) | waste_pool | waste_order | waste_ce |
|---|---|---|---|---|---|---|---|
| factual | 0.9557 | 0.8052 | 0.5830 | 0.5574 | 0.1505 | **0.2222** | 0.0256 |
| overview | 0.3992 | 0.3755 | 0.2103 | 0.1882 | 0.0236 | **0.1652** | 0.0221 |
| multihop | 1.0000 | 0.6466 | 0.5106 | 0.5500 | 0.3534 | 0.1360 | −0.0394 |
| all 133 | 0.8016 | 0.6283 | 0.4491 | 0.4442 | 0.1734 | **0.1791** | 0.0050 |

`waste_order` — the loss from the pool's own **order**, given the pool already holds the gold — is
the largest lever overall (0.1791) and the largest for overview (0.1652, against a `waste_pool` of
only 0.0236).

**The registered question:** *which mechanism produces `waste_order`, and does changing it move the
endpoint's top-20, per type?*

⚠️ **The registered question is NOT "does this improve things".** A null is a real, recordable
outcome and closes the lever. What has **never** been run is any contrast of the pool's own ORDER:
§I92 tested the **cap** and **MMR** on *coverage*; §I67 tested the **width** on *coverage*; T4 tested
the **cross-encoder's query text**; §I98 tested **lane placement**. Every one of those is a coverage
knob or a CE knob.

## 2. Arms — one index (`knowledge_base_v3`, nomic-768), HyDE ON and frozen, read-only

The pool's order is a **TWO-LEVEL** RRF (`store.search_fused` §docstring): level 1 fuses
dense + sparse + ColBERT inside `_qdrant_search` (unweighted, `rrf_k=1`); level 2 fuses that single
list with da/graph/raptor in `search_fused` (weighted, `rrf_k=1`). Then dedup → MMR → truncate.

| arm | what it changes | level | code change | isolates |
|---|---|---|---|---|
| **O0** | nothing — the product's order | — | none | the reference; anchors on T4's arm C |
| **O1** | `mmr_enabled=False` | post | **none** (config) | MMR's **ORDER** effect — §I92 measured only its coverage effect |
| **O2** | `colbert_enabled=False` | 1 | **none** (config) | the §I89 dilution hypothesis, first step |
| **O3** | `colbert_enabled=False`, `splade_enabled=False` | 1 | **none** (config) | the dilution limit case: dense-only order |
| **O4** | level-1 `_rrf_merge` gains `weights=[1.0, 0.5, 0.5]` (dense, sparse, colbert) | 1 | **~1 line** in `_qdrant_search` | dilution WITHOUT removing candidates |

⚠️ **O4's code change is named here and must land BEFORE the run, and must be behaviour-preserving
when `weights is None`** — pinned by a unit test asserting `_qdrant_search` with default weights is
bit-identical to today. That test is part of this pre-registration's deliverables.

⚠️ **O2/O3 change the pool's COMPOSITION, not only its order** — they remove a lane's candidates.
They are included because the §I89 hypothesis is precisely that those lanes *dilute*, and a
candidate-removal is the honest limit case. Their results are read as composition+order, and §4 G3
says so. **O1 and O4 are the order-only arms.**

⚠️ **ONE mechanism per arm.** O0 is the only arm with all lanes and MMR on.

## 3. The unit, and the ceilings

Page-level, the product's convention — *pages of the top-k chunks*, page-deduped — with **both**
ceilings (§I93): `P-ceil@k = min(n,k)/k`, `R-ceil@k = min(k,n)/n`.

**Reported per arm, overall and per type:** coverage of a query's reachable labelled pages, `R@20`,
`R@100`, `P@20`+`P-ceil`, `F1@20`, `nDCG@20`, `MAP`, **`MRR@20` (endpoint — `mrr_at_20`, NOT the pool
`mrr`, §I95)**, `Hit@20`.

⚠️ **Also reported per arm: the pool's candidate SET and page SET**, so the composition/order split
is visible rather than asserted (§11e's precedent).

## 4. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **lane health per query** — the ColBERT, DA, RAPTOR and graph counters (§I96) show **no dropout survived into any accepted call**, in every arm |
| **G2** | **O0 reproduces T4's arm C** per type on the endpoint metrics (tolerance 1e-4) — the anchor that makes the comparison meaningful |
| **G3** | ⚠️ **membership: ASSERTED for O1 only, where MMR did not fire; REPORTED for O2/O3/O4.** For O1, on every query where `len(deduped) <= fetch_k`, the pool's page SET must be **identical** to O0's — that is what makes O1 single-variable. Where MMR did fire, O1's membership is reported, not asserted |
| **G4** | **no reranker fallback** on any query in any arm (§I55) — otherwise that arm's top-k is unranked |
| **G5** | **the arm's mechanism actually took effect**: O1 records `mmr_fired` count; O2/O3 record the contributing lane set per query; O4 records the weights used. An arm whose mechanism never engaged is a copy of O0 |
| **G6** | **133 queries, 0 errors** in every arm |
| **G7** | **O4's code change is inert by default**: `_qdrant_search` with `weights=None` reproduces the pre-change result bit-identically (a separate unit test, run before the arm) |

## 5. Predictions (registered BEFORE the numbers, so they can be falsified)

1. **O1 (MMR off) is a NULL on every metric.** §I92 measured MMR's coverage effect as
   `+0.003178`, unresolved; MMR fires only when `len(deduped) > fetch_k`, which is a minority of
   queries at `mmr_candidates=100`. **If O1 moves a ranking metric, that is the finding** — it would
   mean MMR's reordering, not its membership, is a cost.
2. **O3 (dense-only) IMPROVES overview's `R@20` and `nDCG@20`.** The §I89 mechanism: sparse and
   ColBERT are model-independent, so RRF dilutes the dense lane's advantage. This is the arm the
   pre-registration expects to move.
3. **O2 sits between O0 and O3**, because it removes one of the two diluting lanes.
4. **O4 ≥ O0 on overview** if the dilution is real — it is the same hypothesis as O3 without the
   candidate removal, so a gap between O4 and O3 attributes the effect to *removal* vs *weighting*.
5. **No arm closes `waste_order` for overview (0.1652).** The expected best case is a few points of
   `R@20`; a lever that closes it entirely is not expected and would be surprising.

⚠️ **A prediction that fails is the finding.**

## 6. Reading rule

* **n = 133**; floor ≈ **0.020** overall, ≈ **0.04 per type**. Only the per-type and the larger
  overall effects are likely to resolve; `SD_d` and the `n` required for `δ = 0.05` are reported.
* **Statistic, pinned:** paired difference per query; CI = **`mean ± 1.96·SD/√n`** over the
  per-query differences.
* ⚠️ **`unresolved` means KEEP THE STATUS QUO** — not a prompt to extend the sample.
* **Quote every recall against its ceiling**; **every precision with `P-ceil`**; **`mrr_at_20`,
  never the bare `mrr`**.
* ⚠️ **Do not quote `mrr_at_20` for a page-less lane** (§I98's instrument finding) — not applicable
  here (no arm adds a page-less lane) but stated so the constraint is not silently dropped.
* **No causal claim beyond this index, corpus, CE model.**

## 7. Verifier — independent, stdlib only

`logs/p1/step10/fusion_order_verifier.py`, reading **only the written JSON**, re-deriving from the
raw per-query arrays: G1–G7, the per-arm aggregates, every paired delta with its CI, and every ratio
quoted. ⚠️ **Mutation-proved BEFORE the run**: each mutation reddens **exactly** its own check, and
**every check is reddened by at least one mutation** (no inert check).

## 8. Cost

**Read-only.** No writes to any collection, no re-ingest, no embedder change. **5 arms × 133 queries**
at the measured ~2.5 s/query ≈ **28 min**, plus the verifier, the mutation proof, and O4's
inertness test. ⚠️ Serialize against other cluster work.

## 9. Preconditions

1. `knowledge_base_v3` is live at nomic-768 with the RAPTOR nodes carried (verified: 3,869 points).
2. The HyDE cache resolves under the registered digest; a miss RAISES.
3. `_qdrant_search` accepts `weights` and is **inert by default** (G7's test passes).
4. The lane counters exist and the ColBERT counter is live (§I96).
5. ⚠️ **This file is committed ALONE, before the run (D6.1).**

## 10. Stated — what this run does NOT do

* **It does not measure the generator stage** — retrieval only.
* **It does not change the embedder, the index, the labels, or the cross-encoder.**
* **It does not re-open the fusion width (§I67), the cap or MMR-as-coverage (§I92), the lanes
  (§I98), or the rerank-query policy (shipped, §I97).**
* **It does not test score-based fusion** (replacing rank-based RRF with a normalised score sum).
  That needs cross-lane score normalisation across incomparable scores (cosine / SPLADE / maxsim)
  and is a separate design, named here as the next candidate if O4 moves.
* **It does not claim `waste_order` is fully recoverable** — the oracle in §I99 is an upper bound.
