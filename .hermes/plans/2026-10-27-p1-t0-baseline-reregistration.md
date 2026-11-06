# P1 — T0 RE-REGISTRATION: boundary 5 (the Qdrant dense lane) and precision@k / F1 in V4

> **Written 2026-10-27, BEFORE the re-run.** The pre-registration
> (`.hermes/plans/2026-10-27-p1-t0-baseline-preregistration.md`) fixed the instrument and **nothing
> has been measured against it yet** — the run was blocked by the shared cluster (see `HANDOFF.md`
> session 22) and **no `t0_baseline.json` exists**. So this is a **re-registration of an instrument
> that never produced a number**, not a post-hoc change to a result. Per D6.1 it is **committed
> ALONE** before the run.
>
> Precedent for the form: §I67's E4 → E4′, §I71's C2 → C2′, §I72's S1 → S1′.

---

## 0. What changes, and what does NOT

**Adds:**
* **Boundary 5** — the **product's own dense lane, queried through Qdrant** (the real ANN index), at
  the same limit as boundary 2. Swept over τ like boundaries 1–2.
* **A sixth verifier, V6**, for boundary 5.
* **`precision_at_k` and `f1_at_k` added to V4's re-derivation** (they were already *reported* per §6;
  §7b's V4 row named only R@20 / MRR / MAP / nDCG).

**Does NOT change — and this is load-bearing:**
* Boundaries 1–4 keep their definitions, their units and their score scales. **T0's existing rows stay
  comparable**, and **G3's §I89 anchors (0.918953 / 0.838136) are untouched.**
* The population (133 labelled queries), the τ grid, the metric set, and guards G1–G8.
* **No threshold value is pre-committed.** The aperture is still an OUTPUT.

## 1. Why boundary 5 — and why boundaries 1–2 are still exact

⚠️ **The question that produced this.** Boundaries 1–2 are computed by **exact brute force** (numpy
over every chunk), not through the vector database. So they measure a **cleaner** pipeline than the
one users hit: they exclude the ANN index's approximation loss. The gap is real and, before this
re-registration, it was only *implicit* — present as the difference between boundary 2 and boundary 3
— and **not measured on its own**.

⚠️ **Why boundaries 1–2 cannot simply be moved onto the vector DB.** The aperture sweep needs a
**cosine** to threshold on, and the product's fused path does not have one: with the sparse and
ColBERT lanes live, `store.search()` puts the **RRF rank score** (`Σ 1/(1+rank)`, ≈1.0, 0.5, 0.33 …)
into `.score` (`store.py:655-659`), so a "0.7 threshold" there would be a cutoff on a rank score.
That is §C2's finding and it is unchanged. **The exact computation stays.**

⚠️ **What boundary 5 adds.** It isolates the **dense lane through the real index** — one lane, so the
score stays a cosine, but produced by Qdrant's ANN rather than by exhaustive arithmetic. Boundary 2
minus boundary 5, **same query vector, same limit**, is then the **approximation loss** as its own
number, and the τ sweep can be read on both.

## 2. Boundary 5 — the exact definition

| field | value |
|---|---|
| call | `store.search(q_vec, tenant_id="global", limit=L, query_text=None)` |
| query vector | **the SAME raw query vector as boundaries 1–2** — ⚠️ **no HyDE**, so boundary 5 vs boundary 2 is single-variable (exact vs ANN) |
| `query_text=None` | ⚠️ this is what makes it dense-only: `store._qdrant_search` skips the SPLADE and ColBERT branches on their own guards (`cfg.splade_enabled and query_text`), leaving the single-prefetch dense branch |
| limit | **L = 500** — the product's own `dense_rescore_limit`, so it is directly comparable to boundary 2 |
| score | **the full-dim cosine** — with one prefetch the outer query's score is Qdrant's own score, and the collection is Cosine-distance |
| filters | the product's own (`_NOT_RAPTOR`, the page window, `is_content is not False`) — it is the product's code path, not a re-implementation |
| recorded | ranked **pages** with their cosine, exactly as boundaries 1–2 |
| swept | **yes** — τ over the same grid, **labelled as the ANN cosine** |

⚠️ **Boundary 5 is NOT the same object as boundary 3.** Boundary 3 is the *fused* pool (all lanes,
rank score, ≤100). Boundary 5 is the *dense lane alone* through the index (cosine, ≤500). They are
reported side by side and never conflated.

## 3. Guards added (each must be able to FAIL)

