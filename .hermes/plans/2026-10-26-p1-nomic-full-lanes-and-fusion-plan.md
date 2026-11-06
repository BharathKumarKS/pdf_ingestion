# P1 — nomic with all lanes, then the fusion loss: the ordered plan

> **Written 2026-10-26 (session 21), for the NEXT session.** This sequences four pieces of work that
> were agreed this session and are **not yet started**:
> (A) the **per-space query-vector fix**, which is what makes a lane-complete v2-vs-v3 A/B possible at
> all; (B) **RAPTOR into v3** plus wiring the overview lane into the eval; (C) the **full metric set** on
> the stage ladder + **C2 the aperture** (the text similarity threshold); (D) the **four measurement
> tracks** (T0 the full-funnel nomic **baseline**, T1–T3); then (E) **attributing the actual fusion loss**
> and fixing it.
>
> ⚠️ **Updated this session with the owner's direction:** nomic is **marked as adopted**, and the
> baseline is scoped as a **full-funnel reference table** (§C/§C2/§D-T0) — see **"The nomic decision"**.
>
> **Nothing in this file has been measured or built.** It is a plan, not a result. The one measurement
> it rests on is §I89 (the Stage G re-run), which is registered and in the tree.

---

## Why this order

Stage G (§I89) fixed where the value dies: on the pooled index the advantage is **large and resolved
upstream** (+0.104 at the 64d base, +0.090 after the full-dim re-rank, 67 wins to 8 losses) and is
**destroyed at the fusion** (0.838 -> 0.641, and the arm difference flips to −0.019, resolved
negative). At the product's top-20 the two indexes are indistinguishable (+0.004, unresolved).

So the fusion is the binding constraint. Two consequences drive the ordering:

1. **Do not fix the fusion against a lane set we are about to change.** The product's real lane set is
   dense + sparse + colbert + DA + graph (+ RAPTOR as a separate overview lane). Stage F/G measured a
   **narrowed** configuration — DA and graph OFF in both arms — only because a 1024-dim arm cannot
   query the 768-dim derived collections. Fixing the fusion now would tune it for a lane set that is
   about to move.
2. **The lanes themselves will not rescue the endpoint, and we should say so up front.** DA was
   already measured as a **harm** (−0.0262 on top-20 R@20), the graph lane's contribution is
   **unmeasured**, and the graph lane **bypasses the fusion entirely** (its hits are appended after
   `search_with_das`), so it cannot repair a fusion loss. Including the lanes makes the comparison
   *complete*, not *favourable* — and because the derived lanes are identical across arms, they will
   most likely make the arm difference **smaller**, not larger. The null gets more likely, not less.

---

## The nomic decision — marked, and framed correctly

**Adopted: `nomic-ai/nomic-embed-text-v1.5` @768/64 on `knowledge_base_v3`** (the pooled write, §I88/§I89).
Everything below builds on it. Three qualifications ride with the decision, or the number gets restated
wrongly later:

* ⚠️ **The like-for-like base-lane advantage is +0.0362, not +0.104.** §I89's +0.104 is arm A (qwen3,
  **late-chunked**) vs arm B (nomic, **pooled**) — two differences at once, not like-for-like. The
  like-for-like contrast is §I87's **nomic pooled − qwen3 pooled = +0.0362** (RESOLVED). Quote **+0.0362**
  as the embedder's base-lane advantage. And §I87 also measured nomic **late-chunked** losing to qwen3
  late-chunked by **−0.1399** — the sign depends on the construction, so **name the construction with the
  number**.
* ⚠️ **The advantage is measured at the base / full-dim stage, and it does NOT survive the funnel.** §I89:
  +0.104 (base) → +0.090 (full-dim cut) → **−0.019 RESOLVED NEGATIVE (fusion)** → **+0.004 unresolved
  (top-20)**. Whether the **like-for-like** +0.0362 survives the funnel is **UNMEASURED** — that is T3.
* ⚠️ **⇒ The baseline this plan sets is a FULL-FUNNEL baseline whose purpose is to LOCATE the loss — NOT a
  target for model improvement.** §I89's first finding is that the binding constraint is the **fusion**,
  not the embedder. A model improvement measured against this baseline at the endpoint will most likely
  show nothing, because the funnel discards it upstream. **Fix the fusion first (§E); only then does a
  model change have room. S6 stays parked.**

---

## A. The per-space query-vector fix  (small, product-path)

**The defect.** Both derived lanes take the **arm's** dense query vector and send it verbatim to a
768-dim collection:

