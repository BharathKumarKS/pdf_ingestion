# P1 Step 10 — pre-registration (written BEFORE any number exists)

**Date:** 2026-10-18 · branch `feat/p0-9-gold-dataset-v2` · author: agent, on Bharath's instruction
**Executes:** `.hermes/plans/2026-10-18-p1-step10-remeasure-plan.md` §0–§4; register entries
`IMPROVEMENTS.md` §D9 / §D10 / §D11 / §D13 (and §D4 as a precondition).

This file is written **before** either arm of the ablation runs, so the decision cannot be
reverse-fitted to the result. Do not edit it after the numbers exist; record the outcome in a
separate "Outcome" section (the 2026-10-14 and 3c pre-registrations set that precedent).

The prior pre-registration (`.hermes/plans/2026-10-14-p0-9-4-preregistration.md`) is the ancestor of
this one. §D13 deferred the reranker call to **this** run, on the **rebuilt** index, with the
decision rule carried over unchanged. This file re-states that rule in full rather than referring to
it from memory, because the whole point of §D13 is that the rule must not be re-derived after the
fact.

---

## 1. What is being decided

The one question §D13 left open: **does the cross-encoder re-ranker earn its place, on the rebuilt
index?** On the old index (`knowledge_base`, 5,135 points) its isolated contribution was
**−0.0101, 95% CI [−0.0299, +0.0097] → unresolved at n=133**, and the pre-registered δ=0.05 would
have needed only n=43 while the *observed* 0.011 needs **n≈934**. §D13's decision was to keep the
reranker enabled, **not** extend the query set, and settle it here — after the re-ingest removed the
chunk-boundary fuzz (§D4) and the label noise that the effect currently sits inside.

Secondary (reported, not a decision endpoint): whether the **factual-lane** loss the old index
resolved (**−0.0469, CI [−0.0787, −0.0152]**) survives the rebuilt index. §D13 names this as the
hypothesis to re-check. See §6.

## 2. Query scope and arms (fixed here, before the run)

| Item | Value |
|---|---|
| Gold set | `data/eval_queries_v2.json` (200 queries + 1 `_note` header entry) |
| Text-lane queries | **133** = 53 factual + 40 multihop + 40 overview (`calibrated` ∧ `relevant_pages`, visual excluded) |
| Visual queries | 33 — **excluded** from this funnel (`--include-visual` off); the funnel has no ColPali lane |
| Negatives | 34 — not scored by the funnel |
| Index | `knowledge_base_v2`, 3,796 points, `dense_1024` (Qwen3-Embedding-0.6B, 1024d + 64d MRL) |
| Qdrant | `QDRANT_HOST=10.0.10.65`, `QDRANT_COLLECTION=knowledge_base_v2` |
| Merge | `--merge rrf3` (dense + sparse + ColBERT fused) |
| HyDE | **on**, cache `logs/p0-9/v2_hyde.json` **reused** — the two arms must differ only in the reranker |
| Harness | `scripts/funnel_boundary_recall.py` (rerank ON / `--no-reranker`), `scripts/required_n.py` |
| Artifacts | `logs/p1/step10/v2_rerank.json`, `logs/p1/step10/v2_norerank.json` |
| Judge (step 4 only) | cross-family: `--judge-backend openai --judge-api-base http://10.0.10.70:8000 --judge-model Qwen/Qwen3-VL-8B-Instruct` |

**Why 133 and not the plan's 135.** The plan (§0, §2) and the older pre-registration write the text
lane as "135 = 55 + 40 + 40". The assembled file holds **53** factual, not 55: `gold-001`/`gold-002`
were dropped pre-run by §D6 (preface labels at page 3, outside the retrievable window [30, 936]), as
the 2026-10-14 pre-registration's Outcome already records ("135 pre-registered → 133 delivered").
**133 is the operative n.** No query is added or removed here; the plan's 135 is a stale count.

**The arms differ only in the reranker.** Same collection, same query file, same HyDE cache, same
merge, same content-page bounds (`MIN_CONTENT_PAGE=30`, `MAX_CONTENT_PAGE=936`). Anything else
varying would be a confound, not an effect.

