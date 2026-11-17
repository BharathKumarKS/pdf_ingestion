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

**⚠️ The aperture is needed for BOTH query modalities — as TWO thresholds, not one.** Measured in the
product path: an image query keeps `cfg.visual_score_threshold` (0.58) while a text query passes `0.0`
and is **ungated** (`streamlit_app.py:1078-1081`; the NiceGUI visual panel does the same at
`nicegui_app.py:830`). ⚠️ **That asymmetry is a known open defect, registered as `IMPROVEMENTS.md`
§B4e (2026-10-14)** — and the reason it is two thresholds rather than one is mechanical:
`store.visual_search` divides the MaxSim sum by the **query's own patch count** to get a
mean-best-cosine, so the *scale depends on the modality*. An image is a fixed grid (~1031 patches); a
short text query yields far fewer, so its mean-best-cosine sits on a different scale and **the 0.58
image bar would drop nearly every page**. ⇒ **a single threshold cannot serve both**: it either drops
every text query or admits every image. **Each modality gets its own aperture, calibrated on its own
score distribution and validated on held-out inputs of its own modality.**

⚠️ **An ungated text path is not "safe".** A weak text description returns the top-N pages regardless
of how poor the match, so a nonsense query yields confident-looking results — the exact failure the
image aperture exists to prevent. §B4e's own framing: *"any visual-lane number is threshold-dependent,
so pin this before comparing the visual lane across configs."*

**⚠️ One inconsistency to settle in V3:** §B4e says to calibrate the text threshold *"from the 33
labelled visual queries"*, but the runbook and §I107 record that those 33 queries carry **no labels**
(which is why the gold set is 133 queries, not 166). A knee-of-the-distribution heuristic needs no
labels — but then it is a *heuristic*, not a **validated** aperture. V3 must produce labels (or the
plan must say plainly that the text threshold is heuristic-only and cannot be validated).

**What "fixed" means — the closure criterion (owner, 2026-11-05).** This workstream is **closed only
when a JUSTIFIED APERTURE exists** — not a random threshold, and **not "no aperture"**. Concretely, a
calibrated statistic (margin / z-score / a per-patch shape) whose threshold is derived from a
**calibration set** of images and then **validated on a HELD-OUT set of different images**, with:
* the separation it achieves between in-domain and near/far-domain, and
* its **false-positive rate on benign in-domain images** (the false-positive tax is the reason a
  gate needs a number), and
* an end-to-end **frontend** check: a held-out image submitted through the UI returns pages that
  actually match the image the user asked about (step V6).

**⚠️ `no-separation` on a given statistic is a REDIRECT, not a closure.** It is a legitimate
*measurement* result — and it must be recorded rather than hidden — but it does not end the plan: it
moves the search to another statistic/feature (margin, z-score, a per-patch maximum, a two-stage
read), and if the statistic space is exhausted it escalates to a **feature** change (e.g. a wider
patch dimension, which needs a re-embed) as a product decision. ⚠️ **The plan may not close by
declaring no-separation, and it may not close by shipping a threshold the evidence does not support.**
The pre-registration must fix the falsification clause for each statistic **before** its run, exactly
as the §I112 probe did — so a separating statistic cannot be manufactured after the fact.

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
| **V1** | capture the full per-query score distribution for **BOTH modalities** (image AND text; threshold 0, large limit) | read-only run | — |
| **V2** | derive top1 / margin / z-score; test whether ANY separates in/near/far — **per modality** | read-only run | V1 |
| **V3** | the REAL labelled set, **SPLIT into calibration + held-out**, with **image AND text** inputs | annotation | — |
| **V4** | derive **TWO apertures** (image, text) on the calibration set, then **validate both on the HELD-OUT set** | code + measurement | V2, V3 |
| **V5** | rank the lane with labels (`compute_retrieval_metrics`), add the visual row | measurement | V3 |
| **V6** | **frontend end-to-end: a HELD-OUT image AND a held-out text description through the UI; the returned pages must match what was asked** | acceptance | V4 |

