# P1 — the cross-embedder experiment (hold the corpus fixed, swap only the embedder)

> **Written 2026-10-22, session 9. FOR THE NEXT SESSION.** Read `IMPROVEMENTS.md` §I57, §I58, §I59,
> §I60, §I62 and this file's "measured facts" before writing any code. **Nothing here has been run.**
>
> **Why this exists.** §I59 measured two separate effects in the new index:
> 1. a **64d truncation penalty** 8.7× worse for Qwen3 than Nomic — *clean*, measured within each
>    index, and §I60 confirmed it with the ANN confound removed. **Resolved; not this experiment.**
> 2. a **full-dimension ranking loss** — R@20 ceiling-normalised **0.4987 → 0.2939** (−0.2026,
>    resolved), **with no truncation involved at all**.
>
> Effect 2 is the real regression, and **no instrument so far can attribute it**: the two indexes
> differ in the embedding model *and* the chunking (5,048 vs 3,796 chunks over the same PDF) *and* the
> content-filter state. **This experiment removes two of the three.**

---

## 1. The design — one variable

**Hold the corpus fixed; swap the embedder.** The new corpus (doc `7ba61432`, 3,489 in-window chunks)
is embedded **twice**: once with Qwen3 1024d (already measured — §I60's d=1024 row) and once with
Nomic 768d (this experiment). Same chunks, same pages, same queries, same ceiling, same metric code.

| arm | corpus | embedder | status |
|---|---|---|---|
| **Q** (control) | new, `7ba61432` | Qwen3 1024d | **already measured** — §I60 `d=1024`: R@20 0.2939, R@100 0.5691 (ceiling-norm, exact search) |
| **N** (treatment) | new, `7ba61432` | Nomic 768d | **this experiment** |
| R (optional) | old, `6d55c52b` | Qwen3 1024d | triangulation only; not the decision |

**Read it as:** `N` vs `Q` isolates the **embedder** on a fixed corpus.
- `N ≈ Q` → the embedder is **not** the cause; the re-chunk is, and the next lever is chunking.
- `N > Q` → **Qwen3 ranks worse on this corpus**; an embedder decision becomes defensible.
- `N < Q` → the re-chunk is the problem, not the model.

**Do NOT read a `N > Q` result as "revert to Nomic".** A revert is a re-ingest plus re-indexing
`derivative_artifacts` (73,406 pts) and `concept_embeddings` (6,065 pts) — both moved to 1024d in
§I49 — plus the intent classifier, whose width **is** `dense_dim`. That is an owner decision on a
much larger evidence base than one metric.

## 2. Metric — exact search, not Qdrant

Reuse `logs/p1/step10/mrl_dimension_sweep.py`'s machinery: embed both arms in-process, brute-force
cosine over the whole corpus, rank, dedup to pages. **Why:** §I60 showed Qdrant's filtered-HNSW path
costs up to 18.5 % of the pool, which would sit on top of the effect under test. Exact search removes
it.

- **Primary: R@20 and R@100, ceiling-normalised.** Coverage is saturated (§I60: R@1000 = 1.0000 at
  every dimension), so ranking is the only thing left to measure.
- The ceiling is **identical across arms** (same corpus), so raw and ceiling-normalised agree here —
  report both anyway, so the number stays comparable to §I57/§I59.
- Paired per query, 95 % CI on the paired difference, W/L/T. n = 133.

## 3. Pre-registered rule

Fixed **before** the run:

- **The endpoint is R@20, arm N vs arm Q, paired, ceiling-normalised.**
- **Attributable** iff the CI excludes 0. **Not attributable** iff it straddles 0 — and then the
  honest statement is *"the embedder does not explain the full-dim regression on this corpus; the
  re-chunk does"*, which is a **result**, not an unresolved one.
- **One run. No extension.** A null is a result (§G2 plan §4's disposition, applied here).
- Report R@100 as the secondary; do not switch the endpoint after seeing the numbers.

## 4. Verifiers (each must be able to FAIL)

| # | check | why it discriminates |
|---|---|---|
| **X1** | the cluster Nomic re-embed reproduces the **local** `NomicEmbedder`: cosine ≥ 0.9999 on ≥ 5 real chunks | §I62 — the cluster does **not** apply `search_document: `. Unprefixed gives cosine **0.949** and would silently invalidate the whole run |
| **X2** | arm **Q** reproduces §I60's `d=1024` row **exactly** | the same code path on the same corpus; if it drifts, the comparison is between two instruments |
| **X3** | both arms see an **identical** chunk→page mapping and identical `n_relevant` | the corpus is supposed to be fixed; assert it, don't assume it |
| **X4** | **A-vs-A negative control**: re-run arm N at a different batch size — byte-identical vectors | the only check that catches an instrument manufacturing a delta |
| **X5** | every query that errors is **reported and excluded**, never silently dropped | §I56 — the DA probe's retry wrapper swallowed its retries |

## 5. Measured facts — do not re-derive

- ⚠️ **`QDRANT_HOST` is BLANK in `.env`** → the default is the **LOCAL embedded** store. Every command
  needs `QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2` or it silently targets the wrong
  store (§I49 Finding 1). This experiment needs Qdrant only for the chunk text — read it from SQLite.
- ⚠️ **`unset PYTHONPATH`** before `uv run` — Hermes' terminal exports a PYTHONPATH that shadows the
  venv's pydantic.
- **The cluster serves Nomic**: `POST http://10.0.10.70:8123/embed-text/v1/embeddings`,
  `model="nomic-ai/nomic-embed-text-v1.5"` → 768d, 0.18 s (§I62).
- **Throughput** (§I62, real 461-char chunks): batch 128 → **121 chunks/s**; 3,489 chunks ≈ **29 s**.
  133 queries in one call = **1.78 s**. The **local CPU** Nomic is ~3 s/query → 3,489 would be ~3 h.
- **`dense_<d>` is an exact MRL slice** of the full vector (cosine 1.0000, 200 points/index, §I59).
- **k-units differ between probes** (§I60): §I59's `k` is in **PAGES**, §I60's is in **CHUNKS**. They
  are comparable only at k=1000. Do not mix them.
- **Ceiling** = `|relevant_pages ∩ reachable_pages| / |relevant_pages|`, where reachable = a page with
  ≥1 chunk, `is_content is not False`, inside `[min_content_page, max_content_page]` = `[30, 936]`
  (§I58). Reproduce it; do not inherit a stale number — §D15's "unreachable label pages 4 → 0" is
  already stale.
- **Cost: under 10 minutes wall**, no LLM calls, no writes to any collection.

## 6. Explicitly NOT in this plan

- **No revert, no re-ingest of a live collection.** Arm N is measured **in process**; if it ever needs
  a Qdrant collection it goes in a **scratch** one.
- **No 128d** — dead by §I60 (zero coverage gain; the pool is saturated at every dimension).
- **No ANN tuning** — that is §I61's separate question.
- **No chunking change** — if arm N ≈ arm Q, chunking becomes the next lever and gets **its own**
  plan.
- **No reranker, no DA lane, no graph lane** — all orthogonal, all previously measured (§I55, §I56,
  §I59).

## 7. Register, at the end

- The arm-N numbers and the paired delta against arm Q.
- Whether §I59's Effect 2 is **attributable to the embedder** — yes or no, either way recorded.
- **If `N ≈ Q`**: the finding is that the full-dim regression is a **re-chunk** effect, and the
  follow-on item is chunking (E1/E2/E3), which has never been done.
- Correct §I59's Effect-2 paragraph with the outcome.
