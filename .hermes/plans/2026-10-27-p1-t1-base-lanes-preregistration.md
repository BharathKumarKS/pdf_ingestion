# P1 — T1: the BASE-LANE ship test, re-run against the re-embedded `v3` (pre-registration)

> **Written 2026-10-27, BEFORE any number of this run exists.** It fixes what T1 measures and how its
> numbers may be read, so the result cannot be interpreted after the fact (§D1's rule). **A commit
> containing this file and nothing measured is the point of it** (§I61's precedent, D6.1).
>
> **T1 is not a new instrument.** It is Stage F's **re-registered** instrument
> (`.hermes/plans/2026-10-25-p1-stageF-product-endpoint-preregistration.md`, committed alone as
> `51de3f2`; `.hermes/plans/2026-10-25-p1-stageF-product-endpoint-reregistration.md`, committed as
> `e708784`/`a409d7d`) **re-run against the index that changed underneath it.** This file states the
> one thing that changed, adds the one guard that change requires, and adopts everything else by
> reference. Per §I67/§I71/§I72's precedent it is **committed ALONE, before the run.**
>
> Read first: `HANDOFF.md` (session 22), `IMPROVEMENTS.md` **§I90** (T0, the reference table),
> **§I89** (the pooled re-embed + the Stage G re-run), **§I88** (the pooled write), **§I85** (the
> product null this is the narrowed re-test of), **§I87** (the like-for-like base-lane contrast),
> **§I81/§I83** (v3's population and the 768d derived collections), **§I68/§I84** (the deterministic
> funnel that makes E4 a real control).

---

## 1. The question, and what T1 is for

**Does the pooled nomic index (`knowledge_base_v3`) beat the incumbent qwen3 index
(`knowledge_base_v2`) at the PRODUCT retrieval endpoint, on the same 133 gold queries — on the BASE
lanes?**

This is the plan's §D track **T1, "the narrowed ship test (Stage F re-run on the pooled v3)"**. Stage F
(§I85) asked the same question of the **late-chunked** v3 and returned a **null** at the endpoint
(P1 cR@20 **−0.001213**, CI [−0.023051, +0.020626], unresolved). Since then the index was **re-embedded
pooled** (§I88/§I89): the base-lane advantage went from *absent* to **large and resolved upstream**
(+0.104 at the 64d base; like-for-like **+0.0362**, §I87) and is **destroyed at the fusion**
(−0.019, resolved negative). T1 is the **product-endpoint** counterpart: does a large upstream advantage
move the number a user would see?

⚠️ **T1 is the SHIP TEST for the base lanes, and it is the only stage whose result can license a ship**
(nomic plan §5). It is **not** the full-funnel test — that is **T3**, which needs §A and §B.

## 2. What CHANGED since Stage F, and what did NOT

**CHANGED — one thing: the content of arm B's index.**

| | Stage F (session 20) | T1 (this run) |
|---|---|---|
| arm B's collection | `knowledge_base_v3`, **late-chunked** nomic vectors | `knowledge_base_v3`, **POOLED** nomic vectors (§I88/§I89) |
| arm B's point count | 3,796 | 3,796 (byte-identical ids; §I88) |
| arm A's collection | `knowledge_base_v2`, 3,869 | `knowledge_base_v2`, 3,869 — **untouched** |

⚠️ **Verified live before this file was written** (2026-10-27, read-only): `knowledge_base_v2` = 3,869
points (`dense_1024` 1024 + `dense_64` 64 + `colbert` 128 + `sparse`); `knowledge_base_v3` = 3,796 points
(`dense_full` 768 + `dense_64` 64 + `colbert` 128 + `sparse`); `derivative_artifacts` = 73,406 @ 768;
`concept_embeddings` = 6,065 @ 768. Qdrant `10.0.10.65:6333` and the router `10.0.10.70:8000` both
respond; the HyDE cache resolves under the registered digest.

**NOT changed — adopted by reference from Stage F's pre-registration and re-registration:**

* the **arms** (§3), the **per-arm environment** and the E1/E2 assertions;
* **HyDE ON and frozen** (§4) — served from `data/hyde_cache/`; a miss RAISES;
* the **product retrieval path** — each arm calls the product's own `evaluate_rag.run_retrieval`
  verbatim and scores with the product's own `compute_retrieval_metrics`;
* the **DA lane OFF and the GRAPH lane OFF in both arms** (re-registration §2a/§2c) — both derived
  collections are 768d, so a 1024d arm 400s and the lane is silently skipped; leaving either on is not
  a single-variable A/B. Re-verified live: both are still 768d;
* the **endpoints** (§5), the **reading rule** (§6), the **page convention** (pages of the top-k
  CHUNKS) and the **ceiling convention** (§I58's global divisor);
* the guards **E1–E8**.

## 3. The two arms (adopted verbatim from Stage F §3)

| arm | collection | `DENSE_MODEL` | `DENSE_DIM` | `DENSE_DIM_LOW` | prefixes | role |
|---|---|---|---|---|---|---|
| **A** | `knowledge_base_v2` | `Qwen/Qwen3-Embedding-0.6B` | 1024 | 64 | Qwen3's `QUERY_INSTRUCTION`, no document prefix | **control** — and the instrument check (E8, E9) |
| **B** | `knowledge_base_v3` | `nomic-ai/nomic-embed-text-v1.5` | 768 | 64 | `search_query: ` / `search_document: ` | **treatment** — the pooled index |

⚠️ The low lane's width is resolved **off the collection** (`store._resolve_low_lane`), never from
`cfg` — both collections carry `dense_64`. ⚠️ The A2 `.env` flip is **not applied**: the resolved
default is Qwen3/1024, so each arm's values are **exported and asserted** (E1/E2). A run that forgets
them silently measures Qwen3/1024 against the wrong collection — the S2/S3 trap (§I80).

## 4. HyDE — ON and FROZEN (unchanged, hard precondition)

`data/hyde_cache/18ece9b9404688c8__openai_gpt-oss-20b__ab681b8e43855a46.json` — 127 entries, model
`openai/gpt-oss-20b`, 93 used (the factual + overview queries; multihop is never Hyde-ified). The
filename and the header are both the contract and the header is re-validated on read. ⚠️ **A miss
RAISES; it never falls back to a live LLM call.**

⚠️ **Consequence: the absolute numbers ARE product-shaped** (unlike §I61/§I65/§I67, which ran HyDE off).
Quote both arms' absolutes and the paired delta.

## 5. Endpoints (adopted verbatim from Stage F §5)

| # | endpoint | role |
|---|---|---|
| **P1** | paired Δ **Recall@20 ceiling-normalised** (§I58), **B − A** | **primary** |
| **P2** | paired Δ **Recall@20 raw**, B − A | **primary**, reported beside P1; if they disagree both are stated, never averaged |
| S1 | paired Δ R@100, Hit@20, MRR, `context_precision`, NDCG@20 | secondary |
| S2 | per `query_type` (factual / multihop / overview) Δ cR@20 | secondary |
| **D1** | **arm B (pooled) − arm B (Stage F, late-chunked)** on the same metric | **diagnostic** — the treatment's size at the endpoint; reported either way |

## 6. Pre-registered reading rule

1. **Ship only on a resolved positive primary.** Arm B ships iff the paired 95 % CI on ΔcR@20 (P1)
   **excludes 0** and the point estimate is **> 0**. CI = `mean ± 1.96·SD/√n`.
2. **Unresolved is a result, not a licence** — recorded as **measured-and-unresolved**; nothing ships
   on it.
3. **Negative is recorded, not hidden.**
4. **P2 does not substitute for P1**, and P1 does not substitute for P2.
5. **§I55 fallback queries are excluded from the top-20 headline and named**; headline reported with
   and without them.
6. **Quote the size, not just the sign** — the resolution floor at n = 133 is **≈ 0.020**.
7. **No causal claim beyond these two indexes.** One corpus, one document, one day, one funnel.
8. ⚠️ **D1 is a diagnostic, not a second endpoint.** It is read as *where* the pooled re-embed landed,
   not as a verdict.
9. ⚠️ **T1 measures the BASE lanes only** (dense + sparse + colbert). It is not the full product funnel
   — DA and the graph lane are OFF (§2), RAPTOR is not in v3 and is not on this path, and the visual
   lane is unmeasurable. The full-funnel comparison is **T3** and is **unmeasured**.

## 7. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **E1** | each arm's **resolved** config names its collection and a non-blank `QDRANT_HOST`, and prints `dense_model`/`dense_dim` |
| **E2** | arm A resolves to Qwen3/1024/`knowledge_base_v2`; arm B to nomic/768/`knowledge_base_v3`; `da_enabled` is **False** in both — asserted, and recorded in the artifact |
| **E3** | **133** queries compared in every arm; errored queries counted and named |
| **E4** | **negative control: each arm run TWICE is bit-exact on every metric of every query.** Legitimate because §I68 landed (§I84) — a non-zero self-difference VOIDs the run |
| **E5** | every aggregate re-derives from the artifact's own per-query array |
| **E6** | §I55 fallbacks counted and named per arm |
| **E7** | the cut can move: each arm's pool size against the top-20 cut |
| **E8** | **arm A reproduces a REGISTERED row** — §3d's DA-off v2 retrieval row, **R@20 0.452 ± 0.020** (the n = 133 resolution floor, a pre-existing derived quantity, **not** a fit). If it does not, the harness is not the product path and the run is **VOID** |
| **E9** | ⚠️ **NEW — the treatment is isolated to arm B, and the instrument has not drifted: arm A is BIT-EXACT against Stage F's recorded arm A** (`logs/p1/step10/stageF_arm_A1.json`, session 20) on the six endpoint metrics (`recall_at_20`, `recall_at_100`, `hit_at_20`, `mrr`, `context_precision`, `ndcg_at_20`), on all 133 queries. **Only those six keys are compared** — `compute_retrieval_metrics` gained `map` / `precision_at_k` / `f1_at_k` after Stage F (§I90), so a whole-dict comparison would be an over-strict check that fails on correct data (the T0 lesson). A mismatch VOIDs the run and is diagnosed **before** any endpoint is read |

⚠️ **E4, E8 and E9 are the load-bearing guards.** E4 makes determinism an assertion rather than an
assumption; E8 makes "this is the product" a measurement rather than a claim; **E9 makes "arm A did not
move" a measurement**, which is what licenses reading P1 as the pooled index's effect rather than as
instrument drift.

## 8. Power

`n = 133` is fixed, so power is reported, not chosen: the entry states the observed `SD_d` and the `n`
required for `δ = 0.05` at that `SD_d`. **Floor ≈ 0.020** overall; **≈ 0.04 per type** (n = 40). A point
estimate below its floor is reported as such, never converted into a claim.

## 9. Verifier — one independent verifier, per stage

`logs/p1/step10/t1_verifier.py`, **stdlib only** (no numpy, no project imports, no shared helpers with
the harness), reading **only the written JSON**. It re-derives every aggregate, endpoint, CI, W/L/T and
verdict field from the **raw per-query arrays**:

| # | check |
|---|---|
| V1 | 133 scored / 0 errored rows per arm |
| V2 | each arm's mean R@20 / R@100 / Hit@20 / MRR / NDCG@20 re-derive from the per-query arrays |
| V3 | P2 (raw R@20) Δ / CI / W-L-T re-derive |
| V4 | P1 (cR@20) Δ / CI re-derive under the §I58 global divisor |
| V5 | the negative control (A1 vs A2, B1 vs B2) is bit-exact on every metric of every query |
| V6 | E8 — arm A's aggregate R@20 within ±0.020 of 0.452 |
| V7 | no silently excluded denominator (no `None` metric in a scored row) |
| V8 | the achievable-max divisor is identical across arms |
| V9 | **E9** — arm A is bit-exact against Stage F's recorded arm A on the six endpoint metrics |

⚠️ **Each check must be able to FAIL, and that is proved by mutation before the run**
(`logs/p1/step10/t1_mutation_log.txt`): every mutation must turn **exactly** its own check red. ⚠️ **A
verifier whose check cannot fail is not a verifier** (§I90's over-strict-check lesson cuts the other
way: a check that can only fail is worse than none, and a check that can only pass is not one).

⚠️ An **independent, cross-family reviewer** (`openai/gpt-oss-20b`, read-only) is dispatched on a
**compact extract** — the raw per-query array + the claims — **never the full artifact** (§I74's
lesson). Its verdict is recorded as cheap corroboration; the **substantive** evidence is the harness
guards + the stdlib verifier + the mutation proof.

## 10. Cost, and the stop rule

* **Read-only.** No writes to any collection, no re-ingest, no config change to `src/`. The only LLM
  traffic is the shared cluster embedder + cross-encoder (HyDE is served from the cache).
* **Retrieval-only, minutes**: 4 arm processes × 133 queries (measured shape, Stage F: ~150 s/arm) +
  combine. ⚠️ **Arm A runs first**; if E9/E4 fail there, arm B is not spent.
* ⚠️ **The full run (synthesis + judge) only if the retrieval endpoint RESOLVES** — ~70 min, 5,434
  judge calls. Do not spend it on an unresolved retrieval result.
* ⚠️ **Serialize against other cluster work.** The shared cluster blocked an earlier T0 attempt
  (5-query run: 2,700 s wall / 7.9 s CPU); the harness sets `socket.setdefaulttimeout(90)` and retries
  each product-path call 3×.

## 11. Preconditions (all verified before this file was committed)

1. ✅ §I68's client-side-RRF fix is **committed** (`939beae`) — the funnel is deterministic, so E4 is a
   real control.
2. ✅ `knowledge_base_v3` holds the **pooled** nomic index (3,796 points; §I88/§I89); `knowledge_base_v2`
   is untouched (3,869).
3. ✅ The HyDE cache resolves under the registered digest.
4. ✅ The per-arm environment is exported **and asserted** (E1/E2).
5. ✅ The cluster is reachable (Qdrant `10.0.10.65:6333`, router `10.0.10.70:8000`).
6. ⏳ **This file is committed ALONE, before the run.** Nothing measured is in it.

## 12. Stated — the confounds this design does NOT remove

* **The DA lane and the graph lane are OFF** (both derived collections are 768d). The run is a
  **dense + sparse + colbert** A/B — the product funnel **minus two recall lanes**. **Named, not
  hidden.**
* **RAPTOR is not in v3** (73 nodes in v2; a separate step). ⚠️ This path does not read RAPTOR at all
  (`search()` excludes `raptor_summary`), so its absence does not touch this A/B — recorded so it is
  not mis-attributed later.
* **The overview type's lane is therefore absent**, and overview is T0's worst type at the endpoint
  (coverage **0.1937**). If S2 shows an overview effect, **that absence is a candidate explanation.**
* **The intent router is not on the eval path** — the classifier's dimension does not confound the
  arms.
* **One document, one day, one funnel.** No causal claim beyond these two indexes.