**V1 — the score-distribution harness (read-only; do FIRST).** Store the **full top-k score list per
query** so every later statistic is re-derivable from the raw array rather than recomputed ad hoc.
⚠️ **Both modalities are captured, and captured SEPARATELY** — an uploaded figure via
`get_colpali_embedder(cfg).embed_query_image(...)` AND a typed description via `embed_query_text(...)`.
They must not be pooled: the two sit on different score scales (§B4e's patch-count normalisation), so
pooling them would hide exactly the difference the two apertures have to fit.
Acceptance: the artifact holds, per query, the ordered score list and the page ids, captured at
threshold 0 / a large limit; the number of queries matches the probe set; the run is read-only.
⚠️ **Pre-register this run and commit the pre-registration ALONE first (D6.1)** — it is a measurement.

**V2 — the statistic comparison (read-only; this is the actual answer).** Re-derive, per query:
`top1`, `margin = top1 − top2`, and `z = (top1 − μ_query) / σ_query` where μ/σ come from the query's
OWN score distribution over the corpus. Report, per statistic, whether it separates the three groups,
with the pre-registered falsification clause. **⚠️ Run the whole test PER MODALITY** — the image and
text distributions are separate populations (§B4e), so a statistic may separate for one and not the
other; a pooled test would average the two and could miss a working statistic in both. **Also settle
the V1 self-match question** — is the query image the stored one? (a cosine of exactly 1.0000 is a
self-match signature, not cross-render proof). Deliverable: artifact + **deterministic** verifier +
mutation proof.

**V3 — the real labelled set (annotation, not code), SPLIT into calibration + held-out.** ⚠️ The
current in-domain group is **synthetic matplotlib plots** — in-domain by *topic*, not by *appearance*
— while the near-domain group is also plots, so the test set **confounds the question it is meant to
answer**. Build: in-domain = figure **crops from the actual Feynman pages**; near-domain = figures from
a **different** physics book; far-domain = photos/logos/noise. **Provenance recorded per image.**
⚠️ **The set is split into two DISJOINT groups of different images: a CALIBRATION set (V4 derives the
threshold on it) and a HELD-OUT set (V4 validates on it, and V6 submits from it).** The held-out images
are never used to choose the threshold — that is what makes the validation a test rather than a fit.
Acceptance: every image names its source page/file, its group, and its split; the in-domain group is
real crops; the two splits share no image.

**V4 — the apertures (derive on calibration, VALIDATE on held-out) — TWO of them.** Derive the
statistic's threshold on the calibration set **for each modality separately**, then report what each
does on the held-out set: the separation achieved, and the **false-positive rate on benign in-domain
inputs of that modality**. Wire both into the product path — the image path keeps using
`cfg.visual_score_threshold`, and the text path stops passing a hard-coded `0.0` and gets its own
config value (`streamlit_app.py:1078-1081` and `nicegui_app.py:830` are the two call sites to change) —
with the per-check fail-open/closed posture stated. Also **correct the config comment** (§I123) so it
no longer asserts a separation the measurement contradicts, and mark §B4e resolved. ⚠️ **If NO
statistic separates for a modality, that modality's step is NOT complete** — it records the
`no-separation` finding, moves to the next statistic (a per-patch maximum, a two-stage read), and if
the statistic space is exhausted escalates to a **feature** change (a wider patch dimension → a
re-embed) as an explicit product decision. The workstream closes on **validated apertures**, not on a
finding of no-separation.

**V5 — the ranking metrics (VL-L3).** Label the visual queries / crops with their true page, score the
lane with the product's own `compute_retrieval_metrics`, and add the visual row to the same per-type
table the text lane uses. This is the only route to a real "is the visual lane performing?" number.

**V6 — the FRONTEND end-to-end check with HELD-OUT inputs, BOTH modalities (the owner's acceptance).**
Submit a **held-out image** AND a **held-out text description** through the UI — **not** inputs used to
derive or tune the aperture — and check that the pages returned **actually match what the user asked
about**. Both paths exist in both visual tabs ("Search by → Upload an image" / "Describe it":
`streamlit_app.py` admin *Visual Search* ~:1263-1286 and student *Find a Figure* ~:1165-1187, routed
through `_visual_search_and_explain(..., image_file=..., query_text=...)` → `embed_query_image` /
`embed_query_text` → `store.visual_search(score_threshold=...)`).
Acceptance, all three parts, **per modality**:
1. **correct retrieval** — the top pages returned are the pages the submitted figure / description is
   actually about (the held-out label is known, so this is checkable, not a judgement);
2. **the aperture behaves** — a held-out IN-domain input is NOT rejected, and a held-out FAR-domain
   input (noise/logo/photo, or a description of something not in the book) IS rejected; the
   false-positive rate from V4 shows up here as observed behaviour, not just as a number;
3. **the render is correct** — the returned page images render (⚠️ `data/page_images/` holds PNGs for
   the CURRENT doc only, so a hit on another doc shows "image unavailable"; state which case you hit).
⚠️ **Drive the REAL widget** (`AppTest` for Streamlit, per the `streamlit-app-development` skill) or
state plainly that you did not — a screenshot proves what rendered, not what was retrieved.

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

* **Order:** V1 → V2 → V3 → V4 → V5 → V6. V1/V2 are read-only and can run immediately; V3 is
  annotation-heavy and can proceed in parallel with V4's branch decision.
* **THE CLOSURE CRITERION (owner, 2026-11-05): a JUSTIFIED, VALIDATED aperture.** Not a random
  threshold, and **not "no aperture"**. Derived on a calibration set, validated on a **held-out set of
  different images**, and confirmed end-to-end through the **frontend** (V6).
* **`no-separation` on a statistic is a REDIRECT, not a closure** — it moves the search to another
  statistic, then to a feature change (a wider patch dim → a re-embed) as a product decision. It must
  still be *recorded* when found; it just does not end the workstream.
* **Calibration and held-out images are DISJOINT.** An aperture tuned and tested on the same images is
  a fit, not a validation.
* **BOTH modalities get an aperture, as TWO thresholds — not one.** The patch-count normalisation puts
  image and text queries on different score scales, so a single threshold either drops every text
  query or admits every image (§B4e). The current text path's hard-coded `0.0` is a known open defect,
  not a design choice to preserve.
* **The config comment is corrected in V4, not before** — deciding the replacement value is V4's job,
  not a drive-by edit (§I123 records the contradiction in the meantime), and V4 also marks §B4e
  resolved.
* **The lane is NOT removed and NOT re-ingested** — unless V4 escalates to a feature change, which is
  its own explicit decision. This plan changes the *aperture*, not the index.

## 5. Status table (the resume point)

| id | step | status | verifier | mutation |
|---|---|---|---|---|
| V1 | capture the full per-query score distribution (BOTH modalities) | ✅ **DONE 2026-11-05** — 70 rows (29 image, 41 text), read-only (index 2001 before=after), median patches image 1031 / text 37, 6/6 guards pass ⚠️ **measured on the 2,001-point index, which NO LONGER EXISTS — re-capture on the rebuilt 968 index is required (session 43)** | ✅ `logs/p1/step10/visual_aperture_v1.py` → `logs/p1/step10/visual_aperture_v1.json`; stdlib verifier `logs/p1/step10/visual_aperture_v1v2_verifier.py` **11/11 PASS**; independent reviewer `openai/gpt-oss-20b` **S1-V1..V5 CONFIRMED** (`logs/p1/step10/session39_review.json`) | ✅ `logs/p1/step10/visual_aperture_v1v2_mutation.py` **11/11 reddened, no inert** |
| V2 | top1 / margin / z-score separation test, per modality | ✅ **DONE 2026-11-05** — image: **no-separation on ALL THREE** (top1 gap −0.067, margin −0.048, z −1.95); text: `bounded_no_out_group`; self-match settled (12/12 book pages at cos 1.0) ⚠️ **measured on the 2,001-point index, which NO LONGER EXISTS — re-capture on the rebuilt 968 index is required (session 43)** | ✅ `logs/p1/step10/visual_aperture_v2.py` → `logs/p1/step10/visual_aperture_v2.json`; stdlib verifier `logs/p1/step10/visual_aperture_v1v2_verifier.py` **11/11 PASS**; independent reviewer `openai/gpt-oss-20b` (`logs/p1/step10/session39_review.json`) | ✅ `logs/p1/step10/visual_aperture_v1v2_mutation.py` **11/11 reddened, no inert** |
| V3 | the REAL labelled set, split calibration + held-out, image + text | ✅ **DONE 2026-11-16** — 36 Feynman figure crops + 12 CK-12 near-domain + 9 far-domain + 33 texts; disjoint cal/held-out (29/28) | ✅ `logs/p1/step10/visual_aperture_v3_set.py` → `logs/p1/step10/visual_aperture_v3_set.json`; `--verify-only` **6/6**; independent reviewer `openai/gpt-oss-20b` (`deleg_b7a97997`) **C1..C7 CONFIRMED** | ✅ `logs/p1/step10/visual_aperture_v3_mutation.py` **6/6 reddened, no inert** |
| V4 | derive TWO apertures (image, text) on calibration, validate on held-out | ⬜ | ⬜ | ⬜ |
| V5 | rank the lane with labels (VL-L3) | ⬜ | ⬜ | ⬜ |
| V6 | frontend end-to-end with HELD-OUT inputs, both modalities | ⬜ | ⬜ | ⬜ |

## 6. Open questions carried in

* **The V1 self-match question** — V2 can settle it (is the query image the stored one?).
* **Is 128-d too coarse?** §I107's neighbourhood leaves it partly open; if V2 finds no separation on
  the *stored* vectors, a wider patch dimension is a *different* lever and would need a re-embed.
* **The 33 visual queries carry no labels** — that is V3's job, and it is why the gold set is 133
  queries, not 166.
