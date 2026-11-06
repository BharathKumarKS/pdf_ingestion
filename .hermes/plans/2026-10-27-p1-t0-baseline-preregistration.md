# P1 — T0 pre-registration: the FULL-FUNNEL nomic BASELINE, and the aperture sweep

> **Written 2026-10-27, BEFORE the run.** This registers the instrument for **T0** — the full-funnel
> baseline on the adopted embedder (`nomic-ai/nomic-embed-text-v1.5` @768/64 on `knowledge_base_v3`) —
> and the **recall-vs-threshold (aperture) sweep** that goes with it. It fixes the **population, the
> boundaries, the score scale at each boundary, the metric set, the sweep grid and the guards**.
> **Nothing here has been measured.** Per D6.1 this file is **committed ALONE**, before the run.
>
> Plan: `.hermes/plans/2026-10-26-p1-nomic-full-lanes-and-fusion-plan.md` §C/§C2/§D-T0.
> Register: `IMPROVEMENTS.md` §I89 (the measurement T0 rests on).

---

## 1. What T0 is — and what it is NOT

**T0 is a CHARACTERISATION, not a ship test.** It produces the **reference table** that T1–T3 and every
later change are read against, and it **locates the loss**. It ships nothing and decides nothing.

⚠️ **T0 fixes the INSTRUMENT. The aperture VALUE is an OUTPUT, not an input.** No threshold is
pre-committed; the sweep is measured and the value is read off the curve afterwards. Any change that
*uses* that value is a **separate treatment** and needs its **own** pre-registration.

⚠️ **Why this is not the same question Stage F asked.** Stage F (§I85) was a **paired A/B** (v2/qwen3 vs
v3/nomic) with DA and graph **OFF**. T0 is a **single arm** with the product's **real lane set ON**, so
it does **not** reproduce Stage F/G's rows — its anchor is the **dense-lane exact rows only** (§5, G3),
which are DA-independent.

## 2. The population — named exactly (§I71/§I72's rule)

File: **`data/eval_queries_v2.json`** ⚠️ **NOT** `data/eval_queries.json`, which is still
`evaluate_rag.py`'s *default* `--query-file` (`evaluate_rag.py:1075`). T0 passes the file explicitly.

| family | ids | n | labels? | in T0? |
|---|---|---|---|---|
| retrieval-labelled | `gold-*` (53 factual + 40 multihop), `ovw-*` (40 overview) | **133** | ✅ `relevant_pages` | **YES — the T0 population** |
| negative / unanswerable | `neg-*` | 34 | `relevant_pages: []`, `answerable: false` | **NO** — abstention is their metric, not recall |
| visual | `vis-*` | 33 | ⚠️ **field populated but NOT a label** | **NO** — see below |

⚠️ **The visual rows LOOK labelled and are not.** Every `vis-*` row carries a `relevant_pages` list, so a
naive count reads **166 labelled queries**. The `calibration_note` on each says otherwise, verbatim:
*"Visual, generated from page 37 (DB page numbering — **traceability only, NOT a label**); labels pending
book-wide visual scan"*. **It is the page the query was generated from, not a judged relevance label.**
⇒ **the labelled population is 133, not 166.** (Also blocking: `visual_knowledge_base` holds 1,033 points
for the **old** doc `6d55c52b` only — there is no ColPali data for the new doc.)

**Labels per query:** mean **27.3**, median **6**, min 1, max **314**. ⚠️ The mean is dominated by
overview queries (a label-*size* artifact, §I58) — report `n_relevant` per query beside every metric
(W7 §3.3), never the mean alone.

**Relevance is BINARY** — there is no grade field. ⇒ **nDCG is binary** (rank-weighted recall). A graded
label set is a **separate artifact** (§C of the plan); T0 reports binary nDCG and says so.

**Query types:** 53 factual / 40 multihop / 40 overview. ⚠️ **Every aggregate is reported per type** —
each lane applies to one type (graph → multihop, RAPTOR → overview), and the resolution floor roughly
**doubles** per type (~0.020 at n=133 → **~0.04** at n=40).

## 3. The arm — the product as shipped

**One arm: `knowledge_base_v3` / `nomic-ai/nomic-embed-text-v1.5` / 768 / low 64.**

