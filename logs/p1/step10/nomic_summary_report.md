# The nomic index — where we are, what the numbers say, and what to do next

> **Written 2026-10-27 (session 23).** A plain-language read of the nomic adoption: the reference table
> (T0), the ship test (T1), the loss attribution (the fusion run), and the ordered next actions.
> Every number here is from a registered artifact in `logs/p1/step10/`, named beside it.
> **Register entries:** `IMPROVEMENTS.md` §I89 (the pooled re-embed + Stage G), §I90 (T0), §I91 (T1),
> §I92 (the fusion attribution). **Decision log:** `DECISIONS.md` §8.

---

## 1. What was adopted, and the one sentence that must ride with it

**`nomic-ai/nomic-embed-text-v1.5` @768/64 on `knowledge_base_v3`** (the pooled write, §I88/§I89).

⚠️ **The like-for-like base-lane advantage is +0.0362, not +0.104.** The +0.104 figure is arm A
(qwen3, **late-chunked**) vs arm B (nomic, **pooled**) — two differences at once. The like-for-like
contrast is §I87's **nomic pooled − qwen3 pooled = +0.0362** (RESOLVED). And §I87 also measured nomic
**late-chunked** *losing* to qwen3 late-chunked by **−0.1399** — the sign depends on the construction, so
**name the construction with the number.**

⚠️ **nomic was adopted as a COST decision, on new measurement — not because it was found "better" than
the alternative that was declined.** The measured reason was gemma's endpoint (2048-token window, 37.3 %
of children exposed) and its gated tokenizer (§I77). Do not restate it later as "gemma was worse".

---

## 2. T0 — the reference table (one arm, the product's lane set)

