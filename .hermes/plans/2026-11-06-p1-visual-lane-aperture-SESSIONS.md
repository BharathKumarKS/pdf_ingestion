# Visual-lane aperture — step-by-step plan (2026-11-06)

> **Priority 1 of the next session, per the owner (2026-11-05): the VISUAL QUERY part FIRST, then the
> embedder and the guardrails.** This file is the resumable plan for that first part: read it, find the
> first ⬜ in the status table, continue.
>
> **Source of truth for the PROBLEM:** `IMPROVEMENTS.md` §I107 (the measurement) and §I123 (the
> correction of the record). **The scope this expands:** `.hermes/plans/2026-11-02-p1-nicegui-and-visual-lane-SESSIONS.md`
> §2 Part B (VL-L1/L2/L3).
>
> **Every step carries its own acceptance check + independent (different-family) reviewer + a
> DETERMINISTIC verifier + a mutation proof.** A step with no verdict is **not done** and is **not
> committed**. §8 is the resume point; §9 is the contract.

---

## 0. The frame (what is actually broken, and what "fixed" may legitimately turn out to be)

**What is broken.** The visual lane's aperture is `cfg.visual_score_threshold = 0.58` — a raw
mean-best-cosine bar (`store.py:1927`; the eval applies it at `evaluate_rag.py:358`). §I107 measured
that raw cosine **cannot separate** in-domain from near-domain: the weakest in-domain concept scores
**0.4936** while a near-domain image scores **0.5609** (a near-domain image OUTSCORES the weakest
in-domain one); noise **0.4578**, a logo **0.4355**; verdict **`separating: NONE`**. §I123 records
that the config comment justifying 0.58 is contradicted by that same measurement (its 0.94–1.00 band
describes the **self-match regime** — V1 passed 12/12 at cosine **1.0000** — not real figures).

