# Stage G re-run: findings and design review

**Project:** Synapse Learning Worlds (`pdf_ingestion`) -- P1 retrieval evaluation
**Date:** 2026-10-26
**Subject:** the Stage G stage-decomposition re-run on the pooled index, plus three design questions it raised
**Status:** DIAGNOSTIC ONLY. This report ships nothing. The ship decision belongs to Stage F.

---

## What was measured, and why

The nomic index (`knowledge_base_v3`) originally embedded each chunk with **late chunking** (a child's
vector pooled from its parent's token vectors). The register measured that as costing **0.155** of
coverage versus the same model embedded plainly, and established that the loss is a **method** choice,
not a defect. The treatment was therefore to re-embed v3's dense lanes **pooled** (each chunk embedded
from its own text). That write is done and verified, and Stage G -- the stage-by-stage decomposition --
was re-run against the fixed index.

Everything below compares **two indexes of the same book**, on the same 3,489 chunks and the same 133
questions, so any difference is the index and nothing else.

---

# Part 1 -- The Stage G re-run, plainly

## 1.1 What we are comparing

    A = the incumbent index    (knowledge_base_v2, Qwen3 embedder, late-chunked)  <-- the baseline
    B = the new index          (knowledge_base_v3, nomic embedder, pooled)        <-- the candidate

Same chunks, same pages, same questions. Nothing else differs.

## 1.2 What the score means

**Coverage** = of the pages that could actually answer a question, how many did this stage put in front
of us? 0 = none, 1 = all.

"Could actually answer" matters. Each question has a list of correct pages, but the table-of-contents,
index and front-matter pages sit outside the window we search, so no retriever can ever return them. We
count only the correct pages the index *can* return. That is what makes A and B fairly comparable --
otherwise the book's structure, not the retrieval, moves the number.

## 1.3 W/L/T -- counted question by question

    B better than A = win    B worse = loss    same = tie
    67/8/58  ->  B won 67 questions, lost 8, tied 58

## 1.4 The noise floor, in one line

With 133 questions, differences smaller than about **0.02** are indistinguishable from luck. So "+0.004"
is not a small win -- it is no result. A confidence interval (CI) is the range the true difference
plausibly sits in; if that range crosses zero, we cannot tell the two apart.

## 1.5 The stage ladder

| stage | candidates in -> out | A (incumbent) | B (new) | B - A | W/L/T | verdict |
|---|---|---|---|---|---|---|
| 1. wide base (64d lane) | 3,489 -> 1,000 | 0.815 | 0.919 | +0.104 | 67/8/58 | B clearly better |
| 2. + full-dim re-rank (L=500) | 1,000 -> 500 | 0.748 | 0.838 | +0.090 | 60/19/54 | B clearly better |
| 3. + fusion (RRF -> 100 slots) | dense 500 + sparse + colbert -> 100 | 0.660 | 0.641 | -0.019 | 17/38/78 | B slightly WORSE |
| 4. + cross-encoder (top-20) | 100 -> 20 | 0.459 | 0.463 | +0.004 | 24/22/87 | no difference |

Stages 1-3 are real differences (bigger than the 0.02 floor). Stage 4 is not.

## 1.6 The story in three lines

1. The new index is clearly better at finding the right pages -- stages 1 and 2, +0.10 and +0.09,
   winning 67 questions and losing 8.
2. The fusion throws that advantage away. It merges three lanes into 100 slots, and two of those three
   lanes (keyword search and ColBERT) are identical in both indexes -- so the new index's better dense
   lane gets diluted to a slight net loss.
3. The cross-encoder then brings them back to level, which is exactly why the earlier product-endpoint
   run found no difference.

**One sentence:** the new index's advantage is real, but it does not reach the user -- the fusion, not
the embedder, is what blocks it.

## 1.7 Where to target next, in order

1. **The fusion.** It is the only stage with a real loss, and it is where the value dies. Three concrete
   things, none of them measured yet:
   - **Lane weighting.** Dense currently gets the same weight as the two lanes that are identical across
     indexes. Weighting dense higher is the most direct fix, and it is untested.
   - **Fusion output width** (the 100 slots). Raising it was tested at the endpoint and was a null, but
     the effect on the pool itself was never measured. Stage G now gives that pool curve.
   - **Split the loss** between RRF, page-dedup and MMR. It has never been attributed.
2. **Not the embedder. Not the ingestion.** Both sit upstream of the bottleneck -- improving them feeds
   a step that discards the gain.
3. **Therefore S6 (the fine-tune) is aimed at the wrong stage.** It would sharpen the lane the fusion
   throws away. Re-target it, or park it.

## 1.8 Why this is trustworthy

| check | result |
|---|---|
| arm A reproduced the previously recorded numbers | exactly -- all five rows, gap 0.000000000 |
| arm B's wide-base number matched the earlier independent pooled measurement | exactly (0.843325) |
| the product's own endpoint metric (R@20 over all correct pages) | A 0.4475 vs B 0.4513 -- level |

The first line is the load-bearing one: arm A shares nothing with the treatment, so if it moved,
nothing in the run would be attributable. It did not move.

