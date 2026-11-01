# P1 — 5A: THE OVERVIEW METRIC DIAGNOSIS — is overview's loss the MEASURING STICK or the RANKER? (pre-registration)

> **Written 2026-10-31, BEFORE the re-derivation is run.** Per **D6.1** it is **committed ALONE**, and
> nothing measured is in it.
>
> Read first: `HANDOFF.md` (session 28), `IMPROVEMENTS.md` **§I99** (the endpoint decomposition this
> sharpens), **§I100** (item 9 — "the overview metric itself is now a live suspect"), **§I98** (the lane
> answer, closed), **§I58** (the reachability ceiling), **§I93/§I94a** (metric provenance and the label
> question), `logs/p1/step10/levers_report.md` §2/§3, and `scripts/evaluate_rag.py:351-448` (the metric
> functions this must reproduce).

---

## 1. The question

§I100 registered, in one sentence, a suspicion that has never been tested:

> *"The overview metric itself is now a live suspect: its label sets are broad (73.8 pages of 968), the
> pool is 35 % gold, and no ranker — fused, weighted, dense-only or cross-encoded — surfaces more than
> ~51 % of its slots as gold."*

**This entry separates the two readings of that sentence, and it is the GATE for 5B (graded labels):**

1. **THE MEASURING STICK IS BROKEN** — overview's low scores are an artifact of the metric: a broad
   label set (mean 73.8 pages, max 314) makes recall's denominator enormous, so even a good ranker reads
   as a failure. *Fix: change the metric / grade the labels (5B).*
2. **THE RANKER IS BROKEN** — the low scores are real ranking loss. Against its OWN ceiling the ranker
   sits far below what is achievable, so the metric is not the constraint. *Fix: keep hunting the
   ordering loss (4A/4B, §A); 5B is hygiene, not a fix.*

⚠️ **These have different fixes, and choosing before the split is measured is what D6.1 exists to prevent.**

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only re-derivation** over EXISTING artifacts (`t4_endpoint.json`, `t0_baseline.json`, `fusion_order.json`). No cluster, no LLM, no run, no collection write, no re-ingest. |
| **IS NOT** | a new measurement. It reads no new number out of the system; it computes ceilings and capture ratios the register has never put beside the realised values. |
| **IS NOT** | a label change. Nothing in `data/` is touched. 5B is where labels would change, and this decides whether 5B is warranted. |
| **IS NOT** | a re-run of §I99. §I99 decomposed the RECALL loss into pool/order/CE. This adds the PRECISION and nDCG ceilings (never computed pool-aware) and the capture ratio per metric family. |

---

## 3. The quantities (definitions, fixed here)

Per query, from the source artifact's own arrays (`relevant_pages`, `n_relevant`, `n_reachable`,
`C_pool_cov`, `C_pages`, `C_metrics`):

```
n_rel          labelled pages (source: n_relevant)
n_reach        of those, reachable in the index window (source: n_reachable)
pool_gold      = C_pool_cov * n_reach      labelled pages the product's pool actually holds
k              = 20                        the product's endpoint cut (reranker_top_k)
```

**Realised values** (the product, arm C) are read from `C_metrics`: `recall_at_20`, `precision_at_20`,
`ndcg_at_20`.

**Ceilings — LABEL-side** (properties of the gold set alone; what the register already reports):

```
R_ceil_label   = min(k, n_rel) / n_rel
P_ceil_label   = min(n_rel, k) / k          ( = 1.0 for every overview query, since n_rel > k )
```

**Ceilings — POOL-AWARE** (⚠️ the correction this entry exists to make): the best ANY ranker could do is
bounded by the gold that is actually IN the pool the product built, not by the label set:

```
R_ceil_pool    = min(k, pool_gold) / n_rel          == §I99's pool_oracle_20
P_ceil_pool    = min(pool_gold, k) / k
nDCG_ceil_pool = IDCG(min(pool_gold, k)) / IDCG(k)   (binary gains, page-deduped, as evaluate_rag.py:405-408)
```

⚠️ **The report's `P-ceil@20` is the LABEL ceiling (`min(n_rel,k)/k` = 1.0 for overview). It overstates
what is achievable whenever the pool holds fewer than `k` gold pages.** The pool-aware ceiling is the
honest one, and it is the denominator the capture ratio below uses.

**Capture ratio** — the whole point:

```
capture(metric, type) = realised(metric, type) / ceiling_pool(metric, type)
```

