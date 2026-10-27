# P1 — Stage G, RE-RUN pre-registration: arm B's construction is now POOLED (§I88)

> **Written 2026-10-26, BEFORE the re-run.** Stage G's first run (session 20, `IMPROVEMENTS.md` §I86)
> decomposed **v3 = nomic LATE-CHUNKED** against **v2 = qwen3**. §I88 then established that nomic's
> late-chunk path is **faithful** (cos 1.000000 to an independent span-pooling), so the 0.155 coverage
> loss is a **method** choice — and the treatment is to **drop late chunking for nomic** and re-embed
> v3's dense lanes **pooled**. That write is **DONE and verified** (see §7). This file registers the
> **changed treatment arm** and the guards that make the re-run trustworthy, **before** it runs.
> Per §I67/§I71/§I72, a re-registration is legitimate when it is **restated by measurement** and
> **committed before the run**; it is **not** a relaxation.

## 1. What changed — exactly one thing

**Arm B's dense construction: late-chunked → pooled.** Nothing else moves.

* **The write:** `scripts/reembed_chunks.py --from-collection knowledge_base_v2 --pooled`
  (new mode; `LateChunkEmbedder.embed_isolated_batch`). 3,796 points / 341 parents / **0 failures** /
  91.9 s. Point ids and the `chunk_id` set **byte-identical** to pre-write; `colbert` + `sparse` +
  every payload key carried over from v2 unchanged.
* **The acceptance evidence** (`logs/p1/step10/pooled_reembed_{pre,post}.json`,
  `…_carryover.json`; post sha256 `3d751cf9ce5a8d4f…`), all guards pass:

| check | pre-write | post-write |
|---|---|---|
| cos(stored `dense_full`, a FRESH pooled embedding) | **0.804564** (min 0.5949; 199/200 < 0.99) | **1.000000** (0/200 < 0.99) |
| v3 coverage, full-dim, no prefilter, L=500 | 0.688664 *(= §I86's late-chunked row)* | **0.843325** *(= §I87's `nomic_pooled` row)* |
| v3 coverage L=100 / 1000 / 2000 | 0.4148 / 0.8257 / 0.9488 | 0.591316 / 0.933638 / 0.978649 |
| lane gate (`verify_collection_lanes.py`) | — | all 4 lanes on all 3,796 points, exit 0 |
| v2 | 3,869 | **3,869 — untouched** |

⚠️ **This is the arm-B anchor, and it is why the re-run is measurable**: v3's stored index now
reproduces §I87's `nomic_pooled` row at **every L** — the same numbers, from the stored index rather
than from the probe's own pooled call.

## 2. The question the re-run poses

**§I86's result was that no stage favoured nomic** — every stage ≤ 0, the only RESOLVED stage the
**fused pool** (−0.0358), and the cross-encoder absorbed it (−0.0012, unresolved). ⚠️ **But that was
the LATE-CHUNKED index.** §I87 showed the loss was the ingestion, not the model: **pooled nomic beats
pooled qwen3 (+0.0362, RESOLVED)**, and pooled nomic is the best of the four arms measured.

So the re-run asks the same shape of question on the **fixed** index: **does the pooled ingestion gain
survive the funnel, or is it absorbed again — by the 100-slot fusion and/or the cross-encoder?**

## 3. Arms, stages, unit — unchanged from §I86

* **arm A = `knowledge_base_v2` / `Qwen/Qwen3-Embedding-0.6B` / 1024 / low 64** (control; **untouched**)
* **arm B = `knowledge_base_v3` / `nomic-ai/nomic-embed-text-v1.5` / 768 / low 64** (**now pooled**)
* Stages: **base** (exact 64d MRL lane @ N=1000) → **cut** (exact full-dim top-L=500 **within** that
  lane) → **fusion** (the product's `search_with_das` pool, fetch_k=100) → **cross-encoder** (the
  product's reranked top-20). Stages 1–2 are **exact brute force** (§I66's method, no ANN); 3–4 are
  the **real product path**.
* **Unit:** coverage of a query's **REACHABLE** labelled pages (§I66's unit). Raw product metrics
  (R@100 / R@20 over **all** labelled pages — a different unit) reported beside it, never conflated.
* **DA off, graph off** (§I85's re-registration — both derived collections are 768d nomic-only, so a
  1024d arm cannot query them), **HyDE ON and frozen** (§I73 cache; a miss raises).
