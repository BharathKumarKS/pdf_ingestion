# P1 — RE-REGISTRATION: §I72 (the cross-encoder survival test), after the first run went VOID on S1

> **Written 2026-10-24 (session 15), AFTER the first run, BEFORE the second.** Precedent: §I67's
> E4 → E4′ and §I71's C2 → C2′. A guard is **restated by measurement**, never relaxed. The original
> pre-registration
> (`.hermes/plans/2026-10-24-p1-cross-encoder-survival-preregistration.md`) is **NOT edited** — its
> own terms make that void the run. The VOID artifact is preserved as
> `logs/p1/step10/ce_survival_firstrun_VOID.json` (sha256 `0947bc0d6c541b52f…`).

---

## §1 — WHAT HAPPENED

The first run completed; **7 of 8 guards passed and S1 failed**:

| guard | registered | measured | verdict |
|---|---|---|---|
| **S0** | the resolved config is the one the spec names | collection, rerank URL, model, `fetch_k=100`, `top_k=20` | ✅ |
| **S1** | PRE reproduces §I70's rows EXACTLY | qwen3@1024 **0.274348** (want 0.293934); gemma@768 **0.458665** (want 0.480410) | ❌ **FAIL** |
| **S2** | the reranker is live and reordering | **266 of 266** lists changed order | ✅ |
| **S3** | the same list reranked twice is identical | **10/10** identical | ✅ |
| **S4** | failures counted and reported | **0** failures; no unrecorded arm | ✅ |
| **S5** | A-vs-A gemma re-embed bit-identical | `max_abs_diff 0.0`, 0 rows differing | ✅ |
| **S6** | one shared page map; ceiling 888; docs in cosine order | all aligned; sha256 recorded | ✅ |

The endpoint the run produced, under a **consistent** convention (both sides identical):

| stage | qwen3@1024 | gemma@768 | Δ (gemma − qwen3) | CI | verdict |
|---|---|---|---|---|---|
| PRE (cosine order) | 0.274348 | 0.458665 | **+0.184317** | [+0.130809, +0.237824] | RESOLVED |
| POST (cross-encoder) | 0.363144 | 0.460703 | **+0.097559** | [+0.056072, +0.139045] | RESOLVED |

**survival ratio = 0.5293.** ⚠️ **But the run is VOID and these numbers are NOT registered**: S1 is
the guard that licenses attributing anything to the treatment, and it failed.

## §2 — THE DIAGNOSIS: S1 ENCODED A CROSS-CONVENTION COMPARISON (a pre-registration error)

Two different page-level recall conventions are in play, and the pre-registration used one in its §2
and the other in its §4:

* **§I70's screen convention — "top-k PAGES".** `rank_pages(sims, pages, len(pages))` ranks *every*
  chunk, dedupes to pages, and takes the first `k` **pages**. This is what produced the register's
  rows (0.293934 / 0.480410).
* **The PRODUCT's convention — "pages of the top-k CHUNKS".** `scripts/evaluate_rag.py:333-341`
  iterates the **reranked top-k chunks** and counts each distinct page on its first occurrence. This
  is what the deployed eval computes.

The pre-registration's §2 described the product's convention (correctly — it is the product-faithful
one, and the only one available for the POST arm, since the cross-encoder returns chunks, not a full
page ranking). Its §4 then required PRE to reproduce **§I70's** rows, which are in the *other*
convention. **The two are not the same number**, and the measured gap is consistent across both
embedders: **−0.0196** (qwen3) and **−0.0217** (gemma).

⚠️ **This is the session's third instance of the same class** (§I71's F1, §I70's F2, now this): a
figure carried into a context it was not measured in — here, a *metric convention*, not a count. The
tell was available before the run: the two conventions are stated in different files, and the
pre-registration asserted a reproduction across them without ever saying which one the endpoint uses.

## §3 — WHAT IS RE-REGISTERED, AND WHAT IS NOT

**NOT changed — the question, the arms, the stage, the endpoint's shape, the rule.** The contrast was
and remains: the same 100 candidates per query, ordered by cosine under each embedder, pushed through
the live cross-encoder; paired ceiling-normalised R@20, gemma − qwen3; **SURVIVES iff the POST delta
is > 0 with a CI excluding 0**. One run, one contrast, no grid.

**Restated (S1′), justified by §2 — not a relaxation:**

| # | check |
|---|---|
| **S1′** | The harness computes **both** conventions and reports both. **S1′(a):** the PRE arm under **§I70's convention** (top-20 *pages* from the full deduped ranking) reproduces **0.293934** (qwen3@1024) and **0.480410** (gemma@768) **exactly** — that is what pins the instrument to the register. **S1′(b):** the PRE and POST arms of the *contrast* both use the **product's convention** (pages of the top-k chunks, `evaluate_rag.py:333`), asserted to be the same convention on both sides. The two conventions are reported side by side forever after, and the artifact names which one each row is in. |

⚠️ **Why this is a restatement and not a relaxation:** S1 as written could not pass. The treatment
definition (a cosine-ordered pool, the live cross-encoder) was faithful throughout; only the *metric
convention the guard compared against* was wrong. S1′(a) keeps the original guard's whole purpose —
proving this harness is §I70's instrument — and S1′(b) adds the assertion the original was missing:
that the two sides of the contrast are in the **same** convention.

## §4 — THE FIRST RUN'S NUMBERS, AND WHAT THEY ALREADY SUGGEST

⚠️ **Not registered** (S1 voided the run) — recorded here only so the second run can be compared
against it, and because the *shape* is unlikely to change: the first run shows the cross-encoder
**halving** the gap (ratio 0.5293), and it does so by lifting the **weaker** embedder far more
(qwen3 +0.0888) than the stronger (gemma +0.0020). A compression, not a reversal. The second run
re-measures it under S1′; if it disagrees, the second run is the one that counts.

## §5 — DISPOSITION OF THE FIRST RUN

**VOID**, artifact preserved. Its numbers are not registered and must not be quoted.