---

# Part 2 -- Three design questions

## 2.1 Can we fine-tune the cross-encoder?

**Technically yes.** It is `BAAI/bge-reranker-v2-m3`, open weights, served by the cluster at
`10.0.10.70:8000/rerank/v1/rank` (or loadable locally via `sentence_transformers.CrossEncoder`).
Training a cross-encoder is standard -- (query, positive passage, negative passage) triples -- and the
raw material already exists: roughly 29k question cards, each paired with its source chunk. Hard
negatives would be mined from the pool itself, which is exactly what the CE sees at inference.

**But it is the wrong place to spend the effort**, for two measured reasons:

    its ceiling is the pool. The CE only reorders the 100 candidates the fusion emitted.
        Stage 3 (pool) covers 0.641 for B; stage 4 (top-20) 0.463. A page the fusion dropped
        can never be recovered, however good the CE is.
    its headroom here is under the noise floor. The CE was measured as a strong EQUALISER --
        it lifted the weaker arm +0.0888 and the stronger +0.0020. A better CE would help B a
        little more than A, but the entire gap it could close is the pool gap: 0.019.
        Our floor is 0.02. So even a perfect CE cannot produce a measurable win.

**Verdict:** trainable, but not the bottleneck, and its measurable headroom here is about 0.01-0.02 --
below the floor. Skip for now.

## 2.2 How do we address the loss at the fusion stage?

Three concrete levers, and one that must come first.

**(b) Attribute it first** -- cheapest, and it decides between the other two.

    The fusion does three things in sequence: RRF -> page dedup -> MMR. Nobody has ever
    measured which of the three causes the loss. One ablation at pool level: coverage with
    (i) RRF only, (ii) RRF + dedup, (iii) RRF + dedup + MMR (= the product). Whichever step
    drops it names the fix.

    Leading suspect, flagged as a HYPOTHESIS not a finding: MMR. MMR deliberately penalises
    "redundant" candidates, and a page with many relevant chunks looks exactly like redundancy.
    Since our metric is page-level, MMR could be systematically suppressing the very pages we
    count. That would be a very different fix from lane weighting.

**(a) Lane weighting** -- if the loss is dilution.

    Today the fusion is plain unweighted RRF: every lane contributes 1/(k+rank). Sparse and
    ColBERT are model-independent, so they are identical in both indexes and contribute identical
    mass to every candidate -- which dilutes the dense lane, the only lane that differs between
    the arms. A weighted RRF (w_dense/(k+rank) + ...) is a small change to one function and its
    call site. Untested. It only helps if the dense lane really is better -- and stages 1-2 say
    it is.

**(c) Fusion width** (the 100 slots) -- already tested at the endpoint (null), but the pool-level
effect was never measured. Stage G now gives the pool number at width 100, so sweeping the width and
watching pool coverage is cheap. Expected shape: pool coverage rises with width while the endpoint
stays flat. That is a mechanism finding, not a ship.

**Order:** (b) first, then (a) or (c) depending on what (b) says. All three need a pre-registration and
an endpoint check.

## 2.3 Is recall the right diagnostic at the fusion and reranker level?

**No -- it is right at the fusion and wrong at the reranker**, and the difference matters.

    At the FUSION, the pool's job is INCLUSION: do not drop a page that should be in play.
        So coverage/recall is exactly the right instrument -- and our finding IS a recall loss
        (pages dropped), so the instrument matches the claim.

    At the RERANKER, the job is ORDERING. The candidate set is already fixed by the pool; the CE
    only decides what comes first. Recall@20 is a thresholded view of ordering -- it cannot tell
    "ranked 1st" from "ranked 19th". So recall is the wrong sole measure there.

    Use a rank-aware metric at that stage: MRR and nDCG@20. Both are ALREADY implemented in the
    product's own metric function -- they are simply not being used in Stage G.

This is not theoretical. A previous width experiment is the direct evidence: on the same data, MRR
resolved POSITIVE (+0.0935) while context precision resolved NEGATIVE, and R@20 was unresolved. The
width reordered the pool without changing inclusion -- recall was blind to the entire effect.

**A real limitation this exposes in the table above:** stage 4's "+0.004, no difference" is an
INCLUSION statement, not a RANKING statement. Stage G has no MRR or nDCG, so we cannot currently see
whether the cross-encoder orders better or worse between the two indexes. That is a gap, and it is
cheap to close.

    WARNING if we add it: the cluster reranker SWALLOWS failures and returns the pool UNRANKED.
    Any MRR/nDCG number is only valid when the reranked-metrics-valid flag is true and the
    fallback count is zero -- otherwise the metric silently flattens. Gate it.

---

# Part 3 -- What is NOT measured

| not measured | why |
|---|---|
| the DA and graph lanes | OFF in both arms -- both derived collections are 768-dim nomic-only, so a 1024-dim arm cannot query them. Stages 3-4 are the product funnel MINUS two recall lanes. |
| the generator stage | no synthesis, no judge in this run |
| RAPTOR | not in v3 (a separate step), and not on the eval path at all |
| ranking quality (MRR / nDCG) per stage | not computed by Stage G -- see 2.3 |
| the fusion's internal attribution | the split between RRF, page-dedup and MMR is unmeasured -- see 2.2(b) |
| cross-encoder training | never attempted; headroom argued, not measured |

