# P1 — the PER-TYPE RERANK-QUERY POLICY, before/after (pre-registration)

> **Written 2026-10-29, BEFORE any number of this run exists.** Per **D6.1** it is **committed ALONE**,
> and nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 25), `IMPROVEMENTS.md` **§I97** (T4 — the attribution this policy
> implements), **§I96** (the silent ColBERT lane dropout), **§I95** (the pool-vs-endpoint `mrr` trap),
> `logs/p1/step10/nomic_gap_report.md` §4 and §9, `evaluate_rag.py:185-258`,
> `src/frontend/streamlit_app.py:534-577`, and `logs/p1/step10/t4_endpoint.json`.

---

## 1. The question

**T4 attributed the pool → top-20 loss: the cross-encoder is a net harm at the endpoint, and on factual
queries the cause is the HyDE HYPOTHETICAL being used as the cross-encoder's query** (`evaluate_rag.py:206`
sets `rerank_query = hyp`). Per type, T4 measured (n = 133):

| type | n | N−C nDCG | **Q−C nDCG** | reading |
|---|---|---|---|---|
| **factual** | 53 | +0.1361 R | **+0.1397 R** | the hypothetical is essentially the whole cause; **Q ≈ N** |
| multihop | 40 | −0.0311 (ns) | **+0.0000 [0,0]** | HyDE is not used → Q ≡ C **by construction** |
| overview | 40 | +0.0371 (ns) | −0.0420 (ns) | the hypothetical is the *better* query here |

**⇒ The registered change is a PER-TYPE policy:** the **raw query** for **factual**, the **HyDE
hypothetical** for **overview**, either for **multihop** (HyDE is not used there, so the two are the same
string).

⚠️ **This is a before/after for ONE LINE of the live pipeline.** T4 explicitly did not change `src/`, because
a one-line change to the pipeline off an attribution run is what D6.1 exists to prevent.

## 2. The measurement — why this is a COMPOSITION, not a fresh 52-minute run

**T4 already ran both arms this policy selects between**, on one index, one pool per query:

* **arm C** = the CE fed the **product** query (`hyp` for factual+overview, raw for multihop);
* **arm Q** = the CE fed the **raw** query for every type.

