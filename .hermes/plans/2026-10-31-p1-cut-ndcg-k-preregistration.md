# P1 — 4B: THE ENDPOINT CUT, MEASURED AS nDCG@k (not just coverage) — does widening the cut improve the RANKING? (pre-registration)

> **Written 2026-10-31, BEFORE the re-derivation is run.** Per **D6.1** it is **committed ALONE**, and
> nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 29), `IMPROVEMENTS.md` **§I97** (T4 — which measured the cut's
> COVERAGE half, +0.1451, and only that), **§I99** (the decomposition; `waste_ce`), **§I101** (5A, the
> overview-metric diagnosis), `logs/p1/step10/levers_report.md` §4 (the "20-slot endpoint cut" row), and
> `scripts/evaluate_rag.py:405-448` (the nDCG/IDCG convention this must reproduce).

---

## 1. The question

§I97 P3 measured the 20-slot cut's **coverage** cost — arm W50 vs arm C, **+0.1451 [+0.1125, +0.1777]
RESOLVED** — and the register read that as *"a deliberate context budget, not a bug."* **But coverage is
not ranking.** No run has measured whether the cut changes **nDCG@k** or **R@k**. This closes that gap.

**A structural fact, measured on the artifact BEFORE this document was written, that fixes the design:**

> On **133 of 133** queries, `W50_pages[:20] == C_pages` (and `C_pool_sha == W50_pool_sha`). **The
> cross-encoder's top-20 is a PREFIX of its top-50.** The cut is applied *after* reranking, so widening it
> appends ranks 21–50 and **cannot move any @20 metric** — the top-20 is byte-identical.

⇒ **The cut is provably ranking-neutral at k=20.** What remains to measure is what the EXTRA slots
(21–50) are worth: their nDCG@50, R@50, and precision contribution, against their own ceilings.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only re-derivation** over ONE existing artifact (`t4_endpoint.json`): arm C (CE, top-20) and arm W50 (CE, top-50). No cluster, no LLM, no run, no collection write. |
| **IS NOT** | a new run. ⚠️ **k=100 is NOT available read-only** — T4 kept at most 50 — so this covers **k ∈ {20, 50}** and states k=100 as a named follow-up (see §6). |
| **IS NOT** | a coverage re-statement. §I97 measured coverage; this measures **nDCG@k, R@k, P@k** with **paired 95 % CIs** over the 133 queries. |
| **IS NOT** | a claim about the generator. Whether slots 21–50 help the *answer* is the generator stage, unmeasured. |

---

## 3. The quantities (definitions, fixed here)

Per query, from the source artifact's own arrays (`C_pages`, `W50_pages`, `relevant_pages`, `n_relevant`,
`n_reachable`, `C_pool_cov`):

```
k20 = 20,  k50 = 50
nDCG@k, R@k, P@k   computed by the evaluate_rag.py convention on the arm's page list truncated to k
                   (binary gains, page-deduped; IDCG over min(n_rel, k))
ceilings           label:     R-ceil@k = min(k,n_rel)/n_rel ; P-ceil@k = min(n_rel,k)/k
                   pool-aware: R-ceil_pool@k = min(k,pool_gold)/n_rel ; P-ceil_pool@k = min(pool_gold,k)/k
                               nDCG-ceil_pool@k = IDCG(min(pool_gold,k)) / IDCG(min(n_rel,k))
pool_gold          = round(C_pool_cov * n_reach)
extra_slots_gold   = | (W50_pages[20:50]) ∩ relevant |   the gold the extra 30 slots add
```

**Reported per type and overall:**
* `nDCG@20` (arm C) and `nDCG@50` (arm W50), each beside its **pool-aware ceiling**;
* `R@20`/`R@50`, `P@20`/`P@50`, each beside its ceiling;
* `extra_slots_gold` — the gold added by ranks 21–50;
* **paired deltas** `nDCG@50 − nDCG@20`, `R@50 − R@20`, `P@50 − P@20`, with **paired bootstrap 95 % CIs**
  (10,000 resamples, seed fixed at 20261031).

---

## 4. The READ RULE (fixed BEFORE the numbers exist)

* A delta is **RESOLVED** iff its paired 95 % CI excludes 0; otherwise it is **null**.
* ⚠️ **The prefix identity `W50[:20] == C` is a GUARD, not a finding** — if it held before the run it must
  hold in the re-derivation, and it explains why the @20 cells are identical. It is asserted, not
  reported as a result.

**Registered predictions (falsifiable):**
1. **`nDCG@20`, `R@20`, `P@20` are IDENTICAL between the two arms** (the prefix identity) — a
   reproduction, not a result.
2. **`nDCG@50 − nDCG@20` is UNRESOLVED or NEGATIVE** — the extra 30 slots are ranked below the top-20, so
   they cannot raise the average ranked quality; if the CE's tail is weak this resolves **negative**.
3. **`R@50 − R@20` RESOLVES POSITIVE** — the extra slots add gold pages (this is §I97's +0.1451 coverage,
   now as recall against the label denominator).
4. ⇒ **The cut is a CONTEXT-BUDGET knob, not a ranking lever**: it cannot improve the top-20, and its only
   measurable gain is more gold *below* rank 20. If prediction 2 is unresolved/negative and 3 positive,
   that is confirmed.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **population** — 133 queries; per type 53 / 40 / 40. |
| **G2** | **the prefix identity** — `W50_pages[:len(C_pages)] == C_pages` on every query; and `C_pool_sha == W50_pool_sha` on every query. |
| **G3** | **the @20 metrics reproduce T4's arm C** — per-type mean `nDCG@20` / `R@20` / `P@20` equal the source artifact's own `C_metrics` to 1e-4. |
| **G4** | **the @50 metrics reproduce T4's arm W50** — per-type mean `R@50` re-derived equals the source's `W50_metrics["recall_at_50"]` to 1e-4 (a second, independent path to the same number). |
| **G5** | **`extra_slots_gold >= 0` and `len(W50_pages) >= len(C_pages)`** on every query. |
| **G6** | **no NaN / null** in any emitted aggregate. |

---

## 6. Named follow-up (not in this entry)

**k=100** requires a run (T4 kept ≤ 50). ⚠️ **Given the prefix identity, ranks 51–100 are the same kind of
question as 21–50** — a context-budget question, not a ranking question — so k=100 is **only worth a run
if k=50 shows the extra slots add gold at an acceptable nDCG cost.** Stated here so the decision is not
made after seeing the k=50 numbers.

---

## 7. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/cut_ndcg_k_verifier.py` — re-derives every cell from the
  SOURCE per-query page lists and labels (not the harness's output), re-checks G1–G6, and re-runs the
  bootstrap with the same seed.
* **Mutation proof** `logs/p1/step10/cut_ndcg_k_mutation.py` — one mutation per check, each must redden its
  intended check; **no inert check**.

---

## 8. Registration

On completion: an `IMPROVEMENTS.md` entry (the finding, the k=20/50 tables, the paired CIs, the guard
results, the deviations), a `HANDOFF.md` session-30 block, and the artifact
`logs/p1/step10/cut_ndcg_k.json`. **Read-only. Nothing written to any collection. No run.**

---

## 9. What would falsify this

* If `W50_pages[:20] != C_pages` on any query, the prefix identity is false and the cut is NOT
  ranking-neutral at 20 — the whole framing changes.
* If `nDCG@50 − nDCG@20` RESOLVES POSITIVE, the extra slots DO improve ranked quality and the cut is a
  ranking lever after all (prediction 2 wrong).
* If `R@50 − R@20` is UNRESOLVED, §I97's coverage gain does not translate to recall (prediction 3 wrong).
