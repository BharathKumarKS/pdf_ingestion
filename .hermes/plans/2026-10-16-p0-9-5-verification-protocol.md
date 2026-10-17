# P0-9 Session 5 — human verification protocol (Task 7)

**Status:** pre-registered 2026-10-16, **before any verdict was recorded**.
**Owner:** Bharath (manual work — this is the one P0-9 task the agent cannot do).
**Deliverable:** `label error rate = X/N = Y%` recorded in `IMPROVEMENTS.md` §F4b, with the
per-stratum breakdown.

> Why this file exists: the plan's Task 7 says *measure the labeller's error rate* but does not
> fix the sample, the verdict vocabulary, or what the number will be used for. Without those
> written down first, the sample can be re-cut and the result re-read after the fact — which is
> exactly the circularity D6 was created to prevent. So: the design and its consequences are
> fixed here, then the sheet is filled in.

---

## 1. Where everything lives

| Thing | Path |
|---|---|
| The sheet you fill in | `data/gold_v2_review.md` |
| Generates it (deterministic, re-runnable) | `scripts/build_review_sheet.py` |
| Scores it (pooled + per-stratum + 95% CI) | `scripts/score_review_sheet.py` |
| Tests for both | `tests/test_review_sheet_tooling.py` |
| The PDF to open | `data/base_textbooks/feynman-lectures-on-physics-volume1.pdf` (968 pages) |

Regenerate at any time (same sample — the seeds are fixed):

```bash
uv run python scripts/build_review_sheet.py                 # 6 per stratum = 30 queries
uv run python scripts/build_review_sheet.py --per-stratum 5  # 5 per stratum = 25 queries
```

---

## 2. How many to verify — 30, and why not the plan's 25

The plan's Task 7 samples **25 uniformly at random** from all 200. That is the wrong shape here,
for a specific reason: **the five strata came from five different generation + judge paths**, so
a uniform sample can under-represent a lane and hide a lane-specific failure.

Uniform-25 would land roughly 7 factual, 5 multihop, 5 overview, 4 visual, 4 negative. The two
strata it thins are precisely the two whose labels came from **different rules**:

- **visual** — labels from the *strict* visual judge prompt (§B4c), the only lane where the
  criterion is "does the page SHOW this figure", and 6 of 40 were uncalibrated (§B4d);
- **negatives** — a three-tier generation + acceptance rule, and we *already know* one was
  invalid (`neg-nea-004`) and 6 more are flagged `needs_review`.

**Decision: 6 per stratum = 30 queries**, equal allocation. Equal rather than proportional so
nobody can argue the sample was pointed away from a weak lane, and so every lane gets the same
(namely, weak) precision — see §7 for what that precision actually buys.

| stratum | population | sampled | criterion |
|---|---|---|---|
| factual (answerable) | 53 | 6 | Is the answer on the listed page? |
| multihop (answerable) | 40 | 6 | Do the listed pages establish **both** concepts and the link? |
| overview (answerable) | 40 | 6 | Does the page **contribute to the topic's synthesis**? (not "does it answer a question") |
| visual (answerable) | 33 | 6 | Does the page **show** the described figure/table? (a different figure is WRONG) |
| negatives (must be unanswerable) | 34 | 6 | Is the book genuinely unable to answer it? Any page that does = ANSWERABLE |
| **total** | **200** | **30** | |

*If 30 is more than you want to spend, `--per-stratum 5` gives 25 — the plan's headline number,
stratified instead of uniform. Do not go below 5 per stratum: with 4 the visual and negative
lanes are decided by a single item.*

---

## 3. The ±1 window rule (do not skip this)

The stored page number carries **±1 of chunk-boundary fuzz** and the DB→PDF offset reaches +2
(§D4 — measured, and reframed as a known noise floor, not a defect). So:

> A page **counts as correct if the relevant content is on the listed page or within ±1 of it.**
> Glance at p−1 and p+1 before calling anything wrong.

Record `WRONG` only when the content is absent across that window. Otherwise you will report the
known ±1 fuzz as a labelling error and inflate the rate.

---

## 4. Verdict vocabulary (fixed)

| verdict | means | counts as an error? |
|---|---|---|
| `OK` | the checked pages support the query | no |
| `WRONG` | a **listed** page does not support the query — the label is **over-inclusive** | **yes** |
| `MISSING-PAGE` | the answer is on a page **not listed** — **write that page number in notes** | **yes** |
| `ANSWERABLE` | **negatives only** — the book *can* answer this | **yes** |

`OK` is the only pass. `MISSING-PAGE` is the one that needs a note, because it is the only
verdict that tells us *what to add* rather than what to remove.

---

## 5. How many pages to open per query

The sheet lists **at most 5 pages per query**:

- ≤5 labelled pages → all of them are listed;
- \>5 → the first, the last, and three evenly spaced (over-inclusion from a book-wide scan shows
  up at the edges of a label set). This matters: overview labels average **58** pages and reach
  **314**, so checking them all is not a real option. The sheet prints `(of N labelled)` so you
  can see what you are sampling from.

