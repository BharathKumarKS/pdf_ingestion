# P1 — PRE-REGISTRATION: does the embedder's base-lane ranking gain SURVIVE the cross-encoder?

> **Written 2026-10-24 (session 15), BEFORE the harness exists and before any number is seen.**
> ⚠️ **Not committed** — the owner has not authorised a commit this session. The discipline the
> commit exists to serve (freeze the spec before seeing numbers) is honoured by writing this first
> and not editing it after the run starts: **if any number in this file is edited once the run has
> begun, the run is void.**
>
> Read first: `IMPROVEMENTS.md` §I70 (the embedder screen and its instrument), §I66 (the stage
> decomposition this is one stage of), §I65/§I67 (two cases where a measured ceiling did not become
> recall), §I55 (the reranker's silent-failure class), §I58 (the ceiling rule).

---

## §0 — WHY THIS, AND WHY NOW

§I70 screened the candidate embedders on an **oracle** and found `google/embeddinggemma-300m` @768
the only arm that passes the pre-registered rule: **+0.186476** ceiling-normalised R@20 over the
incumbent `Qwen/Qwen3-Embedding-0.6B` @1024 (CI [+0.133280, +0.239672]) and **+0.046480** over
`nomic-ai/nomic-embed-text-v1.5` @768 (CI [+0.016960, +0.076000]).

That is a **base-lane** (dense ranking) result. The product path runs four more stages after it, and
§I66 measured what each costs:

| stage | current system (ceiling-normalised R@20) |
|---|---|
| 64d lane | 0.8151 |
| → after the full-dim re-score cut | 0.7478 |
| → after the fusion (RRF + dedup + MMR) | 0.6048 |
| → after the cross-encoder to top-20 | **0.4318** |

**The cross-encoder is the single largest loss in the funnel (−0.173).** And this project has three
consecutive precedents of a measured retrieval-side gain that did not become recall: §I65 (the
prefetch lever — null), §I66 (the loss is the fusion's output width), §I67 (raising the fusion width
*and* the re-score cut — both nulls, at ample power).

So the largest unmeasured risk in adopting gemma is: **the cross-encoder re-orders both embedders'
candidate pools toward the same answer, and the base-lane gain is eaten before it can reach the
product.** That is cheap to test, and it is testable **without a re-ingest** — the question is
whether the *ranking signal* survives a stage, not what the index stores.

## §1 — THE QUESTION, IN ONE LINE

Given the same 100 candidates per query, ordered by cosine under two different embedders, does the
cross-encoder preserve the ranking advantage of the better embedder?

## §2 — THE DESIGN

Instrument: §I70's corpus and pool, unchanged, so the pre-rerank numbers are **exactly** §I70's.

* **Corpus**: new doc `7ba61432`, the **shipped pool** (§I70's arm C — `is_content is not False`,
  pages in `[30, 936]`): **3,489** chunks. ⚠️ The §I39 content filter is **not** applied: §I71
  measured it a null on this lane (Δ −0.0063, unresolved, structurally capped at 19 chunks), so the
  shipped pool is the correct control.
* **Queries**: the same **133** (`gold-*` / `ovw-*` with `relevant_pages`), sorted by id.
* **Embedders**: `qwen3@1024` — the **stored** `dense_1024` vectors (free); `gemma@768` — embedded
  from the chunk text through the cluster with its asymmetric prefixes
  (`title: none | text: ` / `task: search result | query: `), exactly as §I70 does.
* **HyDE OFF** — raw query vectors. §I70's and §I71's runs are HyDE-off, and the cache that would
  freeze HyDE for a product run is being built in parallel and is deliberately **not** used here.
* **Ordering**: exact cosine over the whole pool (no ANN), as in §I70.
* **Candidates**: the top **F = 100** chunks by cosine (`cfg.reranker_fetch_k` = 100 — the product's
  own pool width, not a chosen constant).
* **The stage under test**: the live cluster cross-encoder (`cfg.sv_rerank_url`, model
  `BAAI/bge-reranker-v2-m3`), called exactly as `src/pdf_ingestion/reranker.py` calls it
  (`{"model", "query", "documents", "top_k"}`), with `top_k = 20` (`cfg.reranker_top_k`) and the
  **raw query text** as the rerank query (HyDE off).
* **Metric**: page-deduped **ceiling-normalised R@20** (§I58) — the pages of the top-20 **chunks**,
  against the reachable set (a page with ≥1 chunk in the pool): **888** pages, the same figure
  §I70 and §I71 both measured.

Two readings per query per embedder: **PRE** (the cosine order — must reproduce §I70) and **POST**
(the cross-encoder's order).

## §3 — PRE-REGISTERED ENDPOINT AND RULE

* **Primary endpoint: paired, ceiling-normalised R@20 POST-rerank, `gemma@768 − qwen3@1024`, n = 133.**
* **Reported alongside, always:** the **PRE**-rerank delta (which must reproduce §I70's +0.186476
  exactly — guard S1), the **survival ratio** = post-delta / pre-delta, the post-rerank R@20 for
  each embedder, the pre-rerank R@20 for each embedder, and the number of failed rerank calls.
* **The pre-registered rule — the bet survives iff the POST delta is positive with a 95 % CI
  excluding 0.**
  * **SURVIVES** ⇒ the base-lane ranking signal reaches the product's last retrieval stage, and the
    next step is the scratch-index product-endpoint run (the plan's §3), not a ship.
  * **DOES NOT SURVIVE** (post delta unresolved or ≤ 0, while pre was +0.186476) ⇒ **the
    cross-encoder ate the gain**, and the gemma re-ingest is **not** justified on this evidence.
    That is a RESULT, recorded as such, and it redirects the lever to the stages §I66 fingers
    (the fusion's 100-slot output) or to the plan's §4 domain fine-tune.
* **ONE run. One contrast. No grid, no arm added after seeing numbers.**
* ⚠️ **Power.** n = 133, resolution floor ≈ **0.020** at SD_d ≈ 0.115 (§0 of the plan). The pre
  delta is ~9× that floor, so the instrument can see the effect if it survives. A *post* delta that
  lands below ~0.02 is reported as below the floor, not as a null-with-a-sign.

## §4 — GUARDS (each must be able to FAIL)

| # | check |
|---|---|
| **S1** | **PRE-rerank reproduces §I70's rows EXACTLY** — `qwen3@1024` R@20 **0.293934** and `gemma@768` R@20 **0.480410**, both ceiling-normalised on this pool. If the pre-arm does not reproduce, the harness is not §I70's instrument and the POST numbers are unattributable. |
| **S2** | the rerank service is **live and reordering**: for a real query the returned order differs from the input order on at least one pair, and the scores are not all equal. |
| **S3** | **negative control** — the SAME candidate list reranked TWICE returns the identical order (a nondeterministic reranker would make the whole contrast a tolerance, §I68's class). |
| **S4** | every failed rerank call is **counted and reported**, with the affected query ids, and the paired delta states its n. Never silently dropped (§I55's class — the reranker rejects on content token density, measured at 1/133). |
| **S5** | **A-vs-A**: gemma re-embedded at a different batch size is **bit-identical** (`max_abs_diff == 0.0`). |
| **S6** | one shared chunk→page mapping; the ceiling is 888; and the `documents` list sent to the reranker is the candidate texts **in cosine rank order**, asserted by re-locating each document's index in the pool. |

## §5 — WHAT THIS DOES **NOT** TEST

* **It is not the product endpoint.** It applies the cross-encoder to a **cosine-ordered** pool. The
  product applies it to a pool that has been through Qdrant's RRF fusion, page dedup and MMR — and
  §I68 measured that fusion to be **nondeterministic server-side**, which is why it is excluded
  here rather than simulated. So this is a **stage diagnostic** (§I66's method), not a system
  comparison.
* **It does not touch** the SPLADE lane, the DA/card lane, the graph lane (Memgraph is down), RAPTOR,
  the ColPali visual lane, the intent router, or the generator.
* **It does not measure late chunking.** The incumbent's stored vectors were produced with it; the
  gemma arm embeds raw chunk text without it. §I70 carried the same asymmetry, and it is
  **conservative for the candidate** — gemma beat a late-chunked incumbent without late chunking.
* **A SURVIVES verdict does not license a ship.** It licenses the next step (the scratch-index
  product-endpoint run) — §I65 is the standing caution.

## §6 — COST

No LLM calls, **no writes** to any collection. 133 queries × 2 embedders = **266 rerank calls**
(100 documents ≈ 45 KB each), plus one gemma re-embed of 3,489 chunks (measured at 66–1,074 s across
§I70's three runs, `meta.embed_seconds` records which) and one payload scroll (~13 s). **~15 min
wall**, dominated by the rerank calls.

## §7 — ARTEFACTS

* `logs/p1/step10/ce_survival.py` — the harness (extends §I71's `chunk_filter_ab.py`; the pool
  reader, the metric and the paired CI are copied verbatim so S1 can be an exact reproduction).
* `logs/p1/step10/ce_survival.json` — meta, verifiers, per-query PRE/POST rows, the endpoints.
* `logs/p1/step10/ce_survival_verifier.py` — an **independently written** stdlib aggregation over
  the raw per-query array, with `--check` (the §I70/§I71 pattern).
* The register entry (`IMPROVEMENTS.md` §I72) and the `HANDOFF.md` block.

**Verifier dispatched with the run, not after** (§I70/§I71's rule). `openai/gpt-oss-20b`, read-only
(`read_file` / `search_files` only — this machine's shell returns empty stdout with exit 0).
