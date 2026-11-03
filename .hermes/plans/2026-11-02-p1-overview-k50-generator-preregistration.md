# P1 — THE OVERVIEW k=50 GENERATOR TEST — pre-registration

> **Written 2026-11-02, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing measured
> is in it. Read first: `IMPROVEMENTS.md` **§I105** and **§I106** (the per-type k sweep — wider k buys
> recall/coverage, not ranked quality) and **§I108** (the generator eval, which closed the "generator
> unmeasured" gap but ran at the product's **k=20**).

---

## 1. The question

**§I105 and §I106 both end on the same sentence: the ONLY reading under which "a wider k for overview"
pays is the GENERATOR stage — "still unmeasured."** That is no longer true: the generator is now
measured (§I108), but it ran at **k=20**. So:

> **Does raising the endpoint cut from k=20 to k=50 improve the OVERVIEW generator's FAITHFULNESS?**

Baseline (k=20, `v3_judged_full`): overview faithfulness **0.5097** (n=40) — the lowest of the three
types. Overview is also the type where wider k buys the most recall (R@20 0.188 → R@47 0.370, §I105).
This is the first test of whether that extra recall buys a **better-grounded answer**, or only more
context.

⚠️ **This is a MEASUREMENT, not a retrieval improvement.** §I105/§I106 already showed the ranked quality
does not rise; this asks only about the **answer**.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **run** against `knowledge_base_v3` (nomic-768, pooled), **40 overview queries** (`ovw-*`), each through the product's own `evaluate_rag.run_retrieval` + `synthesize` + `compute_retrieval_metrics`. |
| **IS** | **one arm, k=50**: `RERANKER_TOP_K=50` (the CE's top-50 pages are what `synthesize` receives). `reranker_fetch_k=100`, `mmr_candidates=100` unchanged — the pool is not widened, only the cut. |
| **IS** | the **same generator** (`openai/gpt-oss-20b`) and the **same cross-family judge** (`Qwen/Qwen3-VL-8B-Instruct`) as the baseline. HyDE ON; the per-type rerank policy (raw query for factual, hypothetical for overview) as shipped. |
| **IS NOT** | a collection write, a re-ingest, an embedder change, or a `src/` change. **Read-only.** |
| **IS NOT** | a re-run of the full 200-query eval — only the 40 overview queries, because only they are under test. |

---

## 3. The quantities

```
arm            k=50  x  40 overview queries
baseline       v3_judged_full (k=20), the SAME 40 queries
PRIMARY        paired Δ faithfulness          (k50 − k20), 95 % CI, per query
secondary      paired Δ answer_relevance, Δ citation_accuracy
retrieval      R@20, R@50, nDCG@20, nDCG@50, context_precision (k=50), pool size
mechanism      chunks sent to the LLM (k), context length
```

A delta is **RESOLVED** iff its paired 95 % CI excludes 0.

---

## 4. Predictions (fixed BEFORE the numbers exist)

1. **Anchor (not a finding):** k=50's **R@50 > R@20** for overview — recall is monotone in k (§I105).
   If R does not rise, the arm did not receive a wider cut and the run is void.
2. **The test:** overview **faithfulness** — three admissible outcomes, all reported:
   * **RESOLVED POSITIVE** ⇒ wider k pays on the answer side; the context-budget reading is **closed
     positive** and "wider k for overview" becomes a ship candidate (a per-type policy).
   * **UNRESOLVED** ⇒ the extra context neither helps nor hurts measurably.
   * **RESOLVED NEGATIVE** ⇒ the extra context **dilutes** grounding (the classic long-context harm).
3. **answer_relevance** ≈ unchanged (the answer should still answer; only grounding is under test).

**Falsification clause.** If faithfulness resolves **positive**, then a per-type `k` policy (wider for
overview) is a live lever and should be re-registered as a product change. If it resolves **negative**
or is unresolved, **"wider k for overview" is closed** — it is a context-budget knob with no measured
answer-side benefit, and §I105/§I106's verdict is complete.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population **40** overview queries, all `ovw-*`, all with `relevant_pages`. |
| **G2** | **zero errors** in the run. |
| **G3** | **zero reranker fallbacks** (§I55 — a fallback returns the pool UNRANKED). |
| **G4** | reachable pages == **888** (T0's recorded value). |
| **G5** | the resolved config asserts `reranker_top_k == 50`, `qdrant_collection == knowledge_base_v3`, `dense_model == nomic-ai/nomic-embed-text-v1.5`, `dense_dim == 768`. |
| **G6** | the baseline is the SAME 40 query ids (paired join is non-empty on all 40). |
| **G7** | faithfulness computed on **all 40** (no silent judge drop). |

---

## 6. Bounds

* One corpus, one document (Feynman Vol. 1), one funnel. n=40. The overview label sets are broad (mean
  73.8 pages).
* ⚠️ **The judge is a single cross-family model on a single run** — no independent verifier is applied to
  a judge SCORE (§I108's own caveat). The paired comparison controls for the judge being the same model.
* ⚠️ **Confound, stated:** k=50 changes the context the judge sees as well as the answer, so a rise is
  "more context helped grounding", not proof that k=50 is right for production.
* The cluster is a single point of failure; a mid-run outage voids the affected queries (re-run).
* **Read-only: no collection write, no re-ingest, no `src/` change.**

---

## 7. Registration and what would falsify this

On completion: an `IMPROVEMENTS.md` entry, a `HANDOFF.md` block, the artifact
`data/eval_results/overview_k50_*.json`/`.md`, the run log, and a paired comparison vs the k=20 baseline.
**Read-only at run time.**
