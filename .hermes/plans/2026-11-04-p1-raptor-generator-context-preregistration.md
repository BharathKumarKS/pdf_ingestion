# P1 — RAPTOR AS GENERATOR CONTEXT (overview) — pre-registration

> **Written 2026-11-04, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing measured is
> in it. Read first: `IMPROVEMENTS.md` **§I98** (the RAPTOR lane as a *ranked* participant is a resolved
> harm on overview), **§I89** finding 3 (the RAPTOR lane is absent from the eval path), **§I108** (the
> generator baseline), **§I111** (the ordering attribution).

---

## 1. The question

**RAPTOR is the one lane built for overview** — 3-level hierarchical cluster summaries, LLM-written,
chapter-scale prose. Two facts today: `evaluate_rag.py` **never calls `search_raptor`** (so it is absent
from every number in the register), and as a **ranked** lane it **hurts** overview (§I98, −0.0383 nDCG)
because a summary has **no `page_number`** and can only **displace** a real page from the top-20.

> **If the RAPTOR summaries are given to the GENERATOR as extra context — never entering the ranked list
> — does overview's FAITHFULNESS improve?**

This is the restated **(c)**: RAPTOR as **generator context**, not as a ranked lane. It cannot hurt the
retrieval metrics (it never enters the ranked list); it is measured where overview is weakest.

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **run** on the 40 overview queries: the product's own `run_retrieval` produces the ranked list; the SAME list is synthesised twice — once plain, once with the top-2 RAPTOR summaries appended to the prompt — and both are scored by the same cross-family judge. |
| **IS** | two arms: **A** the CE top-20 pages only (**reused from `v3_judged_full`, k=20** — no re-run); **B** the same pages **plus the top-2 RAPTOR summaries** appended to the synthesis prompt as an extra `[Summary]` block. |
| **IS** | a **generator** measurement: **faithfulness** (primary), answer_relevance, citation_accuracy. |
| **IS NOT** | a change to the ranked list, the fusion, the CE, the cut, or any collection. The retrieval metrics are **identical by construction** between arms (G4 asserts it). |
| **IS NOT** | a re-run of arm A — the §I108 baseline IS arm A, so the comparison is paired against a recorded artifact. |

---

## 3. The quantities

```
arm set        {A, B}  x  40 overview queries
A  CE top-20 pages only          (reused: v3_judged_full, k=20)
B  CE top-20 pages + top-2 RAPTOR summaries in the prompt
PRIMARY        paired Δ faithfulness        (B − A), 95 % CI, per query
secondary      paired Δ answer_relevance, Δ citation_accuracy
mechanism      summaries attached per query, summary lengths, prompt token delta
```
A delta is **RESOLVED** iff its paired 95 % CI excludes 0.

---

## 4. Predictions (fixed BEFORE the numbers exist)

1. **Anchor (not a finding):** arm A reproduces `v3_judged_full`'s overview faithfulness (**0.5097**,
   n=40) — the reuse is exact, so this is a load-bearing guard, not a prediction.
2. **Liveness:** the RAPTOR lane returns ≥ 1 summary on a majority of overview queries. If it returns
   nothing, the run is void (the lane is absent again — §I89).
3. **The test:** overview **faithfulness**, three admissible outcomes:
   * **RESOLVED POSITIVE** ⇒ RAPTOR-as-context is a live lever; promote to a product change (a separately
     pre-registered stage).
   * **UNRESOLVED** ⇒ the summaries neither help nor hurt grounding.
   * **RESOLVED NEGATIVE** ⇒ the summaries distract the generator (a long-context dilution, as in §I110).

**Falsification clause.** If faithfulness does not resolve positive, **the RAPTOR lane is closed in both
placements** — as a ranked participant (§I98) and as generator context (this run) — and its remaining
value is as a *human-facing* summary, not a retrieval or generation lever.

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population **40** overview queries, all `ovw-*`, all with `relevant_pages`. |
| **G2** | **zero errors**; **zero reranker fallbacks** (§I55). |
| **G3** | the CE top-20 page list is **IDENTICAL between arms** on every query — the ranked list is untouched (the whole point). |
| **G4** | the RAPTOR summaries attached in arm B are **not** page-bearing candidates: every attached summary has **no `page_number`** and is absent from the arm's page list. |
| **G5** | the judge is **cross-family** (generator `openai/gpt-oss-20b`, judge `Qwen/Qwen3-VL-8B-Instruct`) — a same-family judge is not a verdict. |
| **G6** | arm A's faithfulness reproduces the §I108 baseline (0.5097) — the reuse is exact. |
| **G7** | **determinism of the attachment**: the summaries attached per query are identical across two reps of the retrieval step (the synthesis itself samples; the ATTACHMENT must not). |

---

## 6. Bounds

* One corpus, one document, one funnel. n=40. ⚠️ **The generator SAMPLES** — cited pages vary run to run
  (measured §NG-P2); the paired comparison controls for this only by pairing the same queries.
* ⚠️ **The judge is a single cross-family model on a single run** — no independent verifier is applied to
  a judge SCORE (§I108's own caveat).
* ⚠️ **Confound, stated:** arm B's prompt is longer, so a rise is "more context helped grounding", not
  proof that the summaries specifically did. A **length-matched control** (appending 2 random non-summary
  passages) is NOT in this run; if B resolves positive, that control is the next pre-registered stage.
* **Read-only: no collection write, no re-ingest, no `src/` change.**

---

## 7. Verifier and mutation proof (every stage)

* **Independent stdlib verifier** `logs/p1/step10/raptor_context_verifier.py` — re-derives every paired
  delta, CI and verdict from the artifact's **raw per-query scores**, without importing the harness;
  re-checks G1–G7.
* **Mutation proof** `logs/p1/step10/raptor_context_mutation.py` — one mutation per check from the
  artifact's own field inventory; **no inert check**.
* Both run by `run_raptor_context.sh` (mutation → run → verifier).

---

## 8. Registration and what would falsify this

On completion: an `IMPROVEMENTS.md` entry, the artifact `logs/p1/step10/raptor_context.json`, the run log,
the verifier and mutation proof. **Read-only at run time.**