```
store.search_da(...)              -> query_points(da_collection,      query=query_vector.tolist())
graph._find_concepts_scored(...)  -> query_points(concept_collection, query=query_vector.tolist())
```

`query_vector` is the arm's own dense vector (`store.py:886` for DA, `evaluate_rag.py:224` for graph).
A 1024-dim arm gets a 400, the lane's `except` swallows it and returns `[]`, and the lane is **silently
skipped**. This is the §D15/§I12 defect, recorded but never fixed.

⚠️ **Scope:** it bites only when the arm's dimension differs from the derived collections'. Production
is 768-dim nomic, so **production is fine**. It is the v2/1024 *arm* that is broken — which is exactly
why Stage F had to turn both lanes off and narrow its question.

**The fix.** One query vector **per space**: for the DA and graph lanes, embed the query with the model
that *built* that collection (nomic/768), not with the arm's model. The lane's space is nomic's, so the
lane's query must be nomic's.

**Design constraints, both load-bearing:**

* ⚠️ **Change only the MODEL, never the text input.** The DA lane currently receives the **HyDE-augmented**
  vector (it is fused with the dense lane), and the graph lane receives the **raw** query vector. The
  fix must preserve each lane's existing text input and swap only the embedder, or it changes the lane's
  meaning rather than its space.
* ⚠️ **Resolve the space off the COLLECTION, not from config** — read the collection's dimension and
  assert the lane's vector width against it. A config default is how this defect appeared.
* ⚠️ **Do not replace the silent skip with another one.** Today a dimension mismatch returns `[]` with a
  warning. It must raise, or at minimum be counted and surfaced in the artifact, because a lane that is
  silently empty is indistinguishable from a lane that legitimately contributed nothing (§I47/§I68 class).

**Guards (each must be able to fail):**

| # | guard |
|---|---|
| A1 | a **1024-dim arm** can query the 768-dim DA and graph lanes and gets **non-empty** results (today: 0) |
| A2 | the lane's query vector is **not** the arm's dense vector (different widths) — the fix actually switched the space |
| A3 | **arm B is bit-exact before and after** the fix on every metric — its dense vector already IS nomic's, so the fix must be a no-op for it. ⚠️ **This is the discriminating control:** a fix that moves arm B has changed something other than the space. |
| A4 | a deliberate dimension mismatch raises (or is counted and reported), never a silent `[]` |

**Deliverable:** the code change, tests, and a read-only before/after probe showing arm A's lane results
go 0 -> N while arm B's metrics are unchanged.

---

## B. RAPTOR into v3, and wiring the overview lane

**B1 — the write.** `knowledge_base_v3` has **0** RAPTOR nodes; `knowledge_base_v2` has **73**. The
summary text is derived from chunks whose ids did **not** change (Shape B preserved them), so the nodes
can be **copied and re-embedded** with nomic — no LLM pass, no re-parse. Minutes.

* ⚠️ v2's RAPTOR nodes carry **no `colbert` and no `sparse`** (the lane gate reports 3,796/3,869 for
  both) — so only the dense lanes are written for them.
* Gate: v3's point count goes **3,796 -> 3,869**, and the lane gate still passes.

**B2 — the wiring.** ⚠️ `evaluate_rag.py` **never calls `search_raptor`**. It is called from exactly one
place in the repo: `streamlit_app.py:589`. So the overview lane is **not on the eval path at all** and
has never been measured in any funnel run.

* Decide the integration shape and **label it**: a **separate lane** (what the UI does) versus a **fused**
  variant. ⚠️ §I66's binding constraint is the fusion's 100-slot output — adding RAPTOR *to the fusion*
  makes it compete for those slots and can displace dense hits. **Recommended: report it as a separate
  lane first**, plus a fused variant labelled as a diagnostic construction, not the product.
* This is a **product-path change**: it needs its own before/after and its own entry.

---

## C. The metric set, on the stage ladder

**Why.** Stage G measures **inclusion** only. A reranker's job is **ordering**, and recall@20 cannot
distinguish "ranked 1st" from "ranked 19th". Direct evidence that this matters: a previous width
experiment resolved **MRR POSITIVE (+0.0935)** while **context precision resolved NEGATIVE** and R@20 was
unresolved — the width reordered the pool without changing inclusion, and recall was blind to it.

**Report, at every stage of the ladder** (base / cut / fusion / cross-encoder) **and per lane ablation:**

