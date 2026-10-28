# P1 — the FUSION ATTRIBUTION: which part of `RRF → dedup → MMR` eats the pages (pre-registration)

> **Written 2026-10-27, BEFORE any number of this run exists.** It fixes what the attribution measures
> and how its numbers may be read (§D1's rule). **A commit containing this file and nothing measured is
> the point of it** (§I61's precedent, D6.1).
>
> This is the plan's **§E1a** ("does MMR hurt at all?") and **§E3** ("fusion width — the pool-level
> curve was never measured") in one run. Read first: `HANDOFF.md` (session 22), `IMPROVEMENTS.md`
> **§I90** (T0 — the table this anchors on), **§I89** (the fusion is the binding constraint; MMR named
> as the *leading suspect*), **§I66** (the fusion output is the binding constraint; the 100-slot cap),
> **§I67** (the width A/B at the ENDPOINT — a null, and the reason the pool curve is the missing half),
> **§I65** (a pool gain is not a recall gain), **§E1** of
> `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md`.

---

## 1. The question

**T0 (§I90) measured the funnel's two big losses: the fusion (−0.1537 coverage) and the cross-encoder
(−0.2292).** The fusion does three things in sequence — **RRF merge → page dedup → MMR** — and the split
between them has **never been attributed** (§I66 left it open; §I89 names **MMR** as the leading
suspect). **Which component is responsible for the pages the fusion drops?**

## 2. What the CODE says, read before the design (not inferred)

`store.search_with_das` (`store.py:848-918`), verbatim:

1. `dense_hits = self.search(qv, limit=pool)` where **`pool = cfg.mmr_candidates`** — the fused
   (dense + sparse + colbert, RRF) list, **capped at `mmr_candidates`**.
2. **DA lane**: resolved parent chunks not already present are **appended** (so `len(dense_hits)` can
   exceed the cap).
3. **Page dedup**: keep only the highest-scoring chunk per page.
4. `if cfg.mmr_enabled and len(deduped) > fetch_k: candidates = _mmr_select(deduped, top_k=fetch_k)`
   **`else: candidates = deduped[:fetch_k]`** — where **`fetch_k = cfg.reranker_fetch_k`**.

**Two structural facts follow, and they are what make the experiment decidable:**

* ⚠️ **MMR can only fire when `len(deduped) > reranker_fetch_k`.** T0 measured the product pool at
  **86.47 pages on average** — *below* 100. ⇒ at the shipped configuration **MMR is a no-op on most
  queries**, and §I89's "leading suspect" is **predictable to be false**. This run tests that
  prediction; it does not assume it.
* ⚠️ **Page dedup cannot lower page-level coverage.** It removes duplicate *chunks*, not pages — every
  page it removes a chunk from is still present via its best chunk. It can only **free slots** for the
  cap. ⇒ **the loss must come from a CAP**, and there are two: `mmr_candidates` (step 1) and
  `reranker_fetch_k` (step 4).
* ⚠️ **Raising `mmr_candidates` alone cannot widen the pool** — step 4 re-caps at `reranker_fetch_k`.
  This is §I66's "raising either alone does NOT widen the fusion", now read off the code. **Both must
  move together**, which is why this run's width arm moves both.

## 3. Arms (one index — `knowledge_base_v3` / nomic-768 — the product's lane set)

**DA ON and the graph lane ON**, matching **T0** exactly, so arm C can anchor on T0's fusion row. HyDE
ON and frozen. Read-only: no writes, no re-ingest, no `src/` change. All variation is by **config flag**
— the product's own knobs — never by re-implementing the funnel.

| arm | `MMR_ENABLED` | `MMR_CANDIDATES` | `RERANKER_FETCH_K` | what it isolates |
|---|---|---|---|---|
| **C** | true | 100 | 100 | **the product as shipped** — the anchor (G1) |
| **C_nommr** | **false** | 100 | 100 | **MMR's own contribution**, at the shipped width |
| **W500** | true | **500** | **500** | **the CAP's contribution** (§I66's binding constraint) |
| **W500_nommr** | false | 500 | 500 | the cap with MMR removed — the interaction |
| **D100** | — | — | — | **the DENSE lane alone through Qdrant at limit=100**, using **the same query vector arm C's fusion used**: separates "the cap" from "fusing three lanes" |
| **D100_raw** | — | — | — | the same dense-only call at limit=100 with the **RAW** query vector (no HyDE) |
| **D500_raw** | — | — | — | the same dense-only call at **limit=500**, raw vector — **a live re-derivation of T0's boundary 5** (G2b) |

⚠️ **The dense-only arms are the reference T0 did not have.** T0's boundary 5 is this call at **L=500**
with the **raw** vector (coverage **0.838136**, identical to the exact computation). So:

* **D500_raw vs D100_raw** — the cap's effect **on one lane**, single-variable (raw vector, one lane,
  only the limit moves).