## 3. The metric — stated precisely, because the plan's phrasing is ambiguous

The plan §0 calls the metric "funnel `B5b` R@20". **That cannot be the endpoint.** `B5b` is the
retriever's *own* top-20 before reranking: it is computed identically in both arms and is therefore
**identical by construction** — it measures the reranker's *input*, not its *effect*. It is the
control, not the endpoint.

The endpoint is **R@20 on each arm's final top-20** (`top20_pages`):

- **rerank arm** → the cross-encoder's top-20 (`B6_rerank_20`);
- **no-rerank arm** → the retriever's own top-20 (`B6` collapses to `B5b` when `--no-reranker`).

So the paired difference is **`B6_rerank_20`(ON) − `B6`(OFF)**, i.e. exactly what
`required_n.py v2_rerank.json v2_norerank.json` computes from each file's `top20_pages` — the same
construction the 2026-10-14 run used to get −0.0101. This is the primary, pre-registered endpoint.

R@20 is page-level YES-only (D8): `|top20 ∩ relevant_pages| / |relevant_pages|`.

**Ceiling normalisation (§D9) is reported alongside every R@20, and the ceiling is the §D9 one:**
`mean(min(20,|rel|)/|rel|)` — measured from the current labels as **0.8016** (text lane), factual
**0.9557**, multihop **1.0000**, overview **0.3992**. These reproduce §D9's recorded values exactly.

> ⚠️ **Do not use the funnel's printed "ceiling".** `funnel_boundary_recall.py` prints
> *"Precision@20 ceiling … mean min(|rel|,20)/20"* = **0.4861** for this lane — that is the **P@20**
> ceiling, a different quantity. Dividing R@20 by 0.4861 would inflate it by ~1.65×. The R@20
> ceiling is 0.8016.

## 4. Decision rule (agreed in advance — carried over from §D13, unchanged)

> **The re-ranker stays if and only if `rerank` beats `no-rerank` on R@20 by more than the 95 %
> confidence interval on the paired difference. Otherwise it comes out.**

- Paired difference `d_q = R@20_rerank(q) − R@20_norerank(q)` over the 133 shared queries.
- CI = `mean(d) ± 1.96 · SD(d) / √n`, two-sided 95 %.
- **The rule is met only if the CI excludes 0 *and* `mean(d) > 0`.** A CI entirely below 0 means the
  reranker *hurts* — also a decision, and the arm comes out.
- σ_d is recomputed **for this comparison on this index** (D1) — the old index's 0.1163 is a
  reference point, not an input.

**Note on `required_n.py`'s output (a correction to the plan §2 verifier).** The plan states the
verifier must confirm that "`required_n.py` prints the paired delta **with its 95 % CI**". It does
**not** — `scripts/required_n.py` prints *shared queries, mean difference, SD of the per-query
difference, correlation,* and *required N at δ*. The CI is **not** in its output. The CI will
therefore be computed from the same per-query differences by the fixed formula above (which is what
produced the recorded [−0.0299, +0.0097] on the old index), and both the script's output and the CI
computation will be pasted into the Outcome. This is a pre-registered computation, not a post-hoc
choice.

## 5. The honest power statement — the rule may again be UNREACHABLE, not merely unmet

At **n = 133** the CI half-width is `1.96 · SD_d / √133`. On the old index `SD_d = 0.1163` gave
**±0.0198** (observed CI width 0.0396). The plan §0 estimates "on the order of ±0.04"; the measured
figure on the old index was **±0.0198**, i.e. the plan's estimate is conservative by ~2×. The
rebuilt index may move `SD_d` either way — the whole premise of §D13 is that removing the
chunk-boundary fuzz and label noise *lowers* the floor, which would *narrow* the CI.

Against a CI of roughly ±0.02, the old index's effect (0.011) is **unresolvable by construction** —
not "not yet significant", but arithmetically below the resolution of the design. Reaching 0.05
needs n≈43; reaching 0.011 needs **n≈934**.