**What "fixed" means — and the outcome that is ALLOWED.** The deliverable is **a justified aperture**,
which is one of exactly two things:
1. **A calibrated statistic** (margin / z-score / the query's own score distribution) that separates
   in-domain from near-domain/far-domain at a measured threshold, with its false-positive rate on
   benign traffic — **or**
2. **A recorded `no-separation`**, with the threshold policy then made EXPLICIT (no gate; or a
   documented floor whose only job is to drop noise) and the misleading comment corrected.

⚠️ **`no-separation` is a RESULT, not a failure.** §I107 already points at it; a plan that can only
succeed by finding a separating statistic is a plan that will manufacture one. The pre-registration
must fix the falsification clause **before** the run, exactly as the §I112 probe did.

**Why it matters at all.** With no usable aperture the lane has **neither** a labelled retrieval
metric **nor** a confidence gate — so it cannot refuse, cannot abstain, and cannot be reported. That
is what blocks VL-L3 and the H-workstream's grounding floor from ever seeing a visual row.

## 1. Reuse map (do not rebuild what exists)

| need | existing asset | use |
|---|---|---|
| the §I107 measurement + its probe set | `logs/p1/step10/visual_lane_validation.py` → `.json` | the starting labels and the reproduction anchor |
| the lane's score path | `store.visual_search` (MaxSim ÷ query-patch count) | the score is ALREADY a mean best cosine — the normalisation lever is partly applied |
| the product's metrics | `evaluate_rag.compute_retrieval_metrics` | V5's ranking table (recall@k / MRR / nDCG) |
| the visual queries | the 33 visual queries (⚠️ **unlabelled** — hence 133 gold queries, not 166) | V3 must label them |
| the eval artifacts pattern | any `logs/p1/step10/*_verifier.py` + `*_mutation.py` pair | the V-step verifier/mutation shape |

⚠️ **Two shape facts, measured:** `visual_search` **filters at `score_threshold` and caps at `limit`** —
so to capture a *distribution* it must be called with **threshold 0 and a large limit**. And the
stored score is the **mean** best cosine over a fixed patch grid, not a raw MaxSim sum (the old 0.15
value was applied to the raw sum and filtered nothing).

## 2. The steps

| id | step | kind | depends on |
|---|---|---|---|
| **V1** | capture the full per-query score distribution (threshold 0, large limit) | read-only run | — |
| **V2** | derive top1 / margin / z-score; test whether ANY separates in/near/far | read-only run | V1 |
| **V3** | build the REAL labelled set (figure crops, provenance per image) | annotation | — |
| **V4** | the aperture decision: wire the statistic, or record no-separation + fix the comment | code + doc | V2 (+V3) |
| **V5** | rank the lane with labels (`compute_retrieval_metrics`), add the visual row | measurement | V3 |

**V1 — the score-distribution harness (read-only; do FIRST).** Store the **full top-k score list per
query** so every later statistic is re-derivable from the raw array rather than recomputed ad hoc.
Acceptance: the artifact holds, per query, the ordered score list and the page ids, captured at
threshold 0 / a large limit; the number of queries matches the probe set; the run is read-only.
⚠️ **Pre-register this run and commit the pre-registration ALONE first (D6.1)** — it is a measurement.

**V2 — the statistic comparison (read-only; this is the actual answer).** Re-derive, per query:
`top1`, `margin = top1 − top2`, and `z = (top1 − μ_query) / σ_query` where μ/σ come from the query's
OWN score distribution over the corpus. Report, per statistic, whether it separates the three groups,
with the pre-registered falsification clause. **Also settle the V1 self-match question** — is the
query image the stored one? (a cosine of exactly 1.0000 is a self-match signature, not cross-render
proof). Deliverable: artifact + **deterministic** verifier + mutation proof.

**V3 — the real labelled set (annotation, not code).** ⚠️ The current in-domain group is **synthetic
matplotlib plots** — in-domain by *topic*, not by *appearance* — while the near-domain group is also
plots, so the test set **confounds the question it is meant to answer**. Build: in-domain = figure
**crops from the actual Feynman pages**; near-domain = figures from a **different** physics book;
far-domain = photos/logos/noise. **Provenance recorded per image.** Acceptance: every image names its
source page/file and its group; the in-domain group is real crops.

**V4 — the aperture decision (the fix).** If V2 found a separating statistic: wire it as the gate,
with the **measured** threshold and the false-positive rate on benign traffic, and the per-check
fail-open/closed posture stated. If V2 found none: record **`no-separation`** explicitly, set the
threshold policy to what the evidence supports, and **correct the config comment** (§I123) so it no
longer asserts a separation the measurement contradicts. Either branch is a complete step.

**V5 — the ranking metrics (VL-L3).** Label the visual queries / crops with their true page, score the
lane with the product's own `compute_retrieval_metrics`, and add the visual row to the same per-type
table the text lane uses. This is the only route to a real "is the visual lane performing?" number.

## 3. Verification contract (per step)

1. **Acceptance check** run by the author; the raw output read.
2. **Independent reviewer** — different model family, read-only, given the diff + numbered claims,
   told to re-derive rather than agree.
3. **DETERMINISTIC verifier** — a **stdlib program**, not a judge: given the artifact, it recomputes
   **every reported cell from the raw per-item array** and compares. Its own evaluation is therefore
   reproducible and needs no model. ⚠️ **This is the owner's requirement: the verifier's evaluation
   must be deterministic.** An LLM reviewer is the *second* check (judgment on the claims), never the
   first.
4. **Mutation proof** — every check reddened by ≥1 mutation, and **no inert check**. A check that
   cannot fail guards nothing.
5. A step with no verdict is **not done** and is **not committed**. Record the outcome here +
   `HANDOFF.md`, and register the number in `IMPROVEMENTS.md`.
6. **The completeness gate** (`scripts/verify_plan_coverage.py`, D0.4) must stay at **0 gaps** for this
   file's status table.

## 4. Decisions (settled)

* **Order:** V1 → V2 → V3 → V4 → V5. V1/V2 are read-only and can run immediately; V3 is
  annotation-heavy and can proceed in parallel with V4's branch decision.
* **`no-separation` is allowed.** The pre-registration fixes the falsification clause before the run.
* **The config comment is corrected in V4, not before** — deciding the replacement value is V4's job,
  not a drive-by edit (§I123 records the contradiction in the meantime).
* **The lane is NOT removed and NOT re-ingested.** This plan changes the *aperture*, not the index;
  the stored ColPali vectors stay as they are.

## 5. Status table (the resume point)

| id | step | status | verifier | mutation |
|---|---|---|---|---|
| V1 | capture the full per-query score distribution | ⬜ | ⬜ | ⬜ |
| V2 | top1 / margin / z-score separation test | ⬜ | ⬜ | ⬜ |
| V3 | the REAL labelled set (figure crops + provenance) | ⬜ | ⬜ | ⬜ |
| V4 | the aperture decision (wire the statistic, or record no-separation) | ⬜ | ⬜ | ⬜ |
| V5 | rank the lane with labels (VL-L3) | ⬜ | ⬜ | ⬜ |

## 6. Open questions carried in

* **The V1 self-match question** — V2 can settle it (is the query image the stored one?).
* **Is 128-d too coarse?** §I107's neighbourhood leaves it partly open; if V2 finds no separation on
  the *stored* vectors, a wider patch dimension is a *different* lever and would need a re-embed.
* **The 33 visual queries carry no labels** — that is V3's job, and it is why the gold set is 133
  queries, not 166.