* **C vs D100** — what **fusing three lanes** does **at the same cap and the same query vector**.
* ⚠️ **`D100` must use arm C's own vector or it is not single-variable.** `run_retrieval` computes the
  HyDE-augmented vector internally and returns only the raw one, so `search_with_das` is wrapped with a
  **recording** wrapper (records its `query_vector` argument; changes no behaviour) and that vector is
  what `D100` is run with. ⚠️ **C vs D100_raw would confound the fusion with HyDE** — both are reported,
  and only the pair with the matched vector is read as the fusion's effect.

⚠️ **`RERANKER_FETCH_K` moves with `MMR_CANDIDATES`** (§2). It also renames the metric key
`recall_at_{fetch_k}` — immaterial here, because **this run's unit is COVERAGE, not a fixed-k metric**.

## 4. The unit, and why it is coverage

**Coverage of a query's REACHABLE labelled pages** — the §I66 unit T0 uses, page-level, no k:

```
coverage(q) = |distinct pages in the arm's pool  ∩  (relevant_pages ∩ reachable_pages)| / |reachable|
```

* The pool is **the product's own `run_retrieval(...)["hits"]`** — i.e. `search_with_das` **plus the
  graph append** — exactly the object T0 recorded as `fusion_ranked`.
* **`reachable_pages`** = the pages the live content filter can ever return (T0: **888**).
* ⚠️ **No fixed-k metric is reported as an endpoint.** Coverage at a pool boundary is the right unit
  (§I66); `recall@k` at a pool of width 500 would compare different k's across arms.

**Reported per arm:** mean coverage (overall + per `query_type`), the pool-size distribution, and the
**per-query page sets** (so the verifier and any reviewer can re-derive everything).

## 5. Pre-registered predictions (stated BEFORE the numbers, so they can be wrong)

1. **C vs C_nommr ≈ 0.** MMR is inert at the shipped width because `len(deduped) ≤ 100` on most
   queries. ⇒ **§I89's MMR suspicion is expected to be REFUTED at this configuration.**
2. **W500 vs C > 0, and large** — of the order of the fusion's whole −0.1537 loss, if the cap is the
   cause.
3. **W500_nommr ≈ W500** — the cap acts independently of MMR.
4. **D100 < T0's b5 (0.838136)** — the cap costs pages on the dense lane alone too.
5. **C < D100** — fusing three lanes at the same cap loses pages relative to the dense lane alone
   (the sparse/ColBERT lanes are model-independent and contribute mass to candidates the dense lane
   would not have surfaced).

⚠️ **A prediction that fails is the finding.** These are registered so the run can falsify them.

## 6. Guards (each must be able to FAIL)

