# P0-9 Session 4 — pre-registration (written before the numbers are seen)

**Date:** 2026-10-14 · `feat/p0-9-gold-dataset-v2` · author: agent, on Bharath's instruction
**Gold set:** `data/eval_queries_v2.json` — 168 answerable + 34 negatives = 202 (16.8%).
Assembled by `scripts/build_gold_v2.py` (commit `e69c347`).

This file is written **before** the v2 eval runs, so the decision cannot be reverse-fitted
to the result. Do not edit it after the numbers exist; record the outcome in a separate
"Outcome" section (the 3c pre-registration set that precedent).

---

## 1. What is being decided

The single open P0 question: **does the cross-encoder re-ranker earn its place?**
v1 said it *hurt* (0.651 → 0.569, −0.082) but at n=23 that is unresolvable
(SE ≈ 0.05). v2 makes it resolvable.

Secondary: **abstention** — can the system decline on a negative? v1 had zero negatives,
so this was unmeasurable.

## 2. Query scope (decided here, before the run)

| Lane | Queries | Harness |
|---|---|---|
| Text (factual + multihop + overview) | **135** = 55 + 40 + 40 | `funnel_boundary_recall.py` |
| Visual | **33** | `evaluate_rag.py` → `run_visual_retrieval` (ColPali MaxSim) |
| Negatives | **34** | `evaluate_rag.py` → abstention metric |

**Decision:** the text-lane funnel **excludes the 33 visual queries** (default; `--include-visual`
overrides). Rationale: the funnel measures dense/sparse/ColBERT/rerank — it has **no ColPali
lane**, so a visual query cannot be scored by it, and mixing them in would dilute both the
text-lane numbers and the reranker delta. The visual lane is measured separately by
`evaluate_rag.py`. The 135 figure matches HANDOFF's "135 answerable".

## 3. The comparison (rerank ON vs OFF)

Same gold set, same 3-way RRF merge, same HyDE (pinned to one cached hypothetical per query
so the A/B compares lanes, not two LLM samples):

```bash
uv run python scripts/funnel_boundary_recall.py --queries data/eval_queries_v2.json \
    --hyde --hyde-cache /tmp/v2_hyde.json --merge rrf3 --json /tmp/v2_rerank.json
uv run python scripts/funnel_boundary_recall.py --queries data/eval_queries_v2.json \
    --hyde --hyde-cache /tmp/v2_hyde.json --merge rrf3 --no-reranker --json /tmp/v2_norerank.json
uv run python scripts/required_n.py /tmp/v2_rerank.json /tmp/v2_norerank.json --delta 0.05
```

Primary metric: **R@20** on the reranked top-20 (YES-only gold labels — D8).

## 4. Decision rule (agreed in advance)

> **The re-ranker stays if and only if `rerank` beats `no-rerank` on R@20 by more than the
> 95% confidence interval on the paired difference. Otherwise it comes out.**
> Abstention accuracy on the negatives is reported separately and **must exceed the
> majority-class baseline** (better than always-answering, i.e. > 0.0 abstention, since a
> negative is never correctly answered by retrieving).

Recompute σ_d **per comparison** (D1) — do not reuse the v1 number (0.2315).

## 5. Stopping rule (D1 — sequential design)

Start at 135. If the CI on the paired difference straddles 0 at 135, extend in blocks of 30
(re-scan the added queries the same way) and recompute σ_d each time. **Do not** stop at the
first CI that excludes 0 without the pre-registered stopping rule; and do not keep adding
queries until one arm wins.

## 6. What would falsify the current plan

- If the reranker's CI still straddles 0 at 135, the honest report is "unresolved at n=135",
  not a coin-flip call.
- If abstention is ≤ the majority baseline, the negatives are not being handled — a
  guardrail gap to register, not a metric to quietly drop.
- If the text-lane R@20 moves by less than the label-noise floor (§D4, ~1 page), no
  reranker claim is readable until the numbering is normalised.

## 7. Known label caveats carried into this run

- §D4 — the text lane mixes DB and PDF page numbering (0/−1 on ~45% of pages). Not fixed;
  it adds ~a page of label noise and is a floor on how finely a delta can be read.
- §B4b — the visual index holds 3 vectors/page; `run_visual_retrieval` dedupes by page.
- §B4d — the visual denominator is 33, not 40.

---

## Outcome (post-hoc, 2026-10-14 — recorded after the run, not a target)

Run: 2026-10-14 18:03–18:06, `logs/p0-9/run_session4_v2.sh`, **steps 1–2 only**.
`QDRANT_HOST=10.0.10.65` (cluster index), shared HyDE cache `logs/p0-9/v2_hyde.json`.

| pre-registered | delivered | note |
|---|---|---|
| text lane **135** | **133** | `gold-001`/`gold-002` dropped pre-run by §D6 (front-matter labels outside the window) |
| rerank vs no-rerank on R@20, 95% CI on the paired difference | **−0.0107**, CI **[−0.0304, +0.0091]** | **straddles 0 → UNRESOLVED at n=133**, per §4/§6 |
| `required_n.py` — the powered decision | **did not run** | the script's `--queries` default is `data/eval_queries.json` (**v1**, ids `vec-NNN`) → *"only 0 shared queries"*, exit 1. Re-run with `--queries data/eval_queries_v2.json`: n=133, SD_d **0.1164**, SE 0.0101, required N **43** at δ=0.05 (**934** at the observed 0.011). §D7 |
| abstention **> majority baseline** | **not measured** | step 4 (`evaluate_rag.py`) left no artifact — no generation metrics, no abstention block |
| visual lane (33) | **not measured** | same — `run_visual_retrieval` never ran |

Funnel (page-level recall; a boundary "has" a page if any of its chunks is in the pool):

