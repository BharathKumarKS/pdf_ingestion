# P1 — THE WIDE-POOL k SWEEP: does a WIDER pool + higher K change the per-type picture? (pre-registration)

> **Written 2026-11-01, BEFORE the re-derivation is run.** Per **D6.1** it is **committed ALONE**, and
> nothing measured is in it.
>
> Read first: `IMPROVEMENTS.md` **§I105** (the per-type k sweep on the product's own pool, k ≤ 50 for the
> CE arm and ≤ 50 for the pool arm), **§I92** (the 100→500 cap: pool coverage +0.1835 → endpoint +0.003),
> **§I103** (score fusion; the composition trap), **§I99** (`waste_order`), and
> `scripts/evaluate_rag.py:405-448` (the nDCG/IDCG convention).

---

## 1. The question

§I105 answered "does a wider cut help, per type?" **on the product's pool (cap 100)**. The owner's next
question: **widen the pool cap and sweep k higher.** The CE arm at k > 50 needs a RUN (no artifact holds
the cross-encoder's ranking over a wide pool) — that is a separate pre-registration.

**This pre-registration covers the half that is READ-ONLY:** the **pool's own order at cap 500**, which
`fusion_attribution.json` already recorded (`W500_pages`, 268–389 pages/query). It answers whether the
per-type picture changes when the pool is wider and k goes to 250 — and specifically whether §I105's
**capture artifact** (a shrinking ceiling) survives a wider pool.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only re-derivation** over ONE existing artifact (`fusion_attribution.json`). No cluster, no LLM, no run. |
| **IS** | **two arms at the SAME cap ladder**: **POOL100** = the pool's order at cap 100 (`C_pages`, 55–100 pages); **POOL500** = the pool's order at cap 500 (`W500_pages`, 268–389 pages). |
| **IS NOT** | the CE arm. ⚠️ The cross-encoder's ranking over a wide pool is **not** in any artifact (verified: `fusion_attribution`'s `C_pages`/`W500_pages` are the POOL, not the CE — `C_pages[:20]` equals `t0.fusion_ranked[:20]`). That arm needs a run. |
| **IS NOT** | a like-for-like "same pool, higher k" test. The two pools are **different compositions** (§I103's trap) — the wide pool is a **set-superset** of the narrow one (133/133) but adds candidates. So this is **wider pool AND higher k**, stated as such. |

---

## 3. The quantities (definitions, fixed here)

```
POOL100  = fusion_attribution.json  C_pages      (the pool's RRF order at cap 100)
POOL500  = fusion_attribution.json  W500_pages   (the pool's RRF order at cap 500)

POOL100_KS = (1, 2, 5, 10, 20, 30, 40, 50)                     # 50 = safe; C_pages min length is 55
POOL500_KS = (1, 2, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200, 250)   # 250 = safe; W500 min length is 268
K_ANCHOR   = 20

R@k, nDCG@k, P@k   the evaluate_rag.py convention (binary gains, page-deduped, IDCG over min(n_rel,k))
cov@k              |gold ∩ top-k pages| / n_reachable
pool_gold          = round(pool_cov * n_reach)     (C_cov for POOL100, W500_cov for POOL500)
ceilings           R_ceil_pool@k = min(k, pool_gold)/n_rel
                   nDCG_ceil_pool@k = IDCG(pool_gold,k)/IDCG(n_rel,k)
capture            realised / ceiling, per query then averaged
```

Paired deltas vs k=20, **paired bootstrap 95 % CIs** (10,000 resamples, seed **20261031**), per type.

---

## 4. The READ RULE (fixed BEFORE the numbers exist)

* A delta is **RESOLVED** iff its paired 95 % CI excludes 0; otherwise **null**.
* **Comparability split (§I102's trap) on every k > 20**: `n_rel <= 20` (same IDCG denominator ⇒
  non-negative by construction) vs `n_rel > 20` (comparable). Only the second block is a finding.

**Registered predictions (falsifiable):**

1. **`R@k` and `cov@k` rise monotonically with k on BOTH arms** (truncation identity), and **POOL500
   reaches a higher recall at matched k than POOL100** where the wide pool added gold (§I92: +0.1835
   pool coverage).
2. **`nDCG@k` does NOT improve materially on either arm**; on the comparable block it is ~flat or
   negative — the §I105 result reproduced on a wider pool.
3. **THE CRUX — the §I105 capture artifact should DIMINISH on POOL500.** §I105's apparent capture gain
   came from the ceiling shrinking as k passed `pool_gold` (~31). A **wider pool holds more gold**
   (`W500` pool_gold median 6, **max 173**, vs `C` max 61), so the ceiling is **higher**, so
   `capture_nDCG@k` for overview should be **flatter and lower** than on POOL100. If so, §I105's capture
   rise is confirmed as a narrow-pool ceiling effect.
4. **POOL100 reproduces §I105's POOL arm** on the shared k grid (20/30/40/50) — a cross-artifact anchor.

**Falsification clause.** If overview's `capture_nDCG` on POOL500 **also rises > +0.05** from k=20 to
k=250, then the capture rise is NOT a narrow-pool artifact and §I105 item 3 must be revisited.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population 133; per type 53 / 40 / 40. |
| **G2** | **cross-artifact anchor** — `fusion_attribution.C_pages[:20] == t0.fusion_ranked[:20]` on 133/133 (proves `C_pages` IS the pool order). |
| **G3** | **set-superset** — `set(C_pages) ⊆ set(W500_pages)` on 133/133. |
| **G4** | **monotone** — `R@k` non-decreasing in k, per query, both arms. |
| **G5** | **k within the list** — no k exceeds a query's available list length, or it is REPORTED. |
| **G6** | **§I105 reproduction** — POOL100's per-type mean R@20/nDCG@20 match §I105's POOL arm to 5e-5. |

---

## 6. Bounds and named follow-ups

* **The CE arm (the LAST layer) at k > 50 is NOT in this document** — it needs a run
  (`QDRANT_HOST=10.0.10.65`, `knowledge_base_v3`, 3,869 points, cap 500, recording `reranked` not `hits`).
* One corpus, one document, one funnel. n=40 per non-factual type.
* **Read-only**: nothing written to any collection, no re-ingest.