| # | check |
|---|---|
| **G1** | **THE ANCHOR — arm C reproduces T0's fusion coverage `0.684486`** (T0 artifact, `aggregate.fusion.overall.coverage_reachable`), tolerance **1e-6**. If it does not, this harness is not T0's instrument and the run is **VOID** |
| **G2** | **arm C reproduces T0's fusion POOL SIZE** — mean **86.466165**, tolerance 1e-6 (the same object, measured a second way) |
| **G2b** | **`D500_raw` reproduces T0's boundary 5 coverage `0.838136`**, tolerance 1e-6 — a **third** anchor, on a boundary T0 computed by a different route (T0's b5 was a live Qdrant call too, but through its own code) |
| **G3** | every arm scores **133** queries with **0 errors** |
| **G4** | every pool in every arm is **page-deduped** — no `page_number` appears twice (asserts we read `search_with_das`'s output, not a raw lane) |
| **G5** | **determinism: arm C is run TWICE and is bit-exact** on every query's page set and coverage. Legitimate because §I68 landed (§I84) |
| **G6** | **nesting: `pages(C) ⊆ pages(W500)` on every query** — widening the cap must be a superset, or the widening changed the candidate set rather than the cut, and the attribution is not read |
| **G7** | the **reachable-pages set is identical to T0's** (sha256 of the sorted page list, `meta.reachable_pages_set_sha`) — the denominator did not move |
| **G8** | **`reranker_fetch_k` and `mmr_candidates` moved together** in the width arms (asserted, recorded) — §2's read-off-the-code constraint |

⚠️ **G1/G2 are the load-bearing pair**: they make "this is T0's fusion boundary" a measurement rather
than a claim, on **two independent quantities** (coverage and pool size).

## 7. Reading rule

* **n = 133**; the resolution floor is **≈ 0.020** overall, **≈ 0.04 per type** (n = 40).
* **This run ships nothing.** It attributes an existing loss. A pool gain is **not** a recall gain
  (§I65) — and §I67 already measured the width's **endpoint** null, so the expected shape is
  **pool coverage rises while the endpoint stays flat**.
* **Quote deltas against arm C**, and state the arm's config with every number.
* ⚠️ **MMR λ is not a variable here.** `cfg.mmr_lambda = 0.7` is inside W7 §6.5's 0.5–0.8 band, so if
  MMR *is* implicated the suspect is the **similarity measure** (ours is RRF-score relevance +
  **Jaccard** diversity — lexical, not semantic), not λ. §E1b (the course's canonical MMR) is a
  **separate, later** arm and is **not** measured here.
* ⚠️ **No claim about the endpoint.** This run does not rerank and does not measure top-k.

## 8. Cost, and the stop rule

* **Read-only.** No writes to any collection, no LLM calls (HyDE frozen). The cluster traffic is the
  embedder + the fused lanes (`search_with_das` also runs the cross-encoder — the price of calling the
  product's own `run_retrieval` verbatim).
* **4 product arms × 133 queries** (measured shape: ~5 min/arm) + the cheap D100 arm (one Qdrant call
  per query, no reranker). ≈ **25 min wall**.
* ⚠️ **Serialize against other cluster work**; `socket.setdefaulttimeout(90)` + 3 retries per
  product-path call, as in T0/T1.

## 9. Verifier — independent, stdlib only, per stage

`logs/p1/step10/fusion_attribution_verifier.py`, reading **only the written JSON**, re-deriving from
the **raw per-query page arrays**:

| # | check |
|---|---|
| V1 | 133 rows / 0 errors per arm |
| V2 | every arm's mean coverage re-derives from its per-query page sets |
| V3 | the per-`query_type` means re-derive |
| V4 | G1 — arm C's coverage vs T0's `0.684486` (tolerance 1e-6) |
| V5 | G2 — arm C's mean pool size vs T0's `86.466165` |
| V6 | G4 — page-dedup in every arm |
| V7 | G6 — `pages(C) ⊆ pages(W500)` per query |
| V8 | G5 — arm C's two reps are bit-exact per query |
| V9 | the reported **deltas** (W500−C, C_nommr−C, W500_nommr−W500, C−D100, D100−T0b5) re-derive |

⚠️ **Mutation-proved before the run** (`logs/p1/step10/fusion_attribution_mutation_log.txt`): each
mutation must turn **exactly** its own check red.

⚠️ An independent cross-family reviewer (`openai/gpt-oss-20b`, read-only) is dispatched on a **compact
extract**, never the full artifact (§I74's lesson).

## 10. Preconditions

1. ✅ §I68's client-side-RRF fix is committed (`939beae`) — the funnel is deterministic (G5).
2. ✅ `knowledge_base_v3` holds the pooled nomic index (3,796); the derived collections are 768d, so
   the DA and graph lanes are **live** on this index (both are OFF in T1 only because a 1024d arm
   cannot query them).
3. ✅ The HyDE cache resolves under the registered digest.
4. ✅ The cluster is reachable.
5. ⏳ **This file is committed ALONE, before the run.**

## 11. Stated — what this run does NOT do

* **It does not measure the endpoint** — no reranking, no top-k. §I67 owns that, and its answer was a
  null. This run says *where the pages go*, not whether the student is better served.
* **It does not test the course's canonical MMR** (§E1b) — that needs the full-dim vectors carried
  through the fusion, a product-path change with its own before/after.
* **It does not test lane weighting** (§E2).
* **It does not measure the cross-encoder's −0.2292 loss** — that is the *other* half of T0's funnel,
  and it is not a fusion component. **Named, so the two losses are not conflated.**
* One document, one day, one funnel.
