# P1 — RE-REGISTRATION: §I71 arm 1 (the content filter), after the first run went VOID

> **Written 2026-10-24 (session 15), AFTER the first run, BEFORE the second.** Precedent: §I67's
> E4 → E4′ re-registration — a guard is **restated by measurement**, never relaxed. The original
> pre-registration (`.hermes/plans/2026-10-24-p1-chunking-filter-ab-preregistration.md`, commit
> `aa4b55b`) is **NOT edited** — editing it after the run started would void the run by its own
> terms. The VOID artifact is preserved as
> `logs/p1/step10/chunk_filter_ab_firstrun_VOID.json` (sha256 `0b25fd3467d68c82…`).

---

## §1 — WHAT HAPPENED

The first run of `logs/p1/step10/chunk_filter_ab.py` completed and **failed three of its guards**:

| guard | registered | measured | verdict |
|---|---|---|---|
| **C1** | arm C reproduces §I70's qwen3@1024 row exactly | R@20 0.293934 · R@100 0.569074 · R@500 0.922982 · R@1000 1.0 | ✅ **PASS** |
| **C2** | treatment pool == C − flagged; flagged == **263**; bands 72 / 186 / 5 | flagged **19**; bands **19 / 0 / 0** | ❌ FAIL |
| **C3** | A-vs-A: arm C byte-identical on a re-embed | vectors **bit-identical** (`max_abs_diff 0.0`, 0 rows differing) but **266 metric mismatches** | ❌ FAIL |
| **C4** | treatment built from the TEXT, not the stored column — 263, not 5 | in-pool **19**; stored `False` **5** | ❌ FAIL |
| **C5** | empty-ceiling queries reported, never dropped | 0 empty ceilings, 133/133 in both arms | ✅ PASS |
| **C6** | one shared chunk→page mapping | sha256 of one `pages` array | ✅ PASS |
| **X1** | pool pages == §I58 `reachable_pages()` | **888 == 888**, pool-only 0, sqlite-only 0 | ✅ PASS |
| **X2** | the resolved config names the remote store | `10.0.10.65` / `knowledge_base_v2` | ✅ PASS |

**Two of the three failures are PRE-REGISTRATION PREMISE ERRORS, one is a harness bug.**

## §2 — THE PREMISE ERRORS (measured, not inferred)

**F1's "263 (6.9 %)" is the WHOLE-CORPUS count, not the pool's.** The arm's pool is the **content
window** — `min_content_page 30` / `max_content_page 936`, which is what `store.py`'s retrieval
filter applies. Measured over the collection's 3,796 chunks:

| band | chunks | pages | in window? |
|---|---|---|---|
| TOC | 72 | **22–34** | only **19** are in-window (pages 30–34) |
| index | 186 | **937–968** | **none** — entirely above the window's 936 |
| front matter | 5 | **2–14** | **none** — entirely below the window's 30 |
| **total** | **263** | | **19 in-window, 244 out** |

So the treatment is **19 chunks, not 263** — the window bounds already exclude **93 %** of what the
filter would have removed. The pre-registration measured 263 over the corpus and then wrote it into
a guard about a window-filtered pool: a **category error**, and it is the reason C2/C4 failed.

⚠️ **This is the arm's headline, not a nuisance.** §I39's premise ("the new corpus's retrieval index
still carries its TOC/index chunks as content") is true of the **corpus** and false of the **base
lane**: the lane is window-bounded, so the filter's marginal reach there is 19 chunks. The 5,100
junk *cards* §I39 measured come from the **card generator**, which does **not** apply the window.

**F2's "pages with chunks 933" is wrong.** §I70's own artifact records `reachable_pages: 888`, and
this run reproduces **888** from both directions (the Qdrant pool's distinct pages, and §I58's
`reachable_pages()` over SQLite) — guard **X1**, which is why it is a guard and not a note.

## §3 — WHAT IS RE-REGISTERED, AND WHAT IS NOT

**NOT changed — the arm, the endpoint, the rule, the primary embedder.** The pre-registration's
*treatment definition* was faithful throughout: **T = C minus every chunk the CURRENT filter
rejects**. Only its registered *size* and the control's *denominator* were wrong. So:

* endpoint: **paired, ceiling-normalised R@20, arm T − arm C, n = 133, under gemma@768**;
* rule: **attributable iff the 95 % CI excludes 0**, otherwise the honest statement is a RESULT of
  no movement;
* secondary qwen3@1024; **ONE run; no arm added after seeing numbers**.

**Restated (C2′ / C4′), justified by the measurement in §2 — not a relaxation:**

| # | check |
|---|---|
| **C2′** | the treatment pool is **exactly** `C` minus the flagged chunks; the **IN-POOL** flagged set is **19** (band: 19 TOC); the **WHOLE-CORPUS** flagged set is **263** = 72 TOC / 186 index / 5 front matter, of which **244 are out of window**; the pool is 3,489 (§I70). |
| **C4′** | the treatment was built from the **TEXT**, not the stored `is_content`: in-pool flagged **19** ≠ stored `False` **5**, and the corpus count **263** reproduces §I39. |
| **X1** | (extra) the pool's page coverage **==** §I58's `reachable_pages()` **== 888** (§I70's own artifact). |

## §4 — THE HARNESS BUG (C3)

The A-vs-A control reported **266 metric mismatches on bit-identical vectors** — impossible, and the
tell that the *check* was wrong, not the endpoint. Cause: the control arm was scored against the raw
reachable set (`reach_C`, 888 pages) while arm C itself is scored against **its own per-query
ceiling** (`relevant ∩ reach_C`). A control compared under a different denominator is not a control.
Fixed in the harness; the vector half of the guard (**C3(a)**, `max_abs_diff 0.0`, 0 rows differing)
passed on the first run and is unchanged.

⚠️ Recorded so the next reader does not read the fix as a relaxation: **C3 was a check that could
only fail**, and it was caught by exactly that shape (identical inputs, different verdicts).

## §5 — DISPOSITION OF THE FIRST RUN

**VOID**, and the artifact is preserved as evidence (`chunk_filter_ab_firstrun_VOID.json`). Its
*numbers* are not registered: C1/C5/C6/X1/X2 passed, but the run cannot certify an endpoint whose
registered guard set it failed. The second run re-runs the **same arm** under **C2′/C4′/C3-fixed**.
