# P1 — THE OVERVIEW RETRIEVAL-SIGNAL PROBE — pre-registration

> **Written 2026-11-04, BEFORE the run.** Per **D6.1** it is **committed ALONE**, and nothing measured is
> in it. Read first: `IMPROVEMENTS.md` **§I111** (the pool-order attribution — the ordering loss is the
> LANES' scoring, not the fusion), **§I99** (the decomposition), **§I97/T4** (the per-type rerank-query
> policy), **§I105** (the ceiling).

---

## 1. The question

§I111 established: the fused pool order **equals** the dense-only order for overview (0.2103 vs 0.2128),
the fusion is **not** the culprit, and **60.5 %** of the pooled gold sits at ranks 21–100. ⇒ **the lanes
score the gold too low.** For overview the dominant lane **is** the dense lane (nomic-768).

> **Does a different QUERY REPRESENTATION make the dense lane rank the overview gold higher?**

This is the cheap, read-only half of the "better retrieval signal" class (the expensive half is an
embedder change/re-ingest, §I85/§I87 — out of scope here).

---

## 2. What this IS, and IS NOT

| | |
|---|---|
| **IS** | a **read-only** probe against `knowledge_base_v3` (nomic-768, pooled), **40 overview queries**, holding the INDEX and the lane CONFIG fixed and varying **only the query representation** fed to the **dense lane** (`dense_64` prefetch → `dense_full` rescore, limit 500). |
| **IS** | four arms: **A** the shipped single HyDE hypothetical (baseline); **B** the raw query (a known-worse control, §I97/T4); **C** multi-hypothetical **max** over N=5; **D** multi-hypothetical **mean** over N=5. |
| **IS NOT** | a collection write, a re-ingest, an embedder change, a `src/` change, or a change to the fusion. |
| **IS NOT** | an endpoint run — it measures the **dense lane's own order** (the pool order's dominant component, §I111), not the CE's top-20. A winning arm is promoted to an endpoint run in a LATER, separately pre-registered stage. |

---

## 3. The quantities

```
arm set        {A, B, C, D}  x  40 overview queries   (dense lane, top-100 recorded)
A  single HyDE hypothetical        (the frozen §I73 cache value)
B  raw query text
C  max over the 5 hypotheticals' dense scores, per page
D  mean over the 5 hypotheticals' dense scores, per page
PRIMARY        mean rank of the gold in the dense lane's top-100   (lower is better)
PRIMARY        dense-lane R@20
secondary      dense-lane nDCG@20, Hit@20, and the gold's rank distribution
```
A delta is **RESOLVED** iff its paired 95 % CI excludes 0.

---

## 4. Predictions (fixed BEFORE the numbers exist)

1. **Anchor (not a finding):** arm A reproduces the §I111 dense-only R@20 for overview (**0.2128**) within
   the run's floor. If it does not, the instrument is not §I111's and the run is void.
2. **B is worse than A** on R@20 (§I97/T4: the hypothetical is the better overview query) — a
   **discrimination control**, not a finding.
3. **The test:** does **C** or **D** lift the gold's rank / R@20 above **A**? Three admissible outcomes:
   * **RESOLVED POSITIVE** ⇒ the query representation is a live lever; promote the winner to an endpoint
     run (separately pre-registered).
   * **UNRESOLVED** ⇒ the query side does not move it; the lever is the DOCUMENT side (embedder/re-ingest).
   * **RESOLVED NEGATIVE** ⇒ multi-hypothetical dilutes the query; recorded as such.

**Falsification clause.** If **neither C nor D** resolves positive, the **query-side** half of the
retrieval-signal class is **closed**, and the remaining lever is the **document side** (embedder /
re-ingest / fine-tune, §I85/§I87's caveat attached).

---

## 5. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | population **40** overview queries, all `ovw-*`, all with `relevant_pages`. |
| **G2** | **zero errors** in every arm. |
| **G3** | the 5 hypotheses per query are **FROZEN** in `overview_signal_hypotheses.json` (the run is deterministic given the cache; a cache miss RAISES rather than calling the LLM mid-scoring). |
| **G4** | arm A's dense lane reproduces the §I111 dense-only R@20 for overview (0.2128) within ±0.020. |
| **G5** | arm B ≠ arm A on ≥1 query (the representations actually differ). |
| **G6** | the dense lane's page list is **ordered** and length ≥ 20 in every arm (a truncated lane voids the rank metric). |
| **G7** | **determinism**: re-running arm A's scoring twice is bit-identical on every query. |

---

## 6. Bounds

* One corpus, one document (Feynman Vol. 1), one funnel. n=40. Overview label sets are broad (mean 73.8),
  so the metric ceiling is low by arithmetic (§I111 finding 4) — read every recall against it.
* ⚠️ The probe measures the **dense lane**, not the product endpoint. A dense-lane win does **not** imply
  an endpoint win (§I85's funnel absorbed base-lane gains before).
* ⚠️ N=5 hypotheticals is a choice, not a measurement; a null at N=5 does not exclude a larger N.
* **Read-only: no collection write, no re-ingest, no `src/` change.**

---

## 7. Verifier and mutation proof (every stage)

* **Independent stdlib verifier** `logs/p1/step10/overview_signal_probe_verifier.py` — re-derives **every**
  aggregate, per-arm R@20 / nDCG@20 / mean gold rank from the artifact's **raw per-query page lists**,
  without importing the harness; re-checks G1–G7.
* **Mutation proof** `logs/p1/step10/overview_signal_probe_mutation.py` — one mutation per check, generated
  from the artifact's own field inventory; **no inert check** (every check reddened by ≥ 1 mutation, each
  mutation reddens its intended check).
* Both are run by `run_overview_signal.sh` (mutation → probe → verifier), so the stage is resumable and
  re-runnable from one command.

---

## 8. Registration and what would falsify this

On completion: an `IMPROVEMENTS.md` entry (§I112 or next), the artifact
`logs/p1/step10/overview_signal_probe.json`, the hypotheses cache, the verifier and mutation proof, and
the run log. **Read-only at run time.**