| metric | in the product today? | note |
|---|---|---|
| **recall@k at EACH funnel boundary** | ⚠️ **only @100 and @20** | §H's stated course standard: *"measure recall@N at each funnel boundary"* — we currently cannot see **which stage leaks**. Report at every boundary: 64d prefetch, full-dim cut, fusion pool, reranked top-20. |
| **hit@k** | ✅ | binary "did the student get anything useful" |
| **MRR** | ✅ | rank of first relevant; measured **pre-threshold** by design |
| **nDCG@k** | ✅ | ⚠️ **binary relevance** (`relevant_pages`), page-deduped — it is rank-weighted recall, not a graded metric |
| **MAP** | ❌ **to build** | rank-based, binary; cheap |
| **precision@k** (fixed-slot) | ❌ **deliberately removed** | see the two-precisions note below — it sat at its own ceiling |
| **context_precision** | ✅ | chunk-unit, denominator = **returned count**; a DIAGNOSTIC (0.05–0.10 here) |
| **context_precision_judged** | ✅ (flag) | RAGAS-style, rank-weighted, judge-scored — the only precision here that can move |
| **F1** | ❌ | derived from precision + recall; low priority at fixed k |
| **AUC-PR** | ❌ | W7 §6.1's staircase includes it; robust to class imbalance (W7 §5.3 calls ROC *"the absolute assassin"* of retrieval — the true-negative denominator is ~10⁸). Optional: a curve metric, not a ship test. |
| ~~**MMR**~~ | — | ⚠️ **NOT a metric.** MMR is the diversification **ALGORITHM** inside the fusion; you measure it by **ablation (§E1)**, not by scoring it. **MRR is the metric; MMR is the mechanism** (and §I89 names it the leading suspect for the fusion loss). |