| # | guard | why it can fail |
|---|---|---|
| **G9** | boundary 5's recorded scores are on a **cosine scale, not a fused rank scale** — asserted by the **number of DISTINCT score values** in the top-k (a cosine over 500 real candidates takes hundreds of distinct values; an RRF rank score takes a handful, `1/(1+rank)`), plus every score within [-1, 1] | a lane that silently fell back to the fused path would still return pages and still score ≤ 1 — only the score *shape* catches it |
| **G10** | boundary 5 returns **≥ 1 page on every query**, and the **ANN-vs-exact page overlap** is recorded per query | an empty lane, and the approximation gap being silently dropped |

## 4. V6 — the boundary-5 verifier

Re-derives, from boundary 5's **raw per-query page+cosine array** and nothing else:

* coverage of the query's **reachable** labelled pages, and recall@20 / recall@100;
* the **τ curve** at boundary 5 — `n_admitted`, `admission_uncapped`, recall@K, precision@K and its
  ceiling — compared against the recorded curve;
* **G7-style monotonicity** and **G8-style τ=0.0 == scoop** at boundary 5;
* the **cosine-scale check** (G9) recomputed independently;
* the **ANN-vs-exact overlap** against boundary 2's page set, recomputed.

FAILS if any of those disagree with the harness, or if the scale check fails.

## 5. V4 gains precision@k and F1@k

⚠️ **Stated plainly, because it was a real gap.** §6 registers `precision@k` (+ its ceiling) and `F1`
as **reported** metrics, and the harness does record them per boundary. But §7b's V4 row named only
**R@20 / MRR / MAP / nDCG** for **re-derivation**, so a wrong precision/F1 *formula* would have been
caught only by the unit tests on `compute_retrieval_metrics`, never by V4. This re-registration adds
them to V4's comparison list.

* `precision_at_20` = (distinct relevant pages in the reranked top-20) / 20 — the same numerator as
  `recall_at_20`, divided by the slot count.
* `f1_at_20` = the harmonic mean of `precision_at_20` and `recall_at_20`; 0.0 when either is 0.
* Both are compared against the harness's recorded values (4 dp → tolerance 5e-5).

⚠️ **This does NOT make precision an independent source of information** — it is `recall × |rel| / k`
by construction. It makes the *formula* checked, which is the point.

## 6. Reading rule (unchanged, restated)

* **n = 133**; floor ≈ **0.020** overall, ≈ **0.04** per type (n=40). Anything below the floor is
  **recorded, not claimed**.
* **T0 ships nothing.** The output is a reference table + a calibration curve.
* ⚠️ **The aperture value is read OFF the curve.** No τ is pre-committed.
* ⚠️ **Boundary 5 is not a "production" number either** — it is one lane of the product, with the
  query vector un-HyDE'd so it is comparable to boundary 2. Quote deltas against boundaries 2/3.

## 7. Preconditions

1. ✅ §I68's client-side-RRF fix is committed (`939beae`) — G4's determinism rests on it.
2. ✅ The HyDE cache resolves (§I73).
3. ✅ `knowledge_base_v3` holds the pooled nomic index (3,796 points; §I88/§I89) — G3 checks it.
4. ⚠️ **The shared cluster must be quiet.** The first T0 attempt was blocked by multi-minute stalls
   (5-query run: 2,700 s wall / 7.9 s CPU). The harness now sets `socket.setdefaulttimeout(90)` and
   retries each product-path call 3×; ⚠️ **that hardening post-dates the recorded V1–V5 mutation
   proof**, so the mutation proof is **re-run against the current revision** as step 1 of the run.
5. ⏳ **This file is committed ALONE, before the run.**

## 8. Cost and deliverables

**Read-only.** No writes to any collection, no LLM calls (HyDE frozen). Boundary 5 adds one Qdrant
call per query.

* `logs/p1/step10/t0_baseline.py` — boundary 5 + G9/G10.
* `logs/p1/step10/t0_verifier.py` — **V6**, and **V4 extended** with precision/F1.
* `logs/p1/step10/t0_mutation_log.txt` — the re-run proof, now covering **V1–V6** and the two new
  mutations (**MV6** = boundary 5's recorded cosine set collapsed to a rank-score scale; **MV7** =
  V4's precision/F1 record corrupted).
* `logs/p1/step10/t0_baseline.json` — the artifact (carries each verifier's status).
* `IMPROVEMENTS.md` **§I90** — the register entry.
