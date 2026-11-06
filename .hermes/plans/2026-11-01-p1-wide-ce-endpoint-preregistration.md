# P1 — THE WIDE-CE ENDPOINT RUN: the cross-encoder's FULL ranking over a WIDE pool (pre-registration)

> **Written 2026-11-01, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing measured is
> in it.
>
> Read first: `IMPROVEMENTS.md` **§I105** (the per-type k sweep; the CE arm capped at k=47), **§I92**
> (the cap 100→500: pool coverage +0.1835 → endpoint +0.003), **§I102** (the cut as nDCG@k; the
> construction artifact), and `scripts/evaluate_rag.py:405-448` (the nDCG/IDCG convention).

---

## 1. The question

§I105 answered "does a wider cut help, per type?" but the CE's ranking was available only to **k=50**
(T4 kept ≤50). The owner asked: **widen the pool cap and sweep k higher.** The POOL arm is read-only
(`wide_pool_k_sweep.py`, cap 500, from `fusion_attribution.json`). **This run records the missing half:
the CROSS-ENCODER's full ordered page list over the wide pool**, so the per-type sweep can reach k ≈ 250.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only run** against `knowledge_base_v3` (`QDRANT_HOST=10.0.10.65`, 3,869 points, nomic-768), ONE arm, 133 gold queries, HyDE ON and frozen. |
| **IS** | the product's own `run_retrieval`, with **only config knobs moved**: `mmr_candidates` and `reranker_fetch_k` 100 → **500** (the pool cap), `reranker_top_k` 20 → **500** (so the endpoint keeps the CE's whole ranking). |
| **IS NOT** | a collection write, a re-ingest, or a `src/` change. |
| **IS NOT** | a like-for-like "same pool, higher k" test — the wide pool is a **different composition** (a set-superset of the narrow pool). This is **wider pool AND higher k**, stated as such. |

---

## 3. The quantities

```
CE_pages     the cross-encoder's ordered page list over the wide pool (<= 500), page-deduped
pool_pages   the fused pool's own order (the CE's input)
cov          |CE_pages ∩ reachable| / |reachable|
k grid (in the companion sweep)  (1,2,5,10,20,30,40,50,75,100,150,200,250)
```

The per-type k sweep (R@k / nDCG@k / P@k / cov@k, per-type pool-aware ceilings, capture) is a SEPARATE
read-only harness (`wide_ce_k_sweep.py`), exactly as `cut_ndcg_k.py` followed `t4_endpoint.py`.

---

## 4. The READ RULE and predictions (fixed BEFORE the numbers exist)

* A delta is **RESOLVED** iff its paired 95 % CI excludes 0.
* ⚠️ **The comparability trap, in BOTH directions.** Where `k < n_rel`, IDCG grows with k (comparable).
  Where `k >= n_rel`, `IDCG(n_rel,k)` **saturates** while the DCG numerator keeps growing, so `nDCG@k`
  rises **BY CONSTRUCTION**. Every k must be read against `n_rel` — a k above the query's `n_rel` is not a
  ranking measurement.

**Registered predictions (falsifiable):**

1. **`R@k` and `cov@k` rise monotonically to k=250**, largest for overview (median `n_rel` ~58).
2. **`nDCG@k` does NOT improve in the comparable regime** (`k < n_rel`); any rise above `k ≈ n_rel` is
   the IDCG denominator saturating, and will be reported as such.
3. **The CE arm @20 ≈ §I105's CE @20** — the wide pool's top-20 is near the narrow pool's top-20 (§I92:
   the cap is inert at the endpoint). Anchor, not a finding.
4. ⇒ **The verdict of §I105 survives a wider pool**: wider k buys recall/coverage, not ranked quality.

**Falsification clause.** If, **within `k < n_rel`**, overview's `ΔnDCG@k` vs k=20 resolves **positive**,
then a wider pool + wider k DOES improve ranked quality and §I105 is superseded.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population 133; per type 53 / 40 / 40. |
| **G2** | **reachable pages == 888** (T0's recorded value) — the filter is the registered one. |
| **G3** | **zero errors**. |
| **G4** | **zero reranker fallbacks** (§I55 — a fallback returns the pool UNRANKED). |
| **G5** | the CE list is longer than the product's 20 (the cap actually widened): `min(len(CE_pages)) > 20`. |
| **G6** | the pool is wider than the product's (mean pool size ≫ 86.47, T0's cap-100 mean). |

---

## 6. Bounds

* One corpus, one document, one funnel. n=40 per non-factual type.
* The cluster reranker is a single point of failure; a fallback on any query is counted (G4) and the
  affected query's endpoint is the pool order, not a ranking.
* **Read-only**: nothing written to any collection, no re-ingest, no embedder change.