| setting | value | asserted as |
|---|---|---|
| `QDRANT_COLLECTION` | `knowledge_base_v3` | G1 |
| `DENSE_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | G1 |
| `DENSE_DIM` / `DENSE_DIM_LOW` | 768 / 64 | G1 |
| `QUERY_INSTRUCTION` | `search_query: ` | G1 |
| `DOCUMENT_PREFIX` | `search_document: ` | G1 |
| `DA_ENABLED` | **true** (the product's value — ⚠️ **not** Stage F/G's forced `false`) | G1 |
| graph lane | **ON** | G1 |
| `SPLADE_ENABLED` | true | G1 |
| HyDE | **ON, frozen** — `data/hyde_cache/` (§I73); **a miss RAISES**, never a live call | G1 |
| `reranker_fetch_k` / `reranker_top_k` | 100 / 20 | G1 |
| `dense_prefetch_limit` / `dense_rescore_limit` | 1000 / 500 | G1 |

⚠️ **The lane set is RECORDED, not changed.** RAPTOR is **absent from v3** (B1) and **not on the eval
path at all**; the visual lane is unmeasurable (§2). The fusion config is the product's shipped one:
**our MMR variant (RRF-score relevance + Jaccard diversity, `store.py:810-846`), λ = 0.7, W = 100**.

## 4. The boundaries, and the SCORE SCALE at each (the load-bearing part)

⚠️ **`store.search()` returns different score scales depending on how many lanes are live**, so a
"threshold" means different things at different boundaries:

| # | boundary | what its score IS | what a threshold there means | sweep? |
|---|---|---|---|---|
| 1 | **dense lane, exact 64d MRL** @ N=1000 | **cosine** | **THE APERTURE** (W1 §10.2.1's cone) | **YES — the τ sweep** |
| 2 | **dense lane, exact full-dim** @ L=500 | **cosine** | **THE APERTURE** | **YES — the τ sweep** |
| 3 | **fusion pool** (product `search_with_das`, fetch_k=100) | **RRF rank score** `Σ 1/(1+rank)` (`store.py:655-659`) | a **RANK CUT**, *not* an aperture | reported at the shipped setting only |
| 4 | **cross-encoder** (product reranked top-20) | rerank score | a third scale | reported at the shipped setting only |

⚠️ **Boundaries 1–2 are EXACT BRUTE FORCE** (§I66's method — no ANN, no Qdrant scoring, no RRF), which
is what makes a cosine τ meaningful and reproducible. Boundaries 3–4 are the **real product path**.
⇒ **the aperture sweep runs on boundaries 1–2 only**; a threshold on 3 is a rank cut and is labelled as
one, never as an aperture.

**The §I66 coverage unit is also computed** (coverage of a query's **REACHABLE** labelled pages) at all
four boundaries, so T0 is comparable to §I66/§I86/§I89 — the product metrics (§6) are a **different
unit** and are never conflated with it.

## 5. The aperture sweep — the design

**Two arms per boundary, and they are the course's own construction.** W1 §10.2.1: *"retrieve **up to K**
documents, **strictly terminating** the search at the edge of the aperture"* — i.e. **K AND τ**, not K
or τ.

* **arm "scoop" (τ = 0.0, K = 100)** — top-K by cosine, **no aperture**. This is the product's current
  behaviour (the pool does the cutting) and the **"initial scoop"** the baseline is read against.
* **arm "aperture@τ"** — `{cosine ≥ τ} ∩ top-K`, for **τ ∈ {0.0, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9}**.
  ⚠️ **0.7 is W1 §10.2.1's illustrative example** and **0.85 is W12 §2.4's historical-static example** —
  included so the course's own numbers appear on the curve. ⚠️ **0.45 is included as a *capstone*
  reference only** (it was applied to **RRF scores**, i.e. a rank cut — §C2); it is **not** the course's
  number.
* **Also record `|{cosine ≥ τ}|`** — the aperture's **uncapped** admission, so the curve shows what the
  aperture alone lets in, separately from the K cap.
* ⚠️ **τ = 0.0 in the aperture arm must equal the scoop arm exactly** — a built-in consistency check.

**What the sweep reports, at each τ:** recall@K, precision@K **with its ceiling `min(|rel|,K)/K` beside
it** (W7 §3.3), `|{cos ≥ τ}|`, and the per-type cut. The **recall-vs-τ curve** is the primary output.

⚠️ **The recall-vs-τ curve IS the AUC-PR curve** (W7 §6.1's staircase): a sweep recording **precision and
recall at each τ** *is* the precision–recall curve. Record once, report both ways. ⚠️ And per W12 §2.4 a
**single global τ is an "architectural illusion"** — so the curve is reported **per query type**, and no
one global τ is assumed to be right.

## 6. The metric set (per boundary, per type)

recall@k · precision@k (**+ its ceiling**) · context_precision · hit@k · **MRR** · **MAP** · **nDCG@k
(binary)** · **F1** · **AUC-PR** (from the curve) · `n_relevant` and `k` beside every one.

* ✅ already in the product's `compute_retrieval_metrics`: recall@fetch_k, recall@top_k, hit@top_k,
  context_precision, mrr, ndcg@top_k.
* ❌ **TO BUILD: MAP** — rank-based, binary; added to **`compute_retrieval_metrics`** (the product's
  function, so it is available everywhere) with a unit test.
* ❌ **TO BUILD: precision@k** — re-added **only with its ceiling reported beside it** (it was removed
  because it read as failure at its own ceiling, `evaluate_rag.py:352`).
* ❌ **TO BUILD: F1** — from precision + recall at the same k.
* ⚠️ **AUC-PR** comes from the sweep, not from `compute_retrieval_metrics`.
* ⚠️ **Order-dependent metrics (MRR / MAP / nDCG) are reported ONLY when `reranked_metrics_valid` is
  true and the fallback count is zero** (§I55 — the cluster reranker swallows failures and returns the
  pool UNRANKED, silently flattening them).

## 7. Guards (each must be able to FAIL)

| # | guard | why it can fail |
|---|---|---|
| **G1** | the resolved config equals §3 on every row (`collection`, `model`, `dim`, `dim_low`, prefixes, `da_enabled=True`, SPLADE, N/L, fetch_k/top_k, HyDE) | a forgotten export silently runs the wrong arm (§I80's trap) |
| **G2** | **133** queries scored, **0 errors**; and `n_relevant` present on every row | a partial run |
| **G3** | the **dense-lane exact** coverage reproduces **§I89's arm-B rows** — `cov_base` **0.918953**, `cov_cut` **0.838136** (±0.002) | ⚠️ **the strongest anchor and it is DA-independent.** If the exact 64d/full-dim rows move, the instrument is not the registered one and nothing downstream is comparable. |
| **G4** | two repeats of the product path are **bit-exact on every metric of every query** | §I68 made the funnel deterministic, so drift here is harness drift |
| **G5** | `reranked_metrics_valid == true` and **fallback count 0** | §I55 — otherwise MRR/MAP/nDCG are meaningless |
| **G6** | **lane liveness**: the DA lane and the graph lane each return **non-empty** results on at least the queries they should (multihop for graph) | ⚠️ **a lane that is silently `[]` is indistinguishable from a lane that contributed nothing** (§D15/§I12 — the exact defect §A fixes). Count it and surface it. |
| **G7** | the **recall-vs-τ curve is monotone non-increasing in τ** at each boundary | the candidate set shrinks monotonically in τ, so a non-monotone curve means the sweep is measuring something else |
| **G8** | the **τ = 0.0 aperture arm equals the scoop arm** exactly (same pages, every query) | a built-in consistency check on the sweep construction |

## 7b. Per-stage verifiers — ONE PER STAGE, each must be able to fail

⚠️ **A single aggregate check is not enough**: a stage can be wrong while the aggregate is right, and an
aggregate that re-derives itself from the same code path verifies nothing. So **every stage gets its own
verifier**, and each verifier **re-derives that stage from the RAW per-query array** (stdlib only, no
import of the harness's helpers), independently of the harness that produced it. Each exits non-zero on
its own failure, and the artifact records each verifier's status.

| # | stage it verifies | what it re-derives | what makes it FAIL |
|---|---|---|---|
| **V1** | **base** — dense 64d exact @ N=1000 | the per-query page sets from the raw vectors, then coverage + recall | the page sets or the aggregate disagree with the harness; or **G3's §I89 anchor (0.918953)** is off |
| **V2** | **cut** — dense full-dim exact @ L=500 | the top-L page sets **within** V1's lane, then coverage + recall | the cut is not a subset of the base lane; or **G3's §I89 anchor (0.838136)** is off |
| **V3** | **fusion pool** — product `search_with_das`, fetch_k=100 | the pool from the per-query hit list: **pool size ≤ 100**, R@100, and the **DA/graph liveness counts** | pool > fetch_k; a lane that returned `[]` is reported as live (**G6**); or the recorded fusion config is not the shipped one |
| **V4** | **cross-encoder** — product top-20 | the reranked order from the raw per-query list, then **R@20, MRR, MAP, nDCG** | `reranked_metrics_valid` is false or the fallback count is non-zero (**G5**) — an order-dependent metric must not be reported from an unranked pool; or top_k ≠ 20 |
| **V5** | **the aperture sweep** — τ grid, boundaries 1–2 | **the whole recall/precision curve at every τ** from the raw cosine sets: `|{cos ≥ τ}|`, recall@K, precision@K **and its ceiling** | the curve is not **monotone non-increasing** in τ (**G7**); τ=0.0 ≠ the scoop arm (**G8**); or **AUC-PR** does not re-derive from the per-τ points |

⚠️ **V5 is the one that matters most here**, because the sweep is the new instrument and it is the one
with no prior art in the repo. It must re-derive the curve **from the per-query cosine sets**, not from
the harness's summary — otherwise it is checking the harness against itself.

⚠️ **A stage whose verifier cannot fail is not verified.** Each Vn is **mutation-proved** before the run:
break the mechanism in the harness and the corresponding Vn must go red, with the others green. The
mutation log is a deliverable.

## 8. Reading rule (registered before the numbers exist)

* **n = 133**, paired where a comparison is made. **Resolution floor ≈ 0.020** (n=133) and **≈ 0.04** per
  type (n=40). ⚠️ **Anything below the floor is recorded, not claimed** (D0.1).
* **T0 ships nothing.** The output is a **reference table** + a **calibration curve**.
* ⚠️ **The aperture value is read OFF the curve, not assumed.** The pre-registered reading: a τ is a
  *candidate aperture* if **recall is preserved within the floor** while **precision rises materially**;
  the curve, not a single point, is the result. **No τ is pre-committed.**
* ⚠️ **Not production numbers** for any A/B claim — T0 is a single arm with HyDE frozen. Quote deltas,
  not absolutes, against anything historical.
* ⚠️ **The gold-set limits are stated with every claim:** binary relevance (not graded) and n=133 (vs
  W7 §6.3's 500–1,000, which is calibrated to a **1 %** effect where our declared floor is **2 %**).

## 9. What T0 does NOT measure (stated, not hidden)

* **The visual (ColPali) lane** — no data for the new doc, and the 33 visual queries carry **no labels**.
* **RAPTOR** — absent from v3 and **not on the eval path** (`evaluate_rag.py` never calls `search_raptor`).
* **The generator stage** — no synthesis, no judge.
* **Any cross-index (v2-vs-v3) claim** — that is T1/T3.
* **Any causal claim beyond one document, one day.**

## 10. Preconditions

1. ⏳ **§A (the per-space query-vector fix) is NOT required for T0** — nomic is 768d and the derived
   collections are 768d, so the DA and graph lanes work. It **is** required before T3.
2. ✅ §I68's client-side-RRF fix is committed (`939beae`) — this is what makes **G4** legitimate.
3. ✅ The HyDE cache resolves for these queries (§I73).
4. ✅ `knowledge_base_v3` holds the **pooled** nomic index (3,796 points; §I88/§I89) — **G3** checks it.
5. ⏳ **This file is committed ALONE, before the run.** Nothing measured is in it.

## 11. Cost and deliverables

**Read-only.** No writes to any collection, no LLM calls (HyDE is served from the frozen cache).
Estimated **~15–25 min** (133 queries × the product path, twice for G4, plus the exact brute-force
sweep).

* `logs/p1/step10/t0_baseline.py` — the harness (extends `stageG_decomposition.py`: exact brute force at
  boundaries 1–2, the real product path at 3–4, plus the τ sweep and the product metric set).
* `logs/p1/step10/t0_verifier.py` — **independently written stdlib aggregation** with **one verifier per
  stage (V1–V5, §7b)**: `--check` re-derives each stage from the raw per-query array and exits non-zero
  on that stage's failure; `--extract` writes a compact reviewer pack (§D6.3 — never hand a reviewer a
  large artifact whole).
* `logs/p1/step10/t0_mutation_log.txt` — the **per-stage mutation proofs** (§7b): each mechanism broken
  in the harness, the matching Vn going red and the others staying green.
* `logs/p1/step10/t0_baseline.json` — the artifact (carries each verifier's status).
* `logs/p1/step10/t0_run_<date>.txt` — the run log.
* `IMPROVEMENTS.md` **§I90** — the register entry.
* `DECISIONS.md` — the T0/aperture/score-scale entries named in the plan's §F.