**Pre-registered meaning of an unresolved result:** if the CI straddles 0, the verdict is
**"unresolved at n=133"** and the decision is **keep the reranker enabled, do not extend the query
set** — §D13's answer, re-affirmed. An unresolved verdict is a **result, not a failure to get one**.
§5 of the 2026-10-14 pre-registration forbids extending the query set until an arm wins, and the
"extend in blocks of 30" sequential rule reaches only δ≈0.026 at n=163 — it can never resolve 0.011.
**No new rule is invented mid-run.** If the CI is wide *and* the point estimate has moved to a
magnitude ≥ 0.03, that is reported as a directional (not significant) shift, and the decision stays
"keep enabled".

## 6. What would falsify the §D13 hypothesis carried into this run

§D13 carries one resolved finding forward as a **hypothesis to re-check, not an assumption**: on the
old index the reranker's loss was concentrated in the **factual** lane, where it *was* resolved
(−0.0469, CI [−0.0787, −0.0152], and it survived a Bonferroni correction for 3 subgroups). On the
rebuilt index:

- **Refuted if** the factual subgroup's mean Δ is ≈ 0 or positive and its CI excludes a loss — then
  the old −0.0469 was an artifact of the pre-re-ingest chunking/labels, and §D13's carried
  hypothesis is dead.
- **Supported if** the factual CI again lies below 0 with a comparable magnitude — then the effect is
  real and not a chunking artifact, which is a materially different claim from "unresolved".
- **Inconclusive if** the factual CI straddles 0 — reported as such.

Per-type subgroups (factual 53 / multihop 40 / overview 40) are **exploratory**, as in every prior
run: reported with their CIs and a note that no multiplicity control is pre-registered (the
2026-10-14 run applied Bonferroni post hoc and flagged it as such). **They are not the endpoint.**

## 7. Validity gates — checked BEFORE any score is read (plan §2 verifier)

1. **Preflight passes** (`scripts/preflight.py`, exit 0) — §D11: a cluster outage once made all 167
   non-visual queries fail and `evaluate_rag.py` exited rc=0 having written an empty report. The
   preflight is the gate; a non-zero exit **stops the run** before any arm.
2. **Both arm JSONs exist with the same query count** (133) and the same `n_queries` in their
   `config` block.
3. **§D10 stability check:** `B5b_retriever_top20` must be **identical per query across the two
   arms**. RRF is not bit-reproducible at pool level, so `B4_rrf_union_100` / `B5_colbert_100` may
   differ on a handful of queries (7/133 and 2/133 on the old index) — that is tolerated. **If
   `B5b` moved, the A/B is void and is re-run, not interpreted.**
4. **Same collection, same HyDE cache, same query file** recorded in each arm's `config` block
   (`collection`, `hyde_cache`, `n_queries`, `dense_vector_name`).
5. **Every R@20 is reported raw *and* ÷ 0.8016** (§D9 ceiling), per lane.

## 8. Known caveats carried into this run

- **§D4** — the durable page-numbering fix landed with Steps 3+6/7/8 (parent-aware provenance; offset
  collapses to 0 on 99.95 % of children). Step 10 §3 re-derives the labels against the rebuilt path
  **before** the numbers are trusted; this pre-registration is written before that re-derivation, so
  the ceiling figures in §3 are those of the *current* labels and may be recomputed.
- **§D6** — gold labels can fall outside the retrievable window [30, 936]; the 4 partly-outside
  multihop queries remain, capping their recall below 1.0.
- **§D10** — pool-level non-reproducibility (above).
- **§B4b/§B4d** — visual lane only (33 usable), not measured by this funnel.
- **Step 4** (`evaluate_rag.py`: abstention, generation metrics) is the expensive cluster run
  (~30–60 min of judge calls) and is reported against §D12's recorded baseline (text R@20 0.465;
  factual 0.564 / multihop 0.619 / overview 0.178), ceiling-normalised.

---

## Outcome (post-hoc — recorded AFTER the run, not a target)

_Not yet written. Do not add numbers here until both arms have run._