* The **§I86 GAP ROW** is also re-measured: full-dim over ALL chunks, **no 64d prefilter** (§I63's
  oracle configuration), L ∈ {100, 500, 1000, 2000}.

## 4. Guards — two ADDED, the rest carried

| # | guard | why it can fail |
|---|---|---|
| G1 / G2 | per-arm resolved config asserted (`collection`, `model`, `dim`, `dim_low`, prefixes, N/L, `da_enabled=False`) | a forgotten export silently runs the wrong arm |
| G3 | **arm A** reproduces §I66's exact-probe rows (0.8151 base / 0.7478 cut, ±0.002) | the harness drifted from the registered instrument |
| G4 | 133 queries scored in **both** arms, 0 errors | a partial run |
| G5 | both arms share one corpus (3,489 chunks / 888 pages) | the denominator moved |
| G6 | **arm A**'s gap row L=500 reproduces §I66's N=3489/L=500 = **0.828609** (±0.002) | the no-prefilter row drifted |
| **G7 (NEW)** | **arm B**'s gap row L=500 reproduces §I87's `nomic_pooled` = **0.843325** (±0.002) | ⚠️ **the treatment is not what we think it is** — a half-written or still-late-chunked v3 reads 0.6887, far outside the tolerance. This is the guard that the **pooled index** is what is being decomposed. |
| **G8 (NEW)** | **arm A** reproduces §I86's arm-A rows — `cov_base` 0.815136, `cov_cut` 0.747763, `cov_fusion` 0.660452, `cov_ce` 0.458824, `cov_fulldim_L500` 0.828609 — **to 1e-6** | v2 is untouched and §I68 made the funnel deterministic, so arm A **must** be bit-stable across the two runs. Drift here is harness drift, not a finding. |

⚠️ **G8 is the strongest control in the run**: arm A shares nothing with the treatment, so if it moves,
**nothing** in the run is attributable.

## 5. Reading rule (registered before the numbers exist)

* Per-stage paired **Δ = B − A**, n=133, 95 % CI (`1.96·SD/√n`). **RESOLVED** = the CI excludes 0.
* ⚠️ **Stage G is DIAGNOSTIC. It ships nothing.** The ship decision is **Stage F's** (§I85, and its
  re-run). Stage G exists to say **where** a gain or loss lives.
* ⚠️ **The stage-1 comparison after this write is NOT like-for-like, and must not be read as one:**
  arm A is qwen3 **late-chunked**, arm B is nomic **pooled** — two differences (model *and*
  construction). The **like-for-like** pooled-vs-pooled contrast is §I87's, **already measured**
  (+0.0362, RESOLVED). Quote that one for the embedder question; quote this run's Δ for the **funnel**
  question.
* **Hypothesis, labelled as such (not a result):** the gap row should flip **positive** (arm B
  0.8433 vs arm A 0.8286 ≈ **+0.015**), and the open question is whether stages 1–4 follow it or
  whether the fusion + cross-encoder absorb it again as they did in §I86.

## 6. What this run does NOT measure (stated, not hidden)

* **The DA and graph lanes** — off in both arms (§I85's constraint; the derived collections are 768d).
  So stages 3–4 are the product funnel **minus two recall lanes**, and do **not** reproduce §I66's
  DA-on 0.6048 / 0.4318.
* **The generator stage** (§I66's fourth stage) — no synthesis, no judge.
* **RAPTOR** — not in v3 (73 nodes are a separate step) and **not on the eval path at all**
  (`evaluate_rag.py` never calls `search_raptor`).
* **Any causal claim beyond these two indexes, one document, one day.**

## 7. Preconditions (all hold)

1. ✅ The §I88 write is **done and verified** (§1; post artifact sha256 `3d751cf9ce5a8d4f…`).
2. ✅ `knowledge_base_v2` is **untouched** (3,869 points; lane gate exit 0).
3. ✅ §I68's client-side-RRF fix is **committed** (`939beae`) — the funnel is deterministic, which is
   what makes **G8** a legitimate exactness claim.
4. ✅ The HyDE cache resolves for these queries (§I73).
5. ✅ The per-arm environment is exported **and asserted in-harness** (G1/G2).
6. ⏳ **This file is committed ALONE, before the run.** Nothing measured is in it.

## 8. Cost

~5 min, **read-only** (no writes to any collection, no LLM calls — HyDE is served from the cache).
