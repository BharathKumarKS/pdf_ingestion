# P1 — THE PER-TYPE k SWEEP at the endpoint: does a WIDER cut improve the metric, per query type? (pre-registration)

> **Written 2026-11-01, BEFORE the re-derivation is run.** Per **D6.1** it is **committed ALONE**, and
> nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 31), `IMPROVEMENTS.md` **§I97** (T4 — the cut's coverage half),
> **§I99** (the per-type endpoint decomposition; `waste_order`), **§I101** (5A — the overview-metric
> diagnosis; the capture method and its ceilings), **§I102** (4B — the cut as nDCG@k; the prefix identity
> and the construction artifact), **§I103** (4A — score fusion; the lane-tail nondeterminism), and
> `scripts/evaluate_rag.py:405-448` (the nDCG/IDCG convention this must reproduce).

---

## 1. The question

§I97 P3 and §I102 measured the endpoint cut **20 → 50** on the WHOLE population: recall rises
(`ΔR@k +0.1433` RESOLVED), nDCG@k is unresolved where comparable (`−0.0078`), and the top-20 cannot move
(prefix identity). **Neither run reported per query TYPE, and neither recomputed the per-type ceilings.**

The owner's hypothesis: **wider k at the last layer improves the metric, and the benefit is
type-dependent** — a broad (overview) question should gain from more slots while a narrow (factual)
question should not.

This pre-registration fixes the design that tests it, per type, with the §I101 capture method.

**Structural facts, measured on the artifacts BEFORE this document was written, that fix the design:**

> 1. `W50_pages[:20] == C_pages` on **133/133** (the CE's top-20 is a prefix of its top-50) — the cut is
>    provably ranking-neutral at k=20.
> 2. `t0.fusion_ranked[:20] == t4.N_pages` on **133/133** — two independent runs (T0, T4) agree on the
>    pool's own order, so the POOL arm is anchored to the same pool the CE arm ranks.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only re-derivation** over TWO existing artifacts (`t4_endpoint.json`, `t0_baseline.json`). No cluster, no LLM, no run, no collection write. |
| **IS** | **per query type** (factual 53 / overview 40 / multihop 40), **per k**, with **per-type pool-aware ceilings** and the **capture ratio**. |
| **IS NOT** | a new run. ⚠️ **k > 50 for the CE arm is NOT available read-only** (T4 kept ≤ 50); **k > 100 is impossible** without widening the pool cap (a run). Both are named follow-ups (§7). |
| **IS NOT** | a generator claim. Whether the extra slots help the *answer* is the generator stage, unmeasured. |
| **IS NOT** | a claim that wider k cannot help — it measures whether it does, and against the right ceiling. |

---

## 3. The quantities (definitions, fixed here)

Per query, from the source artifacts' own arrays:

```
arm CE   = t4_endpoint.json  W50_pages  (the cross-encoder's ranked pages; the LAST layer)
arm POOL = t0_baseline.json  fusion_ranked  (the fused pool's own RRF order; the layer BEFORE the CE)

CE_KS   = (1, 2, 5, 10, 20, 30, 40, 47)   # 47 = the safe min length of W50_pages across the 133
POOL_KS = (1, 2, 5, 10, 20, 30, 40, 50)   # 50 = safe; pool lengths run 55..100
K_ANCHOR = 20                              # the shipped setting; all deltas are vs this
```

Metrics per arm, per type, per k (the `evaluate_rag.py` convention):
```
R@k        recall, denominator = n_rel
nDCG@k     binary gains, page-deduped, IDCG over min(n_rel, k)
P@k        denominator = k
cov@k      |gold ∩ top-k pages| / n_reachable
ceilings   pool_gold            = round(pool_cov * n_reach)
           R_ceil_pool@k        = min(k, pool_gold) / n_rel
           nDCG_ceil_pool@k     = IDCG(pool_gold, k) / IDCG(n_rel, k)
capture    realised / ceiling, computed PER QUERY then averaged within type (§I101's convention)
```

Paired deltas vs k=20, **paired bootstrap 95 % CIs** (10,000 resamples, seed **20261031**), per type.

---

## 4. The READ RULE (fixed BEFORE the numbers exist)

* A delta is **RESOLVED** iff its paired 95 % CI excludes 0; otherwise **null**.
* ⚠️ **Comparability split (§I102's trap), applied to EVERY k > 20.** Where `n_rel <= 20`, `IDCG@20 ==
  IDCG@k`, so the k-list is a superset with the SAME denominator and the nDCG delta is **non-negative BY
  CONSTRUCTION**. The population is split at `n_rel <= 20` vs `n_rel > 20`; **only the second block is a
  finding.** Reported for both, never aggregated silently.

**Registered predictions (falsifiable):**

1. **`R@k` and `cov@k` rise monotonically with k for every type** (a superset, so by construction), and
   the rise is **largest for overview** (median `n_rel` 58) and **smallest for multihop/factual**
   (median `n_rel` 3). This is the "wider k buys recall" half, shown per type.
2. **`nDCG@k` does NOT improve materially for any type.** On the comparable block (`n_rel > 20`) the
   delta vs k=20 is **~flat or slightly negative** (§I102 got `−0.0078` at 20→50).
3. **THE CRUX — overview's CAPTURE does NOT rise with k.** Because the pool-aware ceiling grows with k at
   least as fast as the realised value, `capture_nDCG@k` (overview) is ~flat in k. If so, **wider k does
   not close overview's gap to what its pool can support; it returns more of the same.**
4. **The CE arm's @20 cells are IDENTICAL across k** (the prefix identity) — a reproduction, not a result.

**Falsification clause.** If **overview's `capture_nDCG` rises materially with k** (defined: `> +0.05`
from k=20 to k=47), the "wider k helps" hypothesis is **SUPPORTED** and a full-pool run is warranted.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **population** — 133 queries; per type 53 / 40 / 40; the two artifacts' ids align pairwise. |
| **G2** | **prefix identity** — `W50_pages[:20] == C_pages` on 133/133 (a guard, not a finding). |
| **G2b** | **pool sha** — `C_pool_sha == W50_pool_sha` on 133/133. |
| **G3** | **cross-artifact anchor** — `t0.fusion_ranked[:20] == t4.N_pages` on 133/133. |
| **G3b** | **same pool** — the CE arm's `pool_gold` and the POOL arm's `pool_gold` agree per query (reported, tolerance 0). |
| **G4** | **monotone** — `R@k` and `cov@k` are non-decreasing in k, per query (a superset by construction). |
| **G5** | **anchor to the artifact** — the CE arm @20 reproduces `t4.C_metrics`' `recall_at_20` and `ndcg_at_20` per query (tol 5e-5). |
| **G6** | **k within the list** — no k exceeds a query's available list length, or it is REPORTED (never silently truncated). |

---

## 6. Deliverables

The harness `logs/p1/step10/per_type_k_sweep.py` → `per_type_k_sweep.json`; the independent stdlib
verifier `per_type_k_sweep_verifier.py`; the mutation proof `per_type_k_sweep_mutation.py`; and the
per-type × k tables in the write-up.

---

## 7. Bounds and named follow-ups

* **CE arm capped at k=47** (T4 kept ≤ 50). k > 50 for the CE needs a run.
* **POOL arm safe to k=50**, partial to 100 (pool lengths run 55..100).
* **k > 100 is IMPOSSIBLE** without widening the pool cap (default 100) — a separate run (§I92 measured
  the cap 100→500 as +0.1835 pool coverage → +0.003 endpoint).
* **n = 40** per non-factual type ⇒ point estimates on the ceilings; the paired deltas do get CIs.
* **Read-only**: nothing written to any collection, no re-ingest, no embedder change.
