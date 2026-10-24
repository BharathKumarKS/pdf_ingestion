# P1 — §I66: the downstream widths (the fusion output, the re-score cut)? (pre-registration)

> **Written 2026-10-23, session 13, BEFORE any number of this A/B exists.** §I66 located the loss and
> named the lever: *"the binding constraint is the 100-slot fusion output"* — not the 64d prefetch
> (§I61/§I65, a NULL) and not the re-score cut. §I66 measured the ceilings by exact brute force but
> **never measured the endpoint the product ships**; and the fusion-output width's own ceiling is
> **"not yet measured"**. This file fixes what the A/B measures and how its numbers may be read, so the
> result cannot be interpreted after the fact (§D1's rule). **A commit containing this file and nothing
> measured is the point of it.**
>
> Read first: `IMPROVEMENTS.md` §I66 (the decomposition and the ceilings), §I65 (the prefetch A/B — a
> NULL, and the cautionary case), §I63 (the cross-embedder instrument), §I58 (ceiling normalisation),
> §I55 (the reranker's fallback), §I56 (the DA lane — an existing arm of the same fusion stage),
> `HANDOFF.md`, and the plan `2026-10-23-p1-downstream-widths-and-embedder-screen-plan.md` §1.

---

## 1. The question

**Do the two hardcoded downstream widths — the full-dimension re-score cut (L) and the fusion's output
width (W) — improve the product retrieval endpoint on `knowledge_base_v2`?**

The mechanism §I66 measured (denominator = a query's reachable labelled pages):

| stage | production (N=1000) | exact prefetch (N=3489) |
|---|---|---|
| 64d lane | 0.8151 | 1.0000 |
| → after the full-dim re-score cut (L=500) | 0.7478 | 0.8286 |
| → after the fusion (RRF + dedup + MMR to 100) | **0.6048** | **0.6071** |
| → after the cross-encoder to top-20 | 0.4318 | 0.4348 |

**The fusion is the largest single loss after the 64d lane, and it does not shrink when the prefetch
grows** (0.143 → 0.222 at exact prefetch) — because the fusion's *output* width does not grow. That is
why §I65 was a null. The cut is still a large **ceiling** lever (L=1000 +0.0980, L=2000 +0.1486, L=all
+0.1714, all resolved) — but a raised ceiling is not recall (§I65 is the proof), so both are
hypotheses to be tested at the endpoint.

## 2. What this A/B IS, and is NOT

| | |
|---|---|
| **IS** | a **paired, single-variable** A/B on the production retrieval path (`store.search_with_das` + the shipped cross-encoder + `evaluate_rag.compute_retrieval_metrics`), 133 answerable text queries, on the new index |
| **IS NOT** | a re-ingest, a model change, a named-vector addition, a Qdrant write, or a graph write. **Config only.** |
| **IS NOT** | a production-number measurement: **HyDE is OFF in every arm** (§4) and the **prefetch is pinned at 2000** (not the shipped 1000), so the **absolute** numbers are not production numbers and must not be quoted as such. The **delta** is unaffected. |
| **IS NOT** | the §D12 cross-system comparison. All arms are the SAME index, SAME queries, SAME day, one instrument. |

## 3. The change under test

Three settings, each defaulting to the shipped value so the default path is byte-identical to
production (pinned by `tests/test_downstream_widths.py`, 17 tests, mutation-proven):

| setting | default | read site | role |
|---|---|---|---|
| `dense_rescore_limit` (**NEW**) | 500 | `store._qdrant_search`, the outer `Prefetch(limit=...)` (`store.py:455`) | **L** — the full-dim re-score cut |
| `mmr_candidates` | 100 | `store._qdrant_search`'s final `query_points(limit=...)` via `search(limit=pool)` (`store.py:384/513`) | **W** — the fusion's output width (the feed) |
| `reranker_fetch_k` | 100 | `store.search_with_das`'s pool truncation + MMR `top_k` (`store.py:758/761`) | **W** — the fusion's output width (the clip) |
| `da_fetch_k` (**NEW**) | 100 | `store.search_with_das` → `search_da(limit=...)` (`store.py:732`) | the DA lane's depth — **held fixed** |

⚠️ **W is TWO fields, and they must move together.** `mmr_candidates` sets the funnel's output width
(the RRF fusion's output); `reranker_fetch_k` truncates the pool back to its own value. Raising
`mmr_candidates` alone does **not** widen the fusion; raising `reranker_fetch_k` alone cannot exceed
what the feed offered. **W means `mmr_candidates == reranker_fetch_k == W` in this A/B.** (This is the
correction to the plan's earlier framing, which named `fetch_k` alone; the discriminating tests are
`test_pool_is_clipped_to_fetch_k_when_only_the_feed_is_widened`,
`test_pool_is_clipped_when_only_the_truncation_is_widened`, `test_both_width_knobs_together_widen_the_pool`.)

⚠️ **`da_fetch_k` exists to keep the DA lane out of the width test.** It used to be `fetch_k`, so any
width sweep moved the DA lane's depth as well — and §I56 measured the DA lane *in this exact fusion
stage* (−0.0262 on top-20 R@20). `da_fetch_k` is pinned at 100 in **every** arm.

## 4. Arms (pre-registered)

**Each contrast differs from ITS OWN reference in exactly ONE field.**

| arm | W (`mmr_candidates`=`reranker_fetch_k`) | L (`dense_rescore_limit`) | prefetch | `da_fetch_k` | read against | role |
|---|---|---|---|---|---|---|
| **C** | **100** | **500** | 2000 | 100 | — | **control** — shipped W and L |
| **W1** | **300** | 500 | 2000 | 100 | **C** | **width treatment 1 — PRIMARY** |
| **W2** | **500** | 500 | 2000 | 100 | C | width sensitivity — the ceiling arm; **also the CUT CONTROL** |
| **L1** | **500** | **1000** | 2000 | 100 | **W2** | **cut treatment 1 — PRIMARY** |
| **L2** | **500** | **2000** | 2000 | 100 | W2 | cut sensitivity |
| **N** | 100 | 500 | 2000 | 100 | — | **NEGATIVE CONTROL** — arm C re-run; MUST be bit-exact (E4) |

⚠️ **Why the cut arms run at W=500 and are read against W2, not against C.** At W=100 the fusion emits
only 100 candidates, so raising L merely reshuffles candidates far below the cut and the endpoint is
**inert by construction** — the smoke test measured Δ exactly **0.0000**, W/L/T **0/0/3 identical** at
W=100. L's extra candidates can only reach the output if the fusion is wide enough to admit them, so the
cut is tested on the widest fusion (W2), which is therefore its control. Every contrast remains
single-variable: **W1/W2 move W only; L1/L2 move L only.**

**Everything else is pinned in every arm:** the collection (`knowledge_base_v2`), the query file
(`data/eval_queries_v2.json`), the 133 answerable text queries (`gold-*` / `ovw-*`), the query vector
(HyDE OFF, so the raw query vector is shared by every arm), `mmr_enabled` / `mmr_lambda` 0.7,
`reranker_top_k` 20, the reranker itself, the DA lane (ON, `da_fetch_k` 100), SPLADE/ColBERT as
configured, `dense_dim_low` 64, and the metric function.

**Why the prefetch is pinned at 2000 in every arm:** §I66 shows N=1000 caps L's benefit at 0.8151, so
at the shipped prefetch the lane would be the constraint and the cut's ceiling could not express.
Holding it at 2000 (where §I61 found the dimension stops mattering) makes the lane not the cap.
**Consequence, stated so it is a confound not an accident:** the absolute numbers are not the shipped
config's. The delta is what is read.

**Deliberately excluded, and stated so it is a confound not an accident:**
- **HyDE is OFF.** `run_retrieval` generates a hypothetical per factual/overview query with an LLM;
  calling it once per arm would issue the LLM 2–4× per query and could hand the arms *different* query
  vectors, destroying the single-variable property. HyDE is arm-invariant when held fixed, so the
  **delta** is unaffected. **The absolute numbers are not production numbers.** (Same decision, same
  reason, as `da_lane_ablation.py` §I56 and §I65.)
- **The graph lane is NOT included** — it fires on multihop only and is a second lever. Per-`query_type`
  numbers are reported so its absence is visible.
- **Negatives and visual queries are excluded** — they carry no retrieval labels (the §D12/§I58
  convention; the metric is page-level recall).

## 5. Endpoints (pre-registered)

| # | endpoint | role |
|---|---|---|
| **P1** | paired Δ **R@20 ceiling-normalised** (§I58), **W1 − C** | **primary** |
| **P2** | paired Δ **R@20 ceiling-normalised**, **L1 − W2** | **primary** |
| S1 | paired Δ R@20 ceiling-normalised, **W2 − C** and **L2 − W2** | sensitivity |
| S2 | paired Δ raw R@20, Hit@20, NDCG@20, MRR, `context_precision` (W1−C, L1−C) | secondary |
| S3 | per `query_type` (factual / multihop / overview) Δ R@20 ceiling-normalised | secondary |
| M1 | each arm's **pool size** vs the top-20 cut | **the cut-can-move check** (E7) |
| G1 | `reranker` fallback count, **per arm** (§I55) | **guard** |
| G2 | the DA lane's hit count, per arm (asserted `da_fetch_k`=100) | **guard** |

**`R@100` is reported as POOL WIDTH, not as a result.** It is `recall_at_reranker_fetch_k` — the pool's
own width — so it moves with W by construction and cannot be read as evidence for or against the
width. It is carried in the artifact for the record only.

## 6. Pre-registered reading rule

1. **Ship only on a resolved positive primary.** A width ships iff the paired 95 % CI on ΔR@20
   ceiling-normalised (P1) **excludes 0** and the point estimate is **> 0**; likewise the cut on P2.
   CI = `mean ± 1.96·SD/√n` over the per-query paired differences (the repo's convention;
   `required_n.py` prints no CI).
2. **Unresolved is a result, not a licence.** If the CI includes 0, the entry records
   **measured-and-unresolved** and the change does **not** ship.
3. **Negative is recorded, not hidden.** If it resolves negative, the entry says so and it does not ship.
4. **P1 and P2 do not substitute for each other.** Both are reported; if they disagree, both are
   reported and the disagreement is stated, never averaged.
5. **§I55 fallback queries are excluded from the top-20 headline and named — per arm.** The reranker
   returns the pool **unranked** on a fallback, which makes any top-k comparison on that query inert by
   construction. Headline reported both with and without them. **If W2's fallback count materially
   exceeds C's, W2 is reported as UNINFORMATIVE (guard 3), not as a null.**
6. **Sensitivity arms cannot promote a null.** If W1 is unresolved, W2's result cannot make the width
   ship; it is reported as the ceiling arm only.
7. **M1 is a mechanism check, not an endpoint.** Each arm's pool must exceed the top-20 cut (else the
   metric is inert, §G1's defect) — and, for the width arms, the pool must actually grow with W.
8. **No causal claim beyond this index.** One corpus, one model, one day.
9. **Absolute numbers are not production numbers** (§2/§4 — HyDE off, prefetch pinned). Quote the delta.

## 7. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **E1** | the run's resolved settings name `knowledge_base_v2` and a non-blank `QDRANT_HOST` — a run against the local embedded store is unverifiable (§I49 Finding 1), and the harness asserts it before spending |
| **E2** | the artifact records each arm's actual `mmr_candidates` / `reranker_fetch_k` / `dense_rescore_limit` / `da_fetch_k`, and the control arm resolves to the shipped `100 / 100 / 500 / 100` |
| **E3** | **133** queries compared in every arm; errored queries are counted and named, never silently dropped |
| **E4** | **the negative control is bit-exact: arm N must equal arm C on every metric of every query.** If it does not, the instrument is noisy, the A/B is **VOID**, and no endpoint is read |
| **E5** | every aggregate re-derives from the artifact's own per-query array (§I57) — nothing is read off the summary block |
| **E6** | §I55 fallbacks counted and named **per arm**; headline reported with and without |
| **E7** | the cut can move: report each arm's pool size against the top-20 cut. If the pool were ≤ 20 the top-k metric would be inert by construction and must be reported as uninformative rather than as a null. **AND**: the width arms' pools must grow with W, and the cut arms must show the pool's **page set** moving (L changes composition, not size — at W=100 the cut moved nothing, which is why it is tested at W=500) |
| **E8** | `da_fetch_k` is **100 in every arm** and the DA lane's hit count is recorded — a width effect must not be a DA effect |
| **E9** | the **inner** 64d prefetch depth (`dense_prefetch_limit`) is 2000 in every arm and does not vary with W or L (single-variable by construction) |

**E4 is the load-bearing guard.** Without it, a difference between arms could be instrument noise, and
with HyDE off there is no legitimate source of per-query nondeterminism left — so a non-zero N−C is a
bug or a live-drift signal, either of which voids the run.

## 8. Power

`n = 133` is fixed (every answerable text query), so power is reported, not chosen: the entry states
the observed `SD_d` and the `N` required for `δ = 0.05` at that `SD_d`. §I65 measured `SD_d 0.020013`
(required n for δ=0.05 = 1) — if this run is similar, the effect is far below δ and that is stated as
the limit of the result rather than converted into a claim.

## 9. Verifier

One independent, **cross-family** reviewer (the standing rule; the author is DeepSeek-family). It
must: re-derive every aggregate from the per-query array itself, check E2/E3/E4/E5/E6/E7/E8/E9, confirm
the negative control is exactly zero, and look for a query silently excluded from a denominator. The
harness's own `--recheck` mode is the mechanical half (E5 + E4); the reviewer is the second half. The
probe's own numbers are the claim, so the verifier is dispatched **with** the run, not after the
numbers are being quoted (§ standing rule).

## 10. Cost

No LLM calls (HyDE off), no writes, cluster reads only. Six arm-configurations × 133 queries on
`10.0.10.65` over the tunnel. §I65's four-arm run took **31 min**; this should be **~45 min**.
Serialize against other cluster-LLM work — but nothing here touches the GPU.