You are sampling **pages within a query**, so a single page that is plainly irrelevant is
evidence of over-inclusion — record `WRONG` and say so in notes.

---

## 6. Steps

1. **Generate the sheet** (already done; re-run only if you want the 25 variant):
   ```bash
   uv run python scripts/build_review_sheet.py
   ```
2. **Open the PDF**: `data/base_textbooks/feynman-lectures-on-physics-volume1.pdf`.
   In Preview, `⌘⌥G` opens "Go to Page" — type the page number.
3. **Work one stratum at a time**, top to bottom in `data/gold_v2_review.md`. Read the row's
   query, open the listed page(s), apply that stratum's criterion (§2) and the ±1 window (§3).
4. **Write the verdict** in the `verdict` column, and a short note whenever the verdict is not
   `OK` (for `MISSING-PAGE`, the page number you found).
5. **Negatives need a different technique** — there is no page to open. For each one:
   - search the book's index (or the app's search box) for its key terms, and
   - if a passage plainly answers it, record `ANSWERABLE` and note the page.
   Two of the six in the sheet (`neg-in_-001`, `neg-in_-002`) are already flagged
   `needs_review` in the negatives file, so expect those to be the interesting ones; the other
   four are the ones the Session 3b re-scan called clean — the sample exists to test that call.
6. **Score it**:
   ```bash
   uv run python scripts/score_review_sheet.py
   ```
   It refuses to print a rate while any row is blank — a partial sheet silently shrinks the
   denominator. It prints per-stratum and pooled rates with 95% Wilson intervals.
7. **Record it** in `IMPROVEMENTS.md` §F4b as `label error rate = X/N = Y% (95% CI …)`, with the
   per-stratum table, and apply §8's pre-registered consequence.
8. **Commit** the sheet + the §F4b entry (one commit).

---

## 7. What this sample can and cannot tell you (read before interpreting)

With **6 per stratum**, a lane with 0 errors is only bounded at **≤39%** (Wilson 95%). With
**30 pooled**, 0 errors bounds the rate at **≤11.4%**. So:

- **It cannot certify a small error rate.** 0/30 does *not* mean "the labels are ~0% wrong"; it
  means "no gross error in 30 draws, so below ~11%".
- **What it is good for:** catching a lane that is *obviously* broken (>25–40%), and putting a
  defensible number with an interval in the report instead of "we think the labels are fine".
- **The per-stratum rows are the point**, not the pooled number — the pooled rate can look
  healthy while one lane is at 3/6. Read the table, not the headline.

The scorer prints the intervals so the recorded number cannot be over-read. If you want a
tighter bound later, the lever is more queries per stratum, not more strata.

---

## 8. Pre-registered consequences (fixed before the data)

| result | consequence |
|---|---|
| pooled **≤5%** | labels usable as-is; record and move on. |
| pooled **5–15%** | usable, but every reported retrieval metric carries the caveat "labels ≈X% wrong", and no A/B delta below **2×X%** is treated as real. |
| pooled **>15%** | **stop** — repair the failing stratum (re-scan it) before P1 item 10 (ranking) depends on these labels. |
| any single stratum **>25%** | that lane's labels are **not usable**: name the lane and its failure mode in §F4b, and report that lane's numbers as "labels unreliable" until repaired. |

These thresholds are a proposal made *before* any verdict was seen — adjust them **now** if you
disagree, and note the change in §10. Changing them after seeing the table is the thing this
section exists to prevent.

---

## 9. Relationship to the other open items

- **Independent of the cluster.** This is the one P0-9 task that needs no cluster, no LLM, and no
  re-ingest — so it can run *while* Session 4b step 4 is still blocked on the outage.
- **Feeds P1 item 10.** The overview lane is the one with the bad MRR (0.191). If the overview
  stratum comes back clean, ranking work can trust those labels; if it comes back >25%, fix the
  labels first (§8).
- **Does not replace Session 5's human check of the visual lane's 6 uncalibrated queries** — that
  is a separate repair (§B4d), deferred on cluster VLM access.

---

## 10. Deviation log

| date | change | why |
|---|---|---|
| 2026-10-16 | sample is **30 (6 per stratum)** instead of the plan's **25 uniform** | the five strata came from five different judge paths; uniform-25 under-samples the visual and negative lanes, which are the two with known label uncertainty (§2) |
| 2026-10-16 | sheet lists **≤5 pages per query** rather than all labelled pages | overview labels average 58 pages and reach 314 — verifying all is infeasible (§5) |
| 2026-10-16 | **±1 window** rule added | the page numbering carries a measured ±1 fuzz (§D4); without the rule the fuzz is reported as label error (§3) |
| 2026-10-16 | scorer reports **95% Wilson intervals** and refuses partial sheets | a bare percentage at n=30 invites over-reading, and a half-filled sheet silently shrinks the denominator (§7) |
