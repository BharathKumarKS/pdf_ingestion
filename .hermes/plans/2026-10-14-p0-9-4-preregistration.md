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