The policy **is** `Q` on factual and `C` on overview and multihop. Arms C and Q share the **same pool per
query** (T4's G6/G6b: pool size *and* content identical) and differ **only** in the CE's query text — so the
policy's per-query metrics are **exactly** `Q_metrics` for factual and `C_metrics` otherwise, both of which
are present on all **133** rows of `t4_endpoint.json`.

⇒ **The policy's effect is computable by re-derivation over T4's artifact: read-only, no cluster, minutes.**
⚠️ **The live confirmation is a SEPARATE, later gate** (the code change + one product-endpoint run) and is
**not** part of the registered measurement — see §8.

## 3. Arms

| arm | what it is | how |
|---|---|---|
| **C** | the product — CE fed `hyp` for factual+overview, raw for multihop | T4's `C_metrics`, verbatim |
| **P_gold** | the policy gated on the **GOLD** `query_type` | `Q_metrics` for factual, `C_metrics` otherwise |
| **P_router** | the policy gated on the **INTENT ROUTER's** classification | the router's class per query selects the arm |

⚠️ **`P_gold` is the UPPER BOUND; `P_router` is the PRODUCT-REALISTIC number, and the gap between them is
itself a finding.** The eval gates on the **gold** label (`evaluate_rag.py:761`, `query.get("query_type")`);
the **product** gates on the router (`streamlit_app.py:538`). §I82 measured the router's agreement with gold
at **0.5714**, so a shipped policy applies the fix to the wrong queries a substantial fraction of the time.
**Both arms are registered**, and `P_router` is what a ship would actually realise.

## 4. The unit, and the ceilings

**Page-level, the product's convention** — *pages of the top-k chunks*, page-deduped — **with both ceilings
beside every number** (§I93): `P-ceil@k = min(n, k)/k` and `R-ceil@k = min(k, n)/n`, both **properties of
the gold labels**, identical in every arm.

**Reported per arm:** coverage of a query's reachable labelled pages, `R@20`, `P@20` + `P-ceil`, `F1@20`,
**`nDCG@20`**, **`MAP`**, **`MRR@20` (the ENDPOINT MRR — `mrr_at_20`, ⚠️ NOT the pool `mrr`, §I95)**, `Hit@20`
— **overall and per query type**.

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **the composition is wired correctly, exactly:** `P_gold`'s **factual** rows equal T4's **arm Q** factual rows, and its **overview + multihop** rows equal T4's **arm C** rows — field by field, tolerance **1e-4** (the metrics are `round(..., 4)`) |
| **G2** | **internal consistency:** the **multihop** policy ≡ `C` **exactly, 40/40** — the same free check T4 passed, because HyDE is not used for multihop |
| **G3** | **the treatment is the ORDERING only:** per query, `pool_size`, pool-page content and `R@20` / `Hit@20` are **identical** between the policy arm and `C`. ⚠️ **If any moves, the run is VOID** — a pool difference is a confound, not an effect |
| **G4** | **`P_router` uses the ROUTER's output, not gold:** its per-query arm selection reproduces the router's own predicted class for that query (a mismatch on any query fails) |
| **G5** | **the re-derivation models the SHIPPED code:** for every query, the CE query text the policy would send is the string the one-line change would produce (raw for factual, `hyp` for overview) — a static check against the source |
| **G6** | **133 queries, 0 errors**, and every per-query row carries both `C_metrics` and `Q_metrics` |
| **G7** | **the router arm is not degenerate:** the router emits more than one class over the 133 queries, and its factual/multihop/overview counts are recorded |

## 6. Predictions (registered BEFORE the numbers, so they can be falsified)

1. ⚠️ **P_gold > C on `nDCG@20`, `MAP` and `MRR@20`, overall and on factual** — the policy recovers most of
   T4's Q−C effect on the type it targets.
2. **On factual, P_gold ≈ Q** (T4's Q−C factual +0.1397) — the policy's factual gain is the same measured
   effect, not a new one.
3. ⚠️ **P_gold's OVERALL `nDCG@20` ≥ Q's overall (+0.0430)** — because the policy **excludes** the overview
   regression (Q−C overview −0.0420) that arm Q incurred. **A P_gold overall below Q's would falsify the
   policy's premise.**
4. **`P_router` ≤ `P_gold` on the factual and overall effect**, by the router's misclassification rate — the
   product-realistic number is the attenuated one. ⚠️ **The SIZE is unregistered** (the router's per-type
   accuracy is not yet measured); only the direction is.
5. **Zero recall cost:** `R@20` and `Hit@20` are unchanged between the policy and C — the change is the CE's
   input, not the pool.
6. **On overview, the policy changes nothing** (`P_gold` ≡ `C` there by construction) — a guard, not a
   prediction, but stated so a movement would be read as a wiring error.

⚠️ **A prediction that fails is the finding.** These are registered so the run can falsify them.

## 7. Reading rule

* **n = 133**; the resolution floor is **≈ 0.020** overall, **≈ 0.04 per type** (n = 40). ⚠️ **Only the
  FACTUAL per-type effect (n = 53) is expected to resolve** — the overall n = 133 effect is ~0.04–0.06 and
  may or may not. The entry states the observed `SD_d` and the `n` required for `δ = 0.05`.
* **Statistic, pinned:** the paired difference per query, and its 95 % CI as **`mean ± 1.96·SD/√n`** over the
  per-query differences — computed by the harness, because the product's metric function does not emit a CI.
* ⚠️ **`unresolved` means KEEP THE STATUS QUO** — it is **not** a prompt to extend the sample. Extending n is
  forbidden until an arm wins.
* **Quote every recall against its ceiling** (§I93) and **every precision with `P-ceil` beside it**.
* ⚠️ **Quote `mrr_at_20` (endpoint), never the bare `mrr` (pool, §I95)** — the two differ by ~0.10 and the
  policy moves only the endpoint.
* **No causal claim beyond this one index and corpus.** One document, one day, one funnel, one CE model
  (`BAAI/bge-reranker-v2-m3`).

## 8. The live confirmation — a SEPARATE gate, not part of this measurement

⚠️ **The re-derivation proves the EFFECT; it does not prove the CODE emits it.** If §6's predictions hold,
the change is:
* `evaluate_rag.py:206` — `rerank_query = hyp` becomes raw for `query_type == "factual"`;
* `streamlit_app.py:556` — the same, gated on the router's `intent == "factual"` (the gate itself is at
  `streamlit_app.py:538`).
Then **one product-endpoint run** confirms the live pipeline reproduces the composition.
**Registered as its own gate with its own guards:** (L1) the override fired on every factual call; (L2) the
live policy arm reproduces `P_gold` bit-exact on the endpoint fields; (L3) lane health per query (the
ColBERT counter, §I96 — landed this session); (L4) the multihop arm still ≡ C.

## 9. Verifier — independent, stdlib only

`logs/p1/step10/policy_ab_verifier.py`, reading **only the written JSON**, re-deriving from the **raw
per-query arrays**: G1, G2 (both anchors, field by field), G3 (pool identity per query), G4 (router
selection), G6; the per-arm aggregates; the paired P_gold−C and P_router−C deltas with CIs; and every ratio
quoted. ⚠️ **Mutation-proved BEFORE the run** (`policy_ab_mutation_log.txt`): each mutation must turn
**exactly** its own check red, and **every check must be reddened by at least one mutation** (no inert check).

⚠️ An independent cross-family reviewer (`openai/gpt-oss-20b`, read-only) on a **compact extract**, never the
full artifact.

## 10. Cost

**Read-only.** No writes, no re-ingest, no `src/` change, **no cluster calls** for the re-derivation (the
`P_router` arm needs one local router pass over 133 queries: 133 nomic query-embeds). Minutes, not the 52
minutes a fresh 4-arm run cost T4.

## 11. Preconditions

1. `logs/p1/step10/t4_endpoint.json` resolves and passes **14/14** guards (sha256 `3db7c697a5bb0fec…`).
2. The intent classifier at `data/models/intent_classifier.pkl` loads under the 768/nomic config (§I82).
3. ⚠️ **This file is committed ALONE, before the run (D6.1).**

## 12. Stated — what this run does NOT do

* **It does not re-run retrieval.** It composes two arms T4 already measured; §8 is the live confirmation.
* **It does not change the cross-encoder or its model.**
* **It does not decide the SHIP.** A confirmed policy is a product-path finding that licenses §8, nothing
  more.
* **It does not touch the pool, the lanes or the labels.**