**The two precisions — BOTH are reported, and the history is why.** `context_precision` and the removed
`precision@top_k` are **the same ratio** (relevant ÷ returned); they differ only in the **denominator**.
The removed one divided by a **fixed slot count** `top_k`, so it was capped at
`min(|relevant|, top_k) / top_k` ≈ **0.10** on this gold set (median 2 labelled pages) — it read as
**failure while sitting at its own ceiling** (`evaluate_rag.py:352`, the code's own comment). It was
replaced by `recall@top_k` (denominator `|relevant|`, well-conditioned at any gold-set size).
`context_precision` keeps the ratio but divides by the **actual returned count**, so it is not capped.
**⇒ If `precision@k` is re-added, it MUST be reported with its ceiling beside it**, or it repeats the
defect. The precision that can actually move is the **judged** RAGAS variant.

⚠️ **Gate every order-dependent metric.** The cluster reranker **swallows failures and returns the pool
UNRANKED** (§I55), so MRR / nDCG / MAP silently flatten. Report them only when the
`reranked_metrics_valid` flag is true and the fallback count is zero.

⚠️ **Report every metric per query type.** Each lane applies to one type (graph → multihop, RAPTOR →
overview); an aggregate dilutes the thing being measured. ⚠️ **The floor roughly doubles per type:**
~0.020 at n=133, **~0.04** at n=40.

⚠️ **State the convention with the number.** Page-level recall is **"pages of the top-k CHUNKS"** (the
product, `evaluate_rag.py:333-341`), **NOT** "top-k pages" (§I70's screen). The two differ by ~0.02 and
caused a VOID run (§I72).

⚠️ **Report `|relevant|` and `k` beside every metric (W7 §3.3).** *"the total population of relevant
documents n must always be reported alongside the metric … a standalone statement like 'Recall@20 = 0.7'
conveys zero meaningful information without this context."* ⇒ the T0 artifact must carry **`n_relevant`
per query** (Stage G already does) and every aggregate must state its **n**.

⚠️ **The gold-set gaps against the course's own standard — with a recommendation on each (W7 §2.1, §2.5, §3.3, §6.3):**

* ⚠️ **GRADED relevance — the gap worth closing, and the recommendation is YES.** W7 §2.5: *"grading
  must move beyond binary relevance and utilize an integer scale, typically r ∈ {0,1,2,3,4}."* Our
  `relevant_pages` is **binary**, so our **nDCG is binary** — the course's *apex* metric (rank-aware
  **and** grade-aware) loses the grade half and collapses to rank-weighted recall, which also weakens
  the course's own **diagnostic pair** (NDCG + Recall, §6.2). **Proposed scheme: page-level 0/1/2** —
  the page *contains the answer* (2) · *on-topic / adjacent* (1) · *irrelevant* (0). ⚠️ **It must be a
  NEW artifact BESIDE the binary labels, never a silent replacement** — every historical run used
  binary, and D6.4's comparability rule governs. **Why this over more queries:** it re-annotates ~133
  queries × ~2–3 pages; it does not author new queries. **It does NOT block T0** — report binary nDCG
  now, graded when the label set exists.
* ⚠️ **n = 133 vs the course's 500–1,000 — and the honest reading is NARROWER than it looks. The
  recommendation is NO, do not enlarge now.** W7 §6.3 calibrates that floor to a **1% effect** (*"to
  confidently detect a genuine 1% improvement"*). **Our DECLARED floor is 0.020 (2 %)** (D0.1), and at
  that floor **n=133 is adequate** — every effect we have resolved is ≥ 0.02. ⇒ **We are consistent with
  our declared question and inconsistent only with the course's 1 % ambition.** Enlarging is the single
  most expensive item on this list, it unblocks **no current question**, and W7 §2.1 is explicit that
  engineers must not build gold sets (it needs domain-expert authoring). **If we ever enlarge, enlarge
  PER TYPE:** the real weakness is **n=40 (floor ~0.04)** on the two types the lanes live on (multihop,
  overview), not the total. ⚠️ **The counter-argument, stated:** the capstone is vetted by the course
  author, and *"133 against the course's 500–1,000"* is a criticism a reviewer can make on **standards**
  grounds even though our power is adequate for our floor — **a credibility cost, not a statistical
  one.** **Reopening condition (D0.1):** a larger gold set lowers the floor and reopens every
  recorded-and-unresolved knob at once.
* **MMR's λ is ALREADY in the course's band.** `cfg.mmr_lambda = 0.7`, inside W7 §6.5's *"typically
  between 0.5 and 0.8."* ⇒ **If MMR is the fusion's culprit (§E1), it is NOT because λ is mis-set** —
  see §E1 for what the actual suspect is.

---

## C2. The aperture — the similarity threshold we have, and the one we do not

**What exists today.** The text path has exactly ONE aperture mechanism and it is **switched OFF**:

* `evaluate_rag.py --score-threshold` (**default 0.0**) → `run_retrieval`'s `hits_above`
  (`evaluate_rag.py:246`). At **0.0 everything passes**, so `recall@fetch_k` is recall over the whole
  pool and the **pool width (`fetch_k` = 100) is doing the filtering, not a similarity score.** Every
  recorded eval run used 0.0 (a few historical VM runs used 0.45 / 0.4 / 0.3 — recorded, not calibrated).
* `visual_score_threshold` (**0.58**) is the **only** calibrated threshold in config, and it is
  **image-calibrated**: `visual_search` divides the MaxSim sum by the query's **patch count**, so a short
  **text** query sits on a different scale and 0.58 drops nearly every page (**§B4e**). The UI text path
  therefore **ranks, not filters** (`score_threshold=0.0`). §B4e names the method: **take the knee of the
  score distribution** — applied so far only to the visual lane.
* MRR is measured **pre-threshold** (over the whole `hits` list) — deliberately, per the module docstring.

**⇒ The task: a recall-vs-threshold CURVE per boundary, then a chosen aperture.**

⚠️⚠️ **First, the SCALE problem — and it is why "the threshold" has never meant anything here.**
`store.search()` returns a **different score scale depending on how many lanes are live**:

| live lanes | what `search()` puts in `.score` | source |
|---|---|---|
| **dense only** | the **full-dim cosine** (0–1) | the outer re-score query, `store.py:661-669` |
| **dense + sparse + colbert** (production, `SPLADE_ENABLED=true`) | the **RRF rank score** `Σ 1/(1+rank)` ≈ 1.0, 0.5, 0.33 … — **NOT a similarity** | `_FusedPoint(score=e["rrf_score"], …)`, `store.py:655-659` |

⇒ **In production the fusion boundary's `score` is a RANK score, not a cosine.** `hits_above`
(`evaluate_rag.py:246`) thresholds on that field, so **a threshold at the fusion boundary is a RANK
CUT, not an aperture** — which is what the historical `0.45` actually was, and why the current `0.0` is
simply "no cut". **The course's aperture — a cosine cone — is only meaningful at a boundary whose score
IS a cosine: the dense lane.** Get this right before any sweep is pre-registered, or the sweep measures
three different quantities and reports them as one.

**So the sweep is PER BOUNDARY, with that boundary's own scale:**

| boundary | score | what a threshold there means | sweep |
|---|---|---|---|
| **dense lane (pre-fusion)** | **cosine** | **THE APERTURE** (the course's cone, W1 §10.2.1) | cosine τ ∈ {0.3 … 0.9} — **this is the one the course means** |
| **fusion pool** | **RRF rank score** | a **rank cut**, NOT an aperture | a rank-cut curve, **labelled as such** |
| **cross-encoder (top-k)** | rerank score | a third scale entirely | only when the reranked-metrics-valid flag is true (§I55) |

1. Over the 133 gold queries, record the **score distribution at each boundary** AND the
   **recall-vs-τ curve** — not a single number. Take the **knee** (§B4e's method).
2. Report the full metric set at **fixed-k** (today's convention, threshold 0.0) **and across the
   sweep**. fixed-k = *"of the top k, how much is gold"*; the aperture = *"of everything above the score
   bar, how much is gold"* — only the second survives a change in pool width.
3. ⚠️ **A metric under a threshold is threshold-dependent.** Pin the aperture before comparing across
   configs, or the comparison moves with the bar (§B4e's warning, generalised to the text lanes).
4. ⚠️ **The recall-vs-τ curve and AUC-PR are the SAME instrument.** W7 §6.1's staircase places AUC-PR as
   the curve metric; a sweep recording **precision AND recall at each τ** *is* that curve. Record it
   once, report it both ways.

### What the course actually says — VERIFIED against the source documents (2026-10-26)

⚠️ **The course material is NOT in git.** It lives in
`Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/` — the **week summaries** (`Week_Summary/Week N
Summary.pdf`, which carry the deck's own section numbering) and the **decks** (`Slides/`). The word
"aperture" appears **nowhere in this repo**; it has to be carried in from the course.

**VERIFIED VERBATIM — Week 1 Summary §10.2.1, "Spherical Cones and Search Apertures":**

> *"The mathematically sound architecture implements an aperture by setting a strict cosine similarity
> threshold. By setting a threshold of 0.7 (which correlates to a 45-degree cone aperture), the system
> draws a hard boundary. The engine is instructed to retrieve **up to K** documents, strictly
> terminating the search at the edge of the aperture. Opening the aperture wider allows for broader
> topics, while tightening it ensures absolute precision."*

and the flaw it names — which is **exactly our configuration**:

> *"A standard approach is to execute a blind K-Nearest Neighbor (K-NN) search, dictating that the
> system fetch the top 20 nearest results regardless of distance … A blind K-NN search will grab those
> three relevant documents, and then forcefully expand its reach all the way down to the equator to
> grab 17 pieces of irrelevant, orthogonal noise to satisfy the quota."*

**VERIFIED VERBATIM — Week 12 Summary §2.4 "The Empirical Paradox of Global Thresholds", §2.5, §2.6:**

> *"…the global similarity threshold. Historically, architectures utilized a static threshold (e.g.,
> K-Nearest Neighbors within an aperture of > 0.85 cosine similarity) applied uniformly across the
> entire index … queries that were genuinely dissimilar often exhibited a higher average cosine
> similarity (e.g., 0.85) than queries that were truly similar (0.84) … **global thresholds are an
> architectural illusion** … every single neighborhood strictly requires **its own local aperture**."*
> V-Cache's answer is a per-entry **error budget δ** (*"the probability of serving a wrong answer will
> never exceed δ"*), which survives an embedder swap where a raw cosine τ does not.

**VERIFIED — Week 7 Summary §3.3 (the precision ceiling), §6.1 (the staircase), §6.2, §6.3, §6.5:**

* §3.3: *"when n < k, Precision@k has a hard ceiling of n/k … the total population of relevant
  documents n must always be reported alongside the metric."* — **the course teaches the exact reason
  our repo removed `precision@k`.**
* §6.1 the staircase: *Precision/Recall@K → MRR/MAP → AUC-PR → NDCG*, each step fixing the blindness
  below it.
* §6.2 the **minimal diagnostic pair — NDCG and Recall** (*"high recall + low NDCG ⇒ a ranking problem,
  not a retrieval problem"*).
* §6.3: *"to confidently detect a genuine 1% improvement (80% power, alpha 0.05), the gold dataset must
  contain an absolute minimum of **500 to 1,000 queries**."*
* §6.5 **MMR**: *"λ is typically set between 0.5 and 0.8"*; *"setting λ too low (e.g., 0.3)
  over-penalizes similarity"*; diversity-aware retrieval lifts multi-hop answering by **6–12%**.

⚠️ **The course specifies NO default threshold — and its own lab proves it.** The Week-7 lab
(`Labs/Week_7/rag_eval`) ships `--similarity-threshold` with **default 0.0**, identical to ours. The
`0.45` in the capstone's history is the **capstone's own** (the course notes' validation pass says so:
*"capstone, not course"*). **Do not present 0.45 as the course's number.** The only threshold numbers
the course gives are W1's **illustrative 0.7** and W12's historical-static example **0.85**.

⚠️ **UNVERIFIED — do not cite as the course's.** The line *"a low recall number can be a **threshold**
problem, not a **retrieval** problem"*, plus the **0.3/0.4/0.45/0.5 sweep**, appears in the course
notes' Week-7 Q&A — **not** in any deck — and that same Q&A states the eval script default is `0.45`,
which is **false of the course lab (0.0)**. Its provenance is therefore **the capstone, not the
course**. Keep the idea (it is sound and consistent with W1/W12), but **attribute it to us, not to the
deck.**

**⇒ What this means for us.** Our text path runs at threshold **0.0** — an **infinitely wide aperture**,
with the pool width doing the cutting. That is the **exact "blind K-NN" the W1 deck names as the flaw**:
with no aperture we cannot tell *"the retriever missed the page"* from *"the page was there but scored
below the bar"*. **T0 must therefore report the threshold sweep, and the aperture is a CALIBRATION
CURVE, not a single number, until a knee is chosen.**

---

## D. The four measurement tracks (T0 the baseline, T1–T3)

| track | compares | measures | status |
|---|---|---|---|
| **T0** | **v3/nomic alone** (one arm) | the **FULL-FUNNEL BASELINE**: the whole §C metric set, at every funnel boundary, at fixed-k **and** at the aperture (§C2), per query type — the reference table everything else is read against | possible **now** |
| **T1** | **v2 vs v3, BASE lanes** | the narrowed ship test (Stage F re-run on the pooled v3) | possible **now** |
| **T2** | **v3 only, lanes ON vs OFF** | each lane's own contribution, **per type** | graph + DA now; RAPTOR after B1/B2 |
| **T3** | **v2 vs v3, ALL lanes** | the **full-funnel** ship test (§I85 left it unmeasured) | needs **A** + **B** |

* ⚠️ **T0 is DESCRIPTIVE — it is a reference table, not a decision.** One arm has no contrast, so the
  table cannot itself say what to improve; it is the yardstick T1/T2/T3 and every later change are read
  against. Its purpose is to **LOCATE the loss**, not to be a target for model improvement (see "The
  nomic decision" above).
* ⚠️ **T0 must RECORD its lane set AND its fusion config.** Under nomic (768d) the DA and graph lanes are
  live against the 768d derived collections; RAPTOR is absent from v3 (B1) and the visual lane is
  unmeasurable. The fusion config is **the product as shipped** — ⚠️ **our MMR variant (RRF-score
  relevance + Jaccard diversity, `store.py:810-846`), λ = 0.7, W = 100, threshold 0.0** — and it is
  **recorded, not changed**: the baseline measures the product we have, so the **course's canonical MMR is
  an §E1b treatment arm, NOT a baseline setting**. A baseline table without its live-lane list and fusion
  config is not comparable to anything later — and this is exactly what makes **A** unnecessary for T0 but
  mandatory before T3.
* ⚠️ **A nomic-only measurement has no control arm** (v2 cannot use the 768-dim lanes), so T2 must be an
  **ablation inside nomic**, not an A/B.
* ⚠️ **Report every track per query type.** Each lane applies to one type (graph -> multihop,
  RAPTOR -> overview), so an aggregate dilutes the very thing being measured.
* ⚠️ **The floor roughly doubles at n=40.** The familiar ~0.020 floor is for n=133; per type
  (40 multihop / 40 overview) it is **~0.04**. Lane effects smaller than that will not be detectable.
* Each track is **pre-registered before its run**, and **arm A unchanged** (bit-exact) is a guard in T1
  and T3, as it was in Stage G's G8.

---

## E. Then: measure the actual fusion loss

Only after A–D. The fusion does three things in sequence — **RRF -> page dedup -> MMR** — and the split
between them has **never been attributed** (§I66 said the same and left it open).

**E1 — the attribution ablation (do this first).** ⚠️ **TWO separate questions — do not conflate them.**

* **E1a — does MMR hurt at all?** At pool level, measure coverage with: **(i) RRF only; (ii) RRF + dedup;
  (iii) RRF + dedup + MMR (= the product).** Whichever step drops the pages names the fix.
* **E1b — is OUR MMR worse than the COURSE's?** ⚠️ **A different axis, and it is in no plan yet.** Swap
  the variant for the **course's canonical MMR** (W7 §6.5: **cosine(query, document)** for relevance,
  **inter-document cosine** for diversity) and re-measure. **If the canonical form does not hurt, the
  defect is OUR VARIANT, not MMR** — and the fix is to **correct the algorithm, not remove the stage**.
  ⚠️ **Build cost, named:** the fusion's candidates carry `score`/`rrf_score` but **no vectors**, so
  canonical MMR needs the full-dim vectors carried through `search_with_das` — a small but real change to
  the **product path**, so it needs its own before/after.
* ⚠️ **Both arms report PER TYPE**, against the course's prediction (below).

⚠️ **Leading hypothesis, labelled as a hypothesis and not a finding:** **MMR**. MMR exists to penalise
"redundant" candidates, and a page carrying many relevant chunks looks exactly like redundancy — and our
metric is **page-level**, so MMR could be systematically suppressing the pages we count. If that is what
it is, the fix is not lane weighting at all.

⚠️⚠️ **OUR MMR IS A VARIANT — verified in code (`store.py:810-846`) — and the course's λ guidance does
NOT transfer cleanly.** Ours: **relevance = the normalised RRF score** (`rrf_score / max_score`);
**diversity = Jaccard token overlap** (`_tok` = lowercased whitespace split, no stopwords/stemming;
`_jac`). The course's canonical MMR (W7 §6.5) uses **cosine(query, document)** for relevance and
**inter-document cosine** for diversity. Two consequences:

1. **λ = 0.7 is not the same 0.7.** The course's 0.5–0.8 band was tuned for **cosine-scale** terms; our
   two terms are on different scales (a normalised RRF score and a Jaccard overlap), so the band does
   not carry over. ⇒ **the λ value is NOT the suspect — the similarity MEASURE is.**
2. ⚠️ **Our diversity term is LEXICAL, not semantic.** On a homogeneous physics textbook, *distinct*
   pages share heavy vocabulary, so MMR penalises **topical proximity between different pages** — which
   is not redundancy. ⚠️ And the pool is **already page-deduped** before MMR runs (`search_with_das`
   dedups, then MMRs), so MMR **cannot** be removing same-page duplicates: every candidate is already a
   distinct page. **Register the variant as its own entry.**

⚠️ **The course predicts MMR HELPS multi-hop (+6–12 %, W7 §6.5) and that λ too low harms factoids.** So a
negative MMR result here is a **DEPARTURE from the course's own finding** and must be explained, not just
reported. ⇒ **E1 reports PER TYPE, with the prediction stated in advance: MMR helps multihop and is
neutral-to-harmful on factual.** A null on the aggregate with that split is a **different result** from a
null everywhere.

**E2 — lane weighting.** Today the fusion is plain **unweighted RRF**: every lane contributes
`1/(k+rank)`. Sparse and ColBERT are model-independent, so they are identical across indexes and
contribute identical mass to every candidate — which dilutes the dense lane, the only lane that differs.
A weighted RRF is a small change to one function and its call site. **Untested.**

**E3 — fusion width.** Raising the 100 slots was tested at the **endpoint** (§I67, a null), but the
**pool-level** curve was never measured. Sweep W and watch pool coverage. Expected shape: pool coverage
rises with W while the endpoint stays flat (§I72's equaliser) — a **mechanism finding, not a ship**.

**E4 — build the fix** the attribution fingers, and validate it at the **pool AND the product endpoint**.
⚠️ A pool gain is not a recall gain (§I65 is the cautionary case).

---

## F. Register and commit

* `IMPROVEMENTS.md` **§I89** — the Stage G re-run (already drafted in the tree).
* Register the **per-space defect** and its fix as its own entry (§D15/§I12 recorded the symptom).
* **`DECISIONS.md` D1.1 — amend with the like-for-like number.** The nomic adoption currently reads as a
  **cost decision** only; §I87 gives it a like-for-like accuracy figure (**+0.0362**). Record it, and
  record that it is **not** +0.104 (that contrast is not like-for-like).
* **`DECISIONS.md` — a new entry for T0/the baseline:** a **full-funnel baseline to LOCATE the loss**, not
  a target for model improvement (the fusion is the binding constraint, §I89).
* ⚠️ **Register the SCORE-SCALE finding (§C2) as its own entry — it is a defect-class finding, not a
  tuning question.** `search()`'s `.score` is a **cosine only when the dense lane is alone**; with
  SPLADE + ColBERT live (production) it is the **RRF rank score** (`store.py:655-659`). So
  `hits_above`'s "score threshold" **has never been a similarity threshold** in production — a
  threshold there is a rank cut. That is why `0.0` was used everywhere and what the historical `0.45`
  really was. **Any sweep must name its boundary AND its scale** (D4.1's rule, one level up).
* **`DECISIONS.md` — a new entry for the aperture:** the text path has no calibrated threshold today
  (`--score-threshold` = 0.0 = an infinitely wide cone); the **course's definition is verified and
  captured in §C2** (W1 Summary §10.2.1: cosine **0.7** ↔ a 45° cone, verbatim; W12 Summary §2.4:
  global thresholds are *"an architectural illusion"* → local apertures / error budget δ). Record that
  the **course gives NO default and its own W7 lab ships 0.0**, that **`0.45` is the capstone's**, and
  that the aperture is a **calibration curve** until a knee is chosen.
* **`DECISIONS.md` — the gold-set gaps (§C), one entry each:**
  * **Graded relevance: RECOMMENDED.** Binary relevance is why our nDCG is rank-weighted recall, not the
    course's apex metric (W7 §2.5). Proposed page-level **0/1/2** as a **new artifact beside** the binary
    labels. Cheaper than more queries; does not block T0.
  * **Enlarging the eval set: RECOMMENDED AGAINST now.** The course's 500–1,000 (W7 §6.3) targets a **1 %**
    effect; our declared floor is **2 %** (D0.1), where **n=133 is adequate**. Named remedy, per type, if
    a per-type question becomes load-bearing — with the **credibility** counter-argument recorded. **D6.4
    (re-point, do not rebuild) still governs.**
* **`DECISIONS.md` — the MMR variant (§E1):** ours is **RRF-score relevance + Jaccard diversity**; the
  course's canonical MMR is **query–doc cosine + doc–doc cosine** (W7 §6.5). The λ band does not transfer;
  the **similarity measure**, not λ, is the suspect. Register it, and register the course's contradicting
  prediction (**MMR helps multi-hop**) so a negative is a departure that must be explained.
* Commit the **pooled re-embed code + its acceptance artifacts** — currently **uncommitted**.
* The Stage G pre-registration is committed alone (`3d3026e`); the run artifacts are not.
* ✅ **T0 IS PRE-REGISTERED — `.hermes/plans/2026-10-27-p1-t0-baseline-preregistration.md`** (written
  2026-10-27, **before the run**; **not yet committed**). It fixes the population (133, with the
  `vis-*` traceability-not-a-label trap), the **single arm = the product as shipped** (DA **and** graph
  **ON**, unlike Stage F/G), the four boundaries **with the score scale at each**, the **τ grid**
  ({0.0 … 0.9}, with 0.7 and 0.85 as the course's own examples), the metric set (MAP/precision@k/F1 to
  build), and guards **G1–G8** (G3 anchors on §I89's arm-B exact rows; G6 is the silent-lane guard).
  ⚠️ **The aperture VALUE is an OUTPUT of T0, not an input** — no τ is pre-committed.
  ⚠️ **A VERIFIER PER STAGE (§7b, V1–V5)** — base / cut / fusion / cross-encoder / the aperture sweep —
  each **independently re-deriving its stage from the raw per-query array** (stdlib, no harness helpers)
  and each **mutation-proved** before the run. **A stage whose verifier cannot fail is not verified.**
* **Each of T1–T3 is pre-registered and committed ALONE before its run** (D6.1), on the same pattern.

---

## Out of scope, and why (stated, not hidden)

| not included | why |
|---|---|
| the **visual (ColPali) lane** | `visual_knowledge_base` holds 1,033 points for the **old** doc `6d55c52b` only — there is no ColPali data for the new doc. And the **33 visual queries carry no `relevant_pages`**, which is exactly why the gold set is 133 and not 166. Including it needs a ColPali pass **and** new labels. |
| the **generator stage** | no synthesis, no judge in any of these tracks |
| a **cross-encoder fine-tune** | its ceiling is the pool it is handed, and the entire gap it could close is ~0.019 — under the floor |
| **S6, the embedder fine-tune** | it sharpens the lane the fusion discards. Parked until the fusion is fixed. |

## Carried forward (unchanged)

signoff 3 (re-confirm Shape B) · signoff 4 (accept the MRL-convention null) · the **A2 `.env` flip**
(owner action) · the **arm-2 harness** (`min_chunk_tokens` — the two untracked files are a fragment;
arm 2 is not built) · §I56's DA lane · §G2's V5 build · §G5/§I2 (`hop_distance` is a constant 0, so
"multihop" is nominal).
