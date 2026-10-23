# P1 — §I61: raise the 64d prefetch limit? (pre-registration)

> **Written 2026-10-23 06:35 PDT, session 12, BEFORE any number of this A/B exists.** §I61's own
> text registers the change as *"the next lever to test"* and states the gate: **the sweep is a
> 40-query screening subsample with no paired CI and no pre-registration, and the change touches the
> production retrieval path — so it needs its own pre-registered A/B (raise-the-limit vs current,
> 133 queries, paired, on the product endpoint) before it ships.** This file fixes what that A/B
> measures and how its numbers may be read, so the result cannot be interpreted after the fact
> (§D1's rule). **A commit containing this file and nothing measured is the point of it.**
>
> Read first: `IMPROVEMENTS.md` §I61 (the lever and the screening numbers), §I60 (128d is dead),
> §I59 (the ranking-side loss this mirrors), §I58 (ceiling normalisation), §I55 (the reranker's
> fallback), §I56 (the DA lane — an existing arm of the same retrieval path), `HANDOFF.md`.

---

## 1. The question

**Does raising the dense funnel's 64d prefetch depth from 1000 to 2000 improve the product
retrieval endpoint on `knowledge_base_v2`?**

The mechanism §I61 measured: the pool loss is the **filtered HNSW search path**, not the MRL width.
At the production limit of 1000 the new index's `dense_64` lane covers **0.804127** of its reachable
pool against **0.932368** for the full-dimension lane — a **0.128241** gap, ~**30×** the old index's
0.004179. Raising the limit recovers it (1500 → 0.904495, 2000 → 0.971526), and at 2000 the
dimension stops mattering (0.971526 vs 0.971966). At limit = every in-window chunk **both lanes are
exactly 1.0000**, so nothing is unreachable — it is only under-returned.

**What §I61 did NOT do** is measure the endpoint the product ships. It measured the *lane's own
membership*. The dense funnel is
`[dense_64(prefetch) → dense_dim(rescore, 500)] → RRF(dense, sparse, colbert) → MMR → cross-encoder`,
so a lane that under-returns can still lose nothing downstream if the full-dim re-score of the 1000
already held everything that mattered. **That is the thing to test.**

## 2. What this A/B IS, and is NOT

| | |
|---|---|
| **IS** | a **paired, single-variable** A/B on the production retrieval path (`store.search_with_das` + the shipped cross-encoder + `evaluate_rag.compute_retrieval_metrics`), 133 answerable text queries, on the new index |
| **IS NOT** | a re-ingest, a model change, a named-vector addition, a Qdrant write, or a graph write. **Config only.** |
| **IS NOT** | a production-number measurement: **HyDE is OFF in both arms** (§4), so the **absolute** numbers are not production numbers and must not be quoted as such. The **delta** is unaffected. |
| **IS NOT** | the §D12 cross-system comparison. Both arms are the SAME index, SAME queries, SAME day, one instrument. |

## 3. The change under test

`src/core/config.py` gains `dense_prefetch_limit: int = 1000` (the shipped value, so the default
path is byte-identical to production), and `store._qdrant_search` reads it in place of the hardcoded
`1000` at the `dense_64` prefetch. The **outer** full-dim re-score cut stays **500** and the inner
stage stays the **64d** lane — both asserted in `tests/test_dense_prefetch_limit.py`, so the A/B is
single-variable by construction and not by inspection.

## 4. Arms (pre-registered)

| arm | `dense_prefetch_limit` | role |
|---|---|---|
| **C** | **1000** | **control** — the shipped value |
| **T** | **2000** | **primary treatment** — where §I61 found the dimension stops mattering |
| **S** | **3489** | **sensitivity** — every in-window chunk of the new index = effectively exact search |
| **N** | 1000 (re-run) | **negative control** — arm C run a second time |

**Everything else is pinned in both/all arms:** the collection (`knowledge_base_v2`), the query file
(`data/eval_queries_v2.json`), the 133 answerable text queries (`gold-*` / `ovw-*`), the query
vector (HyDE OFF, so the raw query vector is shared by every arm), `mmr_enabled` /
`mmr_candidates` 100, `reranker_fetch_k` 100, `reranker_top_k` 20, the reranker itself, the DA lane
(ON), SPLADE/ColBERT as configured, and the metric function.

**Deliberately excluded, and stated so it is a confound not an accident:**
- **HyDE is OFF.** `run_retrieval` generates a hypothetical per factual/overview query with an LLM;
  calling it once per arm would issue the LLM 2–4× per query and could hand the arms *different*
  query vectors, which would destroy the single-variable property. HyDE is arm-invariant when held
  fixed, so the **delta** is unaffected. **The absolute numbers are not production numbers.** (Same
  decision, same reason, as `da_lane_ablation.py` §I56.)
- **The graph lane is NOT included.** It fires on multihop queries only and is a second lever;
  including it would make a multihop delta attributable to either lane. Per-`query_type` numbers are
  reported so its absence is visible.
- **Negatives and visual queries are excluded** — they carry no retrieval labels (the §D12/§I58
  convention; the metric is page-level recall).

## 5. Endpoints (pre-registered)

| # | endpoint | role |
|---|---|---|
| **P1** | paired Δ **Recall@20** on the reranked top-20, **T − C** | **primary** — the product's own cut |
| **P2** | paired Δ **Recall@20 ceiling-normalised** (§I58), T − C | **primary** — raw R@20 compares different denominators when \|relevant\| varies |
| S1 | paired Δ R@100 (`fetch_k`), Hit@20, NDCG@20, MRR, `context_precision` | secondary |
| S2 | per `query_type` (factual / multihop / overview) Δ R@20 | secondary |
| M1 | **mechanism**: `dense_64` lane pool coverage (ceiling-normalised) at 1000 / 2000 / 3489, n=133 | **the causal chain** — §I61's number re-derived at full sample instead of the 40-query subsample |
| G1 | `reranker` fallback per query (§I55) | **guard** |

## 6. Pre-registered reading rule

1. **Ship only on a resolved positive primary.** `T` ships iff the paired 95 % CI on ΔR@20 (P1)
   **excludes 0** and the point estimate is **> 0**. CI = `mean ± 1.96·SD/√n` over the per-query
   paired differences (the repo's convention; `required_n.py` prints no CI).
2. **Unresolved is a result, not a licence.** If the CI includes 0, the entry records
   **measured-and-unresolved** and the change does **not** ship — §I61's screening finding stands as
   a *mechanism* result only.
3. **Negative is recorded, not hidden.** If it resolves negative, the entry says so and the change
   does not ship.
4. **P2 does not substitute for P1.** It is reported beside it; if they disagree, both are reported
   and the disagreement is stated, never averaged.
5. **§I55 fallback queries are excluded from the top-20 headline and named.** The reranker returns
   the pool **unranked** on a fallback, which makes any top-k comparison on that query inert by
   construction. Headline reported both with and without them.
6. **`M1` is a mechanism check, not a second endpoint.** It must move in the §I61 direction (bigger
   limit → more coverage). If it does **not**, the A/B's premise is wrong and the endpoint result is
   reported as unexplained rather than as a finding about the lever.
7. **No causal claim beyond this index.** One corpus, one model, one day. The lever is
   corpus-size-dependent: at 3489 (every in-window chunk) the prefetch is exact search, so on a
   much larger corpus the same raise buys less. State the corpus size with the result.
8. **Absolute numbers are not production numbers** (§4 — HyDE off). Quote the delta.

## 7. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **E1** | the run's resolved settings name `knowledge_base_v2` and a non-blank `QDRANT_HOST` — a run against the local embedded store is unverifiable (§I49 Finding 1), and the harness asserts it before spending |
| **E2** | the artifact records each arm's actual `dense_prefetch_limit`, and the three values are `1000 / 2000 / 3489` |
| **E3** | **133** queries compared in every arm; errored queries are counted and named, never silently dropped |
| **E4** | **the negative control is bit-exact: arm N must equal arm C on every metric of every query.** If it does not, the instrument is noisy, the A/B is **VOID**, and no endpoint is read |
| **E5** | every aggregate re-derives from the artifact's own per-query array (§I57) — nothing is read off the summary block |
| **E6** | §I55 fallbacks counted and named; headline reported with and without |
| **E7** | the cut can move: report each arm's pool size against the top-20 cut. If the pool were ≤ 20 the top-k metric would be inert by construction and must be reported as uninformative rather than as a null |

**E4 is the load-bearing guard.** Without it, a difference between arms could be instrument noise,
and with HyDE off there is no legitimate source of per-query nondeterminism left — so a non-zero N−C
is a bug or a live-drift signal, either of which voids the run.

## 8. Power

`n = 133` is fixed (every answerable text query), so power is reported, not chosen: the entry states
the observed `SD_d` and the `N` required for `δ = 0.05` at that `SD_d`, beside the §I61 screening
expectation. If the observed `SD_d` puts `δ = 0.05` out of reach at n=133, that is stated as the
limit of the result rather than converted into a claim.

## 9. Verifier

One independent, **cross-family** reviewer (the standing rule; the author is DeepSeek-family). It
must: re-derive every aggregate from the per-query array itself, check E2/E3/E4/E5/E6, confirm the
negative control is exactly zero, and look for a query silently excluded from a denominator. The
probe's own numbers are the claim, so the verifier is dispatched **with** the run, not after the
numbers are being quoted (§ standing rule).

## 10. Cost

No LLM calls (HyDE off), no writes, cluster reads only. Four retrieval paths × 133 queries on
`10.0.10.65` over the tunnel. Serialize against other cluster-LLM work — but nothing here touches
the GPU.