| boundary | rerank | no-rerank | reading |
|---|---|---|---|
| B1_dense64_1000 | 0.7924 | 0.7924 | precedes the reranker — identical, as it must be |
| B2_dense768_500 | 0.7415 | 0.7415 | " |
| B3_sparse_250 | 0.6743 | 0.6743 | " |
| B4_rrf_union_100 | 0.5943 | 0.5942 | " (see §D10 — not bit-reproducible) |
| B5_colbert_100 | 0.6007 | 0.6007 | " |
| **B5b_retriever_top20** | **0.4495** | **0.4495** | the 100→20 cut costs **0.15** of recall |
| **B6_rerank_20** | **0.4389** | **0.4495** | the reranker's isolated contribution: **−0.0107** |

Headline metrics on the reranked top-20: R@20 0.4389 vs 0.4495 · P@20 0.2049 vs 0.1932 ·
Hit@20 0.9549 vs 0.9699 · R-prec 0.3473 vs 0.3752. 30 queries worse / 37 better / 66
identical — churn, not a uniform loss.

**Exploratory (NOT a pre-registered endpoint — subgroup, no multiplicity control beyond the
note below).** The effect is concentrated in the factual lane, where it *is* resolved:

| subgroup | n | mean Δ R@20 | 95% CI | verdict |
|---|---|---|---|---|
| factual | 53 | **−0.0469** | [−0.0787, −0.0152] | **resolved — the reranker hurts** |
| multihop | 40 | +0.0091 | [−0.0351, +0.0534] | unresolved |
| overview | 40 | +0.0176 | [−0.0016, +0.0368] | unresolved |
| all | 133 | −0.0107 | [−0.0304, +0.0091] | unresolved |

The factual result survives a Bonferroni correction for 3 subgroups (z=2.394 → CI
[−0.0857, −0.0081], still excluding 0). Treat it as a hypothesis for the next run, not as
the session's verdict.

**Two measurement defects found while reading the result (registered, §D8/§D9):** the funnel
does not apply `max_content_page`, so it does not mirror deployed retrieval and the bias is
arm-asymmetric (2.15% of the rerank arm's top-20 slots are back-matter pages the app never
serves, vs 0.95% in the no-rerank arm); and R@20 is capped by the label denominator, which is
why v2's 0.4495 is not comparable to v1's recorded 0.636.

### What this session did *not* settle

1. **The reranker decision.** §4's rule is not met and cannot be met at a feasible n — see the
   plan's §5 stopping rule and §D9. Extending to ~934 queries is the only way to resolve the
   observed 0.011; extending in blocks of 30 (the pre-registered rule) reaches δ≈0.026 at n=163.
2. **Abstention.** The second half of the pre-registered decision is still unmeasured.
3. **The visual lane.** Same.
4. **§D4 (DB↔PDF page numbering) was never normalised** — it was "next action 5" *before* this
   run and is still open, so every number above carries ~a page of label noise.

---

## Session 4b re-run — post-fix (2026-10-14)

Run: `logs/p0-9/session4b_rerun.log`, steps 1–3 only, **the same 133 text queries** and the same
HyDE cache (93 hypotheticals = factual 53 + overview 40, fully cached → **no LLM calls**). The
harness fixes landed first (commit `769e60d`): §D7 (`--queries` now required) and §D8
(`max_content_page` applied in `build_filter` + `post()`).

| boundary | rerank | no-rerank | (Session 4) | Δ post-fix |
|---|---|---|---|---|
| B1_dense64_1000 | 0.7999 | 0.7999 | (0.7924) | — |
| B2_dense768_500 | 0.7453 | 0.7453 | (0.7415) | — |
| B3_sparse_250 | 0.6755 | 0.6755 | (0.6743) | — |
| B4_rrf_union_100 | 0.5948 | 0.5948 | (0.5943) | — |
| B5_colbert_100 | 0.6009 | 0.6008 | (0.6007) | — |
| **B5b_retriever_top20** | **0.4492** | **0.4492** | (0.4495) | — |
| **B6_rerank_20** | **0.4391** | **0.4492** | (0.4389 / 0.4495) | **−0.0101** |

**Verdict: still UNRESOLVED at n=133.** Δ −0.0101, 95% CI **[−0.0299, +0.0097]** — straddles 0;
§4's rule is not met. 29 worse / 37 better / 67 identical. `required_n.py` (now with the right
file): n=133, SD_d **0.1163**, SE 0.0101, required N **43** at δ=0.05 (934 at the observed 0.0101).

Headline on the reranked top-20: rerank P@20 0.205 / R@20 0.439 / Hit@20 0.955 / R-prec 0.348;
no-rerank 0.192 / 0.449 / 0.970 / 0.375.

**The §D8 fix did what it should, and did not change the decision.** Removing back-matter pages
from the pools raised every pre-reranker boundary (B1 0.7924→0.7999 … B5b 0.4495→0.4492) and
moved the headline delta by **0.0006** (−0.0107 → −0.0101) — inside the noise. The reranker stays
un-earned on the pre-registered endpoint.

Exploratory per-type (subgroup, no multiplicity control beyond the note): **factual −0.0469**,
CI [−0.0787, −0.0152] → resolved (the reranker hurts factual); multihop +0.0091 → unresolved;
**overview +0.0195, CI [+0.0007, +0.0384]** → now *just* excludes 0 (was [−0.0016, +0.0368]), i.e.
the fix flipped the overview subgroup to a marginal reranker win. It does **not** survive a
Bonferroni correction for 3 subgroups, so treat it as a hypothesis, not a result.

Still unmeasured after 4b: **abstention** (34 negatives) and the **visual lane** (33 queries) —
both live in step 4 (`evaluate_rag.py`), the only expensive cluster run, not yet executed.
