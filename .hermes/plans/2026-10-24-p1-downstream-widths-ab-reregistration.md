# P1 — §I66/§I67: the downstream widths, RE-REGISTERED (E4 disambiguated to metrics-only)

> **Written 2026-10-24, session 13, BEFORE the re-run.** The first A/B
> (`.hermes/plans/2026-10-23-p1-downstream-widths-ab-preregistration.md`) ran and was declared **VOID**
> by its own E4 — see `IMPROVEMENTS.md` §I67. This file re-registers it with **one** change: E4 is
> disambiguated to compare **metrics** (bit-exact), with pool size/pages reported as diagnostics.
> Everything else — the arms, the contrasts, the endpoint, the decision rule — is unchanged, so the
> two runs are directly comparable.
>
> ⚠️ **This is a disambiguation, not a relaxation.** The first pre-registration's E4 text already said
> *"arm N must equal arm C on every **metric** of every query"*. The harness (copied from §I65's) also
> compared `n_pool`/`n_pages` — which are diagnostics, not metrics. **The metrics were bit-exact**
> (1,064 comparisons, 0 metric mismatches, max_abs_diff **0.0**); only a pool size differed, by one
> chunk, on one query. The disambiguation is backed by a **measured** floor (§7), not asserted.
> ⚠️ **The first run's artifact is NOT re-read under this rule** — re-reading an existing artifact under
> a new rule is exactly the post-hoc interpretation §D1 forbids. The re-run produces a fresh artifact.

---

## 1. The question (unchanged)

**Do the two downstream widths — the fusion's output width (W) and the full-dimension re-score cut
(L) — improve the product retrieval endpoint on `knowledge_base_v2`?**

§I66 measured the ceilings by exact brute force and named the fusion output as the binding constraint
(at exact prefetch the fusion's own loss *grows*, 0.143 → 0.222, because feeding it more candidates
does not grow its output). §I65 showed a large ceiling gain in the lane does **not** become recall at
the endpoint. This measures the endpoint.

## 2. What this A/B IS, and is NOT (unchanged)

| | |
|---|---|
| **IS** | a **paired, single-variable** A/B on the production retrieval path (`store.search_with_das` + the shipped cross-encoder + `evaluate_rag.compute_retrieval_metrics`), 133 answerable text queries, on the new index |
| **IS NOT** | a re-ingest, a model change, a named-vector addition, a Qdrant write, or a graph write. **Config only.** |
| **IS NOT** | a production-number measurement: **HyDE is OFF in every arm** and the **prefetch is pinned at 2000** (not the shipped 1000). The **absolute** numbers are not production numbers; the **delta** is unaffected. |
| **IS NOT** | a determinism fix. ⚠️ The product funnel is non-deterministic in a minority of queries (§I67 — Qdrant's server-side RRF fusion). This A/B does **not** fix that; it measures whether the width moves the endpoint *despite* it, with E4' bounding the instrument at the metric level. |

## 3. The change under test (unchanged)

Three settings, each defaulting to the shipped value so the default path is byte-identical
(`tests/test_downstream_widths.py`, 17 tests, mutation-proven):

| setting | default | read site | role |
|---|---|---|---|
| `dense_rescore_limit` | 500 | `store._qdrant_search`, the outer `Prefetch(limit=...)` | **L** — the full-dim re-score cut |
| `mmr_candidates` | 100 | the funnel's final `query_points(limit=...)` via `search(limit=pool)` | **W** — the fusion's output width (the feed) |
| `reranker_fetch_k` | 100 | `store.search_with_das`'s pool truncation + the MMR `top_k` | **W** — the fusion's output width (the clip) |
| `da_fetch_k` | 100 | `store.search_with_das` → `search_da(limit=...)` | the DA lane's depth — **held fixed** |

⚠️ **W is TWO fields and they must move TOGETHER** (§I66): `mmr_candidates` is the funnel's output
width (the RRF fusion's output); `reranker_fetch_k` truncates the pool back to its own value. Raising
either alone does **not** widen the fusion. **W means `mmr_candidates == reranker_fetch_k == W`.**

## 4. Arms (pre-registered — each contrast differs from ITS reference in exactly ONE field)

`W = mmr_candidates = reranker_fetch_k` · `L = dense_rescore_limit` ·
`prefetch = dense_prefetch_limit` · `da = da_fetch_k` · `reranker_top_k = 20` (**pinned in every arm**).

| arm | `mmr_candidates` | `reranker_fetch_k` | `dense_rescore_limit` | prefetch | `da_fetch_k` | read against | role |
|---|---|---|---|---|---|---|---|
| **C** | **100** | **100** | **500** | 2000 | 100 | — | **control** — shipped W and L |
| **W1** | **300** | **300** | 500 | 2000 | 100 | **C** | **width treatment 1 — PRIMARY** |
| **W2** | **500** | **500** | 500 | 2000 | 100 | C | width sensitivity / ceiling arm; **also the CUT CONTROL** |
| **L1** | 500 | 500 | **1000** | 2000 | 100 | **W2** | **cut treatment 1 — PRIMARY** |
| **L2** | 500 | 500 | **2000** | 2000 | 100 | W2 | cut sensitivity |
| **N** | 100 | 100 | 500 | 2000 | 100 | — | **NEGATIVE CONTROL** — arm C re-run verbatim |

**What each arm is, in words:**
- **C** — the control: W and L at their shipped values (100, 500). prefetch (2000) and da (100) are held constant across every arm and are *not* the shipped prefetch (1000).
- **W1** — the fusion output widened to 300; nothing else moves. The width's primary treatment.
- **W2** — the fusion output widened to 500. The width's sensitivity/ceiling arm, and the control for the cut.
- **L1** — the re-score cut raised to 1000 with the fusion held wide (W=500). The cut's primary treatment.
- **L2** — the re-score cut raised to 2000 with W=500. The cut's sensitivity arm.
- **N** — C re-run verbatim. Not a treatment; it exists only for E4'.

⚠️ **Why the cut arms run at W=500 and are read against W2, not against C.** At W=100 the fusion emits
only 100 candidates, so raising L merely reshuffles candidates far below the cut and the endpoint is
**inert by construction** — the smoke test measured Δ exactly **0.0000**, W/L/T **0/0/3 identical** at
W=100. L's extra candidates can only reach the output if the fusion is wide enough to admit them, so the
cut is tested on the widest fusion (W2), which is therefore its control.

**Everything else is pinned in every arm:** the collection (`knowledge_base_v2`), the query file
(`data/eval_queries_v2.json`), the 133 answerable text queries (`gold-*` / `ovw-*`), the query vector
(HyDE OFF, so the raw query vector is shared by every arm), `mmr_enabled` / `mmr_lambda` 0.7,
`reranker_top_k` 20, the reranker itself, the DA lane (ON, `da_fetch_k` 100), SPLADE/ColBERT as
configured, `dense_dim_low` 64, and the metric function.

**Deliberately excluded (confounds, stated not accidental):** HyDE off; the graph lane (multihop only,
a second lever — per-`query_type` numbers are reported so its absence is visible); negatives and visual
queries (no retrieval labels); **prefetch pinned at 2000 in every arm** (§I66: at N=1000 the lane caps
L's benefit at 0.8151).

## 5. Contrasts (what moves, and what each one tests)

| contrast | field that moves | from → to | what it tests |
|---|---|---|---|
| **W1 − C** | **W** (both `mmr_candidates` and `reranker_fetch_k`) | **100 → 300** | does widening the fusion output to 300 move the endpoint? — **PRIMARY (width)** |
| W2 − C | W | 100 → 500 | the ceiling arm for the width — sensitivity |
| **L1 − W2** | **`dense_rescore_limit`** | **500 → 1000** | does raising the cut help once the fusion admits the extra candidates? — **PRIMARY (cut)** |
| L2 − W2 | `dense_rescore_limit` | 500 → 2000 | the ceiling arm for the cut — sensitivity |
| N − C | nothing | — | E4′ — must be bit-exact on the metrics |

⚠️ **The two primaries sit on different references** (C for the width, W2 for the cut). That is
deliberate and is why the cut arms run at W=500.

## 6. Endpoint (pre-registered, unchanged)

Per query `q`, from `evaluate_rag.compute_retrieval_metrics` on the product path (`hits` = the pool from
`store.search_with_das`; `reranked` = the cross-encoder's top-20):

```
R@20(q)    = |distinct labelled pages in the reranked top-20| / |relevant_pages(q)|
ceiling(q) = min(20, |relevant_pages(q)|) / |relevant_pages(q)|            (§I58)
R@20cn(q)  = R@20(q) / ceiling(q)
Δ(q)       = R@20cn(treatment, q) − R@20cn(reference, q)
mean       = mean of Δ over the queries where both are non-null
SD         = sample SD (ddof = 1)                                          (the repo's convention)
CI95       = mean ± 1.96·SD/√n
resolved   = CI95 excludes 0
n          = 133 (fixed — every answerable text query)
```

| # | endpoint | role |
|---|---|---|
| **P1** | paired Δ **R@20cn**, **W1 − C** | **primary (width)** |
| **P2** | paired Δ **R@20cn**, **L1 − W2** | **primary (cut)** |
| S1 | paired Δ R@20cn, **W2 − C** and **L2 − W2** | sensitivity (ceiling arms) |
| S2 | paired Δ raw R@20, Hit@20, NDCG@20, MRR, `context_precision` | secondary |
| S3 | per `query_type` (factual / multihop / overview) Δ R@20cn | secondary |
| S4 | paired Δ R@20cn, **L1 − C** — the "candidate vs shipped" contrast (**two variables**, labelled as such) | secondary, decision-relevant |
| M1 | each arm's **pool size** vs the top-20 cut | diagnostic (E7) |
| G1 | `reranker` fallback count, **per arm** (§I55) | guard |
| G2 | the DA lane's hit count, per arm (asserted `da_fetch_k`=100) | guard |

**`R@100` is reported as POOL WIDTH, not as a result.** It is `recall_at_reranker_fetch_k` — the pool's
own width — so it moves with W by construction and cannot be read as evidence for or against the width.

## 7. Decision rule (pre-registered, per lever — they are independent)

1. **The WIDTH ships** iff `W1−C` resolves positive: CI95 **excludes 0** AND the point estimate is **> 0**.
2. **The CUT ships** iff `L1−W2` resolves positive (same test).
3. **Unresolved is a result, not a licence.** CI includes 0 ⇒ recorded **measured-and-unresolved**, does not ship.
4. **Negative is recorded, not hidden.** CI resolves negative ⇒ recorded, does not ship.
5. **Sensitivity arms cannot promote a null.** If W1 is unresolved, W2−C cannot make the width ship; it
   is reported as the ceiling arm only. Likewise L2−W2 for the cut.
6. **§I55 fallback queries are excluded from the top-20 headline and named**; headline reported both
   with and without them.
7. **Power is reported, not chosen**: state the observed `SD_d` and the `n` required for `δ = 0.05` at it.
8. ⚠️ **DEPENDENCY CLAUSE (new).** The cut is measured **at W=500**. A positive `L1−W2` is therefore only
   shippable **if W=500 also ships**; otherwise the combination (W=500, L=1000) must be tested against C
   in a follow-up before anything ships. `S4` (`L1−C`) is pre-registered as the decision-relevant
   comparison for that case, and is labelled **two-variable** — it is reported, never used to rescue a
   single-variable null.
9. ⚠️ **DIAGNOSTICS DO NOT VOID (new).** `n_pool` / `n_pages` / fallbacks / `da_hits` are reported per
   arm and per query. A diagnostic difference is a **finding about the instrument** (it is the §I67
   non-determinism), not a reason to void the run. Only a **metric** difference voids it (E4′).

## 8. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **E1** | the run's resolved settings name `knowledge_base_v2` and a non-blank `QDRANT_HOST` — a run against the local embedded store is unverifiable (§I49 Finding 1); the harness asserts it before spending |
| **E2** | the artifact records each arm's actual `mmr_candidates` / `reranker_fetch_k` / `dense_rescore_limit` / `da_fetch_k`; the control arm resolves to the shipped `100 / 100 / 500 / 100` |
| **E3** | **133** queries compared in every arm; errored queries are counted and named, never silently dropped |
| **E4′** | **the negative control is bit-exact ON THE METRICS: `\|N − C\| ≤ 0` for every metric of every query.** Any metric mismatch ⇒ the A/B is **VOID** and no endpoint is read. Diagnostics (`n_pool`/`n_pages`) are compared and **reported**, and do **not** void. |
| **E5** | every aggregate re-derives from the artifact's own per-query array (§I57) — nothing is read off the summary block |
| **E6** | §I55 fallbacks counted and named **per arm**; headline reported with and without |
| **E7** | the cut can move: report each arm's pool size against the top-20 cut; the width arms' pools must grow with W; the cut arms must show the pool's **page set** moving |
| **E8** | `da_fetch_k` is **100 in every arm** and the DA lane's hit count is recorded — a width effect must not be a DA effect |
| **E9** | the **inner** 64d prefetch depth (`dense_prefetch_limit`) is 2000 in every arm and does not vary with W or L |

**E4′ is the load-bearing guard, exactly as E4 was.** ⚠️ **The measured floor that justifies it:**
30 queries × 4 repeats of the C config → **R@20cn spread max 0.000000**, pool spread 0; and the first
run's **1,064 comparisons → 0 metric mismatches, max_abs_diff 0.0**. The only difference the first run
found was `n_pool`/`n_pages` on `ovw-041` (95 vs 94) — a **diagnostic**, and the §I67 non-determinism.

## 9. Verifier

One independent, **cross-family** reviewer (the standing rule; the author is DeepSeek-family), dispatched
**with** the run. It must: re-derive every aggregate from the per-query array itself; check
E2/E3/E4′/E5/E6/E7/E8/E9; confirm the negative control is exactly zero **on the metrics**; report the
diagnostic differences separately (§I67's non-determinism); and look for a query silently excluded from
a denominator. The harness's `--recheck` mode is the mechanical half (E5 + E4′); the reviewer is the
second half. ⚠️ The reviewer is told **explicitly** that `n_pool` differences are expected and are not
defects, so it does not re-litigate E4′.

## 10. Cost

No LLM calls (HyDE off), no writes, cluster reads only. Six arm-configurations × 133 queries on
`10.0.10.65` over the tunnel. The first run took **~65 min** (with one transient ~24-min cluster stall);
expect **~55–70 min**.