**Standing caveats:** the stage-1 comparison is NOT like-for-like (arm A is Qwen3 late-chunked, arm B
is nomic pooled -- two differences). The like-for-like pooled-vs-pooled contrast was measured
separately at +0.0362, resolved. And this is one document, one day, one funnel -- no causal claim
beyond these two indexes.

---

# Part 4 -- Recommended next steps, in order

1. **Add MRR and nDCG@20 to the stage ladder and re-run Stage G.** Cheap, read-only, and it makes the
   cross-encoder stage say something instead of nothing. Gate on the reranked-metrics-valid flag.
2. **Run the fusion attribution ablation** -- RRF vs dedup vs MMR -- because that is where the only
   resolved loss lives, and it decides which fix to build.
3. **Only then build a fusion fix** (lane weighting, or the dedup/MMR step the ablation fingers), and
   validate it at the pool AND at the product endpoint.
4. **Leave the cross-encoder alone** for now.
5. **Park S6 (the embedder fine-tune)** -- it aims at a lane the fusion discards.

---

# Part 5 -- Direction agreed (a plan, not a measurement)

**Adopt nomic going forward, then fix the fusion -- in that order.** The reason is specific: Stage G
shows nomic's advantage is large upstream and dies at the fusion, so fixing the fusion is only worth
doing if there is a real upstream gain for it to deliver. On the current incumbent there is not.

**Why adopting nomic is cheap now.** The re-embed reused the existing chunk ids, so the whole derived
layer is already valid for the new index -- cards, the 73,406 derivative artifacts and the 6,065 concept
embeddings are all keyed on `chunk_id`, and those ids did not change.

| what | state | cost |
|---|---|---|
| v3 dense lanes | pooled, verified | done |
| colbert + sparse | carried over, byte-identical | done |
| cards / DA / graph | keyed on unchanged chunk ids | valid as-is |
| intent classifier | retrained for nomic | done |
| RAPTOR nodes | v3 has 0, v2 has 73 | minutes -- a copy + re-embed (a write) |
| the .env flip | not applied; the app still defaults to the old embedder | minutes (owner action) |

Two small steps, not a full re-ingest.

**Then, before the fusion is touched, the lane set is completed and the comparison made fair:**

| # | task |
|---|---|
| A | the **per-space query-vector fix** -- lets a 1024-dim arm query the 768-dim derived lanes, so the derived layer becomes a held-constant across arms instead of the confound that forced the question to be narrowed |
| B | **RAPTOR into v3** (a write) **+ wire the overview lane** into the eval -- it has never been called there |
| C | add **MRR and nDCG@20** to the stage ladder -- recall cannot see ordering, and ordering is a reranker's whole job |
| D | three measurement tracks: **base-lane A/B** (the narrowed ship test) · **nomic-only lane ablation, per type** · **full-funnel A/B** (the ship test that was left unmeasured) |
| E | **then** attribute the fusion loss (RRF vs page-dedup vs MMR) and fix it, validated at the pool **and** the endpoint |

**One expectation to hold.** The lanes are unlikely to rescue the endpoint. DA is a measured **harm**
(-0.0262 on top-20 R@20); the graph lane **bypasses the fusion entirely** (its hits are appended after
the fusion, so it cannot repair a fusion loss); and because the derived lanes are identical across arms
they **dilute** the dense-lane difference. Including them makes the comparison **complete**, not
favourable -- the null gets more likely, not less.

**And one thing to be honest about if nomic is adopted now:** record it as a **cost-and-upstream**
decision, not an accuracy win. The only product-endpoint measurement we have was a null, and R@100 was
resolved **negative** for nomic. Adopting it is still right -- level at the endpoint, much better
upstream, cheaper, and it is the only index that can use the DA and graph lanes. Just do not later
restate it as "nomic improved things".

---

# Appendix -- provenance

| item | value |
|---|---|
| Stage G re-run artifact | `logs/p1/step10/stageG_decomposition.json` (sha256 8a2fd64b317f2d22...) |
| per-arm artifacts | `stageG_arm_A.json`, `stageG_arm_B.json`, `stageG_run_session20.txt` |
| prior run preserved | `stageG_*_session20_latechunked.json` (the late-chunked decomposition) |
| pre-registration | `.hermes/plans/2026-10-26-p1-stageG-rerun-preregistration.md`, committed alone as `3d3026e` |
| the pooled re-embed | `scripts/reembed_chunks.py --from-collection knowledge_base_v2 --pooled`; 3,796 points / 341 parents / 0 failures / 91.9 s |
| its acceptance evidence | `logs/p1/step10/pooled_reembed_{pre,post,carryover}.json` (post sha256 3d751cf9ce5a8d4f...) |
| guards | 8/8 pass, including arm A bit-exact against the prior run (gap 0.000000000) and arm B reproducing the pooled reference (gap 0.000000) |

Model: deepseek/deepseek-v4.1-flash