`capture = 1.0` means the ranker already achieves everything the pool allows (the metric is the
constraint). `capture` well below 1.0 means there is recoverable ranking loss (the ranker is the
constraint).

**pool_gold distribution** — per type, the fraction of queries with `pool_gold >= k` (the fraction whose
pool-aware ceiling is 1.0), and the mean/median/min/max of `pool_gold`.

---

## 4. The MMR subset check (the Q3 question, folded in)

`fusion_order.json` carries `O0_mmr_fired` per query. This re-derives:

* the MMR-firing SET (must be the same 16 of 133 §I100 recorded) and its **per-type split**;
* on those firing queries, `O1 − O0` (MMR off vs the product) for `ndcg_at_20`, `recall_at_20`,
  `mrr_at_20` — i.e. **does MMR move the metric on the very queries where it fires?** The aggregate
  `O1 − O0` is a measured null (§I100); the question this answers is whether the 16 individually move
  with opposite signs (cancelling) or are individually null.

---

## 5. The READ RULE (fixed BEFORE the numbers exist)

For each type and each metric family (R, P, nDCG), compute `capture`. Then:

| verdict | condition |
|---|---|
| **METRIC-LIMITED** | `capture >= 0.90` on a family — the ranker is within 10 % of the pool's own bound, so the low raw number is the ceiling's fault. |
| **RANKER-LIMITED** | `capture < 0.90` — there is recoverable ranking loss; the metric is not the constraint. |

⚠️ **The 0.90 threshold is fixed here and may NOT be moved after the run** (the §D1 rule).

**Registered prediction (falsifiable).** From `levers_report.md` §2 the realised/ceiling ratios for
overview are R 0.1882/0.3992 = **0.47**, P 0.5125/1.0 = **0.51**, nDCG 0.5379/1.0 = **0.54** — all
near half. **I predict overview is RANKER-LIMITED on all three families** (capture < 0.90 everywhere),
so the "broken measuring stick" reading is **REFUTED for overview**, and 5B (graded labels) is
**hygiene, not a fix**. If instead any family returns `capture >= 0.90`, the metric IS the suspect for
that family and 5B is warranted for it.

---

## 6. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **population** — 133 queries, and per type 53 / 40 / 40, matching the source artifact. |
| **G2** | **the realised values reproduce the artifact's own aggregates** — arm C's mean `recall_at_20` / `precision_at_20` / `ndcg_at_20` per type, re-derived from the per-query `C_metrics`, equal the report's §2 to 1e-4. |
| **G3** | **the label ceilings reproduce §I99** — mean `R_ceil_label` per type = 0.9557 / 0.3992 / 1.0000 to 1e-4; overall 0.8016. |
| **G4** | **`R_ceil_pool` equals §I99's `pool_oracle_20`** per type to 1e-9 (the same quantity, two code paths). |
| **G5** | **the MMR set is the 16 §I100 recorded** — `|{O0_mmr_fired}|` = 16, and it equals the set of queries where `O1_pool_sha != O0_pool_sha` (§I100 item 4). |
| **G6** | **no NaN / null** in any emitted aggregate; `n_rel >= 1` and `n_reach >= 0` on every query. |

---

## 7. Verifier and mutation proof

* **Independent stdlib verifier** `logs/p1/step10/overview_metric_diag_verifier.py` — re-derives every
  aggregate cell from the SOURCE per-query arrays (not from the harness's own output) and re-checks
  G1–G6. Reads only the written JSON plus the source artifacts.
* **Mutation proof** `logs/p1/step10/overview_metric_diag_mutation.py` — mutates a copy of the artifact
  once per check and asserts each mutation reddens its intended check; **no inert check** may remain.
  Run BEFORE the numbers are read (the checks are population-specific, so they need a full-shaped
  artifact — the §I91/§I100 precedent if it must run after).

---

## 8. Registration

On completion: a register entry in `IMPROVEMENTS.md` (the finding, the ceilings, the capture ratios,
the MMR subset result, the deviations), a `HANDOFF.md` session-29 block, and the artifact
`logs/p1/step10/overview_metric_diag.json`. **Read-only. Nothing written to any collection. No run.**

---

## 9. What would falsify this

* If any overview family returns `capture >= 0.90`, my prediction is wrong and the metric IS the suspect
  for that family → 5B is warranted.
* If the pool-aware P/nDCG ceilings come out materially BELOW the label ceilings (pool_gold < k for many
  overview queries), then the report's `P-ceil = 1.0` is misleading and the capture ratio must be quoted
  against the pool-aware ceiling — a correction to §I99's framing, not a contradiction of it.