`logs/p1/step10/t0_baseline.json` (sha256 `9a5037308c71c02d…`). 133 labelled queries, **0 errors**,
**all 10 guards + V1–V6 pass**. HyDE ON and frozen, read-only. Coverage = **the fraction of a query's
REACHABLE labelled pages that a stage actually returned** (§I66's unit), n=133.

| boundary | coverage | Δ vs previous | recall@20 | MAP | nDCG@20 |
|---|---|---|---|---|---|
| 1 base — exact 64d MRL @N=1000 | **0.918953** | — | 0.3548 | 0.2315 | 0.3931 |
| 2 cut — exact full-dim @L=500 | **0.838136** | −0.0808 | 0.4242 | 0.2925 | 0.4919 |
| 5 b5 — the SAME lane through QDRANT (ANN) | **0.838136** | **0.000000** | 0.4242 | 0.2925 | 0.4919 |
| 3 fusion — product pool (≤100) | **0.684486** | **−0.1537** | 0.4491 | 0.3421 | 0.5506 |
| 4 cross-encoder — product top-20 | **0.455330** | **−0.2292** | 0.4442 | 0.2789 | 0.4946 |

**Three readings, and they are all still true:**

1. **Rows 2 and 5 are IDENTICAL on every metric of every query** (page overlap 1.000000, mean score gap
   2e-06). At L=500 the vector database's approximate search loses **nothing** to exhaustive arithmetic on
   this corpus. The "exact vs real-world" objection to boundaries 1–2 is, at that limit, **empty**.
   ⚠️ Scope: **L=500** — the product's own dense call inside `search_with_das` uses `limit=100`.
2. **The two real losses are the FUSION (−0.1537) and the CROSS-ENCODER (−0.2292).** Everything upstream
   of the fusion is in good shape.
3. **The aperture is INERT until τ ≈ 0.7**, because the **K=100 cap** — not a similarity bar — does the
   cutting: 513 pages clear τ=0.0 and 414 still clear τ=0.70, but only 100 are admitted. That is the
   course's own "blind K-NN" critique measured on our system. ⚠️ **No τ is committed** — the curve is the
   result.

**Per type at the endpoint:** factual **0.5577** · multihop **0.5812** · overview **0.1937**.
⚠️ **Overview is the loss**, and its lane (RAPTOR) is absent from v3 and not on the eval path.

---

## 3. T1 — the ship test (the pooled index vs the incumbent, base lanes)

`logs/p1/step10/t1_base_lanes.json` (sha256 `f84e4b6599ee1f99…`). Two arms — **A** = `knowledge_base_v2`
/ qwen3-1024, **B** = `knowledge_base_v3` / nomic-768 **pooled** — 133 queries, HyDE ON and frozen,
read-only, 0 errors. **All eleven guards pass.**

**The result: a NULL.**

| endpoint | Δ (B − A) | 95 % CI | W/L/T | verdict |
|---|---|---|---|---|
| **P1 cR@20** (primary) | **+0.003894** | **[−0.020984, +0.028771]** | 24/22/87 | **UNRESOLVED** |
| **P2 raw R@20** (primary) | **+0.003805** | [−0.020503, +0.028112] | 24/22/87 | **UNRESOLVED** |
| R@100 | **−0.018953** | **[−0.036938, −0.000969]** | — | **RESOLVED NEGATIVE** |
| factual (n=53) | +0.010310 | [−0.048981, +0.069601] | 6/7/40 | unresolved |
| multihop (n=40) | −0.003554 | [−0.029711, +0.022603] | 3/4/33 | unresolved |
| overview (n=40) | +0.002840 | [−0.004851, +0.010532] | 15/11/14 | unresolved |

* **The point estimate is ~6× below the run's own resolution floor (0.024878 at n=133)** — power was
  ample, not the limit (n=33 would suffice for δ=0.05). **Per the pre-registered rule, nothing ships.**
* **Two guards make the null mean something.** **E8:** arm A reproduces the registered §3d row — R@20
  **0.4475** vs **0.452**, gap −0.0045, inside ±0.020. **E9 (new):** arm A is **BIT-EXACT against Stage
  F's recorded arm A** (a different session) — **133/133, 0 mismatches**. Since arm A shares nothing with
  the treatment, that makes "**the treatment is isolated to arm B**" a **measurement**, not an assumption.
* **The one resolved secondary is negative and replicates:** R@100 **−0.0190** here vs Stage F's
  **−0.0354** — nomic's fused pool covers ~2–3.5 pp fewer pages at the `fetch_k` cut, in two independent
  runs. ⚠️ That is *not* the endpoint the student sees; top-20 is where they look.
* **Diagnostic D1** — arm B pooled minus arm B late-chunked at the endpoint — is **+0.004989
  [−0.014788, +0.024767], UNRESOLVED**. The pooled re-embed is worth **+0.1547 at the base lane** (§I87)
  and **+0.005 at the endpoint**. The write worked; the funnel ate it.

### The chain, which is the actual finding

```
base lane        +0.104   (§I89, exact 64d MRL)          <- large, RESOLVED
full-dim cut     +0.090   (§I89)                          <- large, RESOLVED
fusion           -0.019   (§I89)                          <- RESOLVED NEGATIVE
product top-20   +0.0039  (T1, §I91)                      <- UNRESOLVED, ~6x below the floor
```

⇒ **The funnel does not preserve the embedder's advantage. It discards it.** A better embedder is **not**
the lever on this pipeline; **the fusion is.** This is the third independent confirmation (§I85's product
null, §I89's stage decomposition, T1), now on the **pooled** index.

---

## 4. The loss attribution — **it is the 100-slot CAP, not MMR**

`logs/p1/step10/fusion_attribution.json` (sha256 `1a43f2d980183335…`). 133 queries, 0 errors, T0's lane
set (DA + graph ON), HyDE frozen, read-only, wall 2,629 s. **All nine guards pass, including all three
anchors** — arm C reproduces T0's fusion coverage **0.684486** *and* T0's pool mean **86.466165**, and
`D500_raw` reproduces T0's boundary 5 **0.838136**. Only the product's own config knobs moved.

| arm | what it is | pool coverage | Δ vs the product (paired) | 95 % CI | W/L/T |
|---|---|---|---|---|---|
| **C** | **the product as shipped** (cap 100, MMR on) | **0.684486** | — | — | — |
| C_nommr | cap 100, **MMR off** | 0.687664 | +0.003178 | [−0.002242, +0.008598] | 6/3/124 |
| **W500** | **cap 500** (both knobs), MMR on | **0.868024** | **+0.183538** | **[+0.151074, +0.216001]** | **79/0/54** |
| W500_nommr | cap 500, MMR off | 0.868024 | **+0.000000** | [0, 0] | 0/0/133 |
| D100 | dense lane alone @100, arm C's own vector | 0.630958 | (C − D100) +0.053528 | [+0.020642, +0.086414] | 59/13/61 |
| D100_raw | dense lane alone @100, raw vector | 0.593164 | (D100 − D100_raw) +0.037794 | [+0.011527, +0.064061] | 51/12/70 |
| D500_raw | dense lane alone @500 (= T0 b5) | 0.838136 | (D500_raw − D100_raw) +0.244972 | [+0.205687, +0.284257] | 83/0/50 |

**Five findings:**

1. **The cap is the entire loss, and it is large.** Cap 100 → 500 lifts pool coverage **0.684486 →
   0.868024, +0.183538 [+0.151074, +0.216001], RESOLVED, 79 wins to 0 losses.** That is *more* than T0's
   whole fusion loss (−0.1537), because the widened **fused** pool (0.868) also beats the **dense lane
   alone** at the same width (0.838). The cap costs the dense lane alone **+0.245** too.
2. **MMR is innocent — §I89's "leading suspect" is REFUTED.** MMR off at the shipped width buys
   **+0.003178, unresolved** (6 wins / 3 losses). At width 500 MMR is **exactly inert: 0.000000, 0/0/133**
   — because `search_with_das` only calls `_mmr_select` when `len(deduped) > reranker_fetch_k`, and the
   deduped pool is ≤ 389 at width 500, so **the branch is never taken**. This was **predicted from the
   code before the run**.
3. **Page dedup is not the culprit either — and that is a code fact, not a measurement.** It removes
   duplicate *chunks*, not *pages*, so under a page-level metric it **cannot lower coverage**; it can only
   free slots for the cap. No dedup-off arm was run because the product has no such flag.
4. **HyDE is worth +0.037794 [+0.011527, +0.064061], RESOLVED** — the first **isolated** HyDE effect in
   the register (`D100 − D100_raw`: same lane, same limit, same code, only the query vector differs).
5. **Fusing three lanes beats the dense lane alone at the same cap:** `C − D100 = +0.053528`, RESOLVED.
   The sparse and ColBERT lanes are **contributing**, not merely diluting.

### ⚠️ And this is where the next action changes

**The cap is recoverable at the pool — and §I67 already measured the SAME change at the product endpoint
as a NULL** (W 100→300 and 100→500, both knobs together: Δ R@20 c-norm **+0.0032 / +0.0027**, both
unresolved). ⇒ **A +0.1835 pool gain buys +0.003 at the endpoint.** That is *"a pool gain is not a recall
gain"* measured with a very large pool gain. ⚠️ **One caveat on that comparison, stated rather than
buried:** §I67 ran with **HyDE OFF**; this attribution ran with **HyDE ON**. So the *pool-level* finding
here is complete and anchored, but the **top-20 width effect under HyDE ON is still unmeasured** — a
cheap named follow-up (§I92a), not a re-derivation of §I67.

* **The fusion is NOT the binding constraint on the endpoint.** §I89's *"the fusion destroys the arm
  difference"* still stands — that is a different claim.
* **The endpoint loss sits in the pool → top-20 RANKING step.** T0's funnel: fusion **0.684486** →
  cross-encoder top-20 **0.455330**, i.e. **−0.2292** discarded, **and widening the pool does not repair
  it**. That step has **never been attributed**: no run has separated *"the cross-encoder ranks the right
  page low"* from *"the 20-slot cut discards it"*.
* ⚠️ **Do not read this as "widen the fusion".** The width lever is measured, cheap and **inert at the
  endpoint**.

---

## 5. What is NOT measured (stated, not hidden)

* **The full funnel (T3).** T1 and T0 both run with **DA and the graph lane OFF or ON respectively, and
  never with both arms lane-complete** — the derived collections are 768d, so a 1024d arm cannot query
  them (§A of the plan is the fix). T3 is **unmeasured**.
* **RAPTOR / the overview lane** — absent from v3 and never called by `evaluate_rag`. B1/B2 are the
  cheapest unbuilt item and they target T0's worst type (**overview 0.1937**).
* **The visual (ColPali) lane** — no data for the new document, and the 33 `vis-*` queries carry no
  labels (which is why the gold set is 133, not 166).
* **The generator stage** — no synthesis, no judge in any of these runs.
* **Graded relevance** — `relevant_pages` is binary, so our nDCG is rank-weighted recall, not the
  course's graded apex metric (W7 §2.5). A page-level 0/1/2 scheme is recommended as a **new artifact
  beside** the binary labels; it does not block anything here.

---

## 6. Next actions, in order

1. **▶ ATTRIBUTE THE POOL → TOP-20 STEP (the new #1).** T0's funnel loses **−0.2292** there and nothing
   has separated *"the cross-encoder ranks the right page low"* from *"the 20-slot cut discards it"*.
   Those two have **different fixes** (a better reranker vs a wider top-k), and neither can be chosen
   before the split is measured. This is where the endpoint loss lives.
2. **§A — the per-space query-vector fix** (unblocks T3, and repairs a silent lane skip).
3. **B1/B2 — RAPTOR into v3 + wire the overview lane**, the cheapest item and the one that targets the
   worst query type (**overview 0.1937** at the endpoint, **0.5221** at the pool).
4. **T2 — the lane ablation per type** (each lane's own contribution, on nomic alone).
5. **§E1b — the course's canonical MMR** — ⚠️ **now LOW priority.** Our variant is measured to cost
   **+0.003178, unresolved**, and **exactly 0 at width 500**; the suspicion that motivated it is refuted.
6. ⚠️ **Do NOT ship the fusion width.** Cap 100 → 500 buys **+0.1835 of pool coverage** and §I67 measured
   the endpoint as a **null**. Re-testing it would be re-measuring a null.
7. ⚠️ **S6, the embedder fine-tune, stays PARKED** — and the reason is now stronger than "the fusion eats
   it": T1 shows the embedder's advantage is **+0.0039 unresolved** at the endpoint, ~6× below the floor.
   **A model change is not the lever on this pipeline.**

**Carried forward:** signoff 3 (re-confirm Shape B) · signoff 4 (accept §I79) · the **A2 `.env` flip**
(owner action — every stage runs on env exports) · the arm-2 harness (`min_chunk_tokens`, a fragment) ·
§I56's DA lane · §G2's V5 build · §G5/§I2 (`hop_distance` is a constant 0, so "multihop" is nominal).
