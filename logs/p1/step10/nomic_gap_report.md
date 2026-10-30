# nomic retrieval evaluation — where the gap is

> **FINAL — 2026-10-27.** Metrics with **both ceilings** (`P-ceil` and `R-ceil`), the per-type split, what
> is not measured, and the decisions. Every figure re-verified against its artifact before this version.
> Engineering record: `IMPROVEMENTS.md` §I89–§I94a · `DECISIONS.md` §8.

**Scope.** One embedder (**nomic-embed-text-v1.5**), one index (`knowledge_base_v3`, 3,796 chunks / 888
pages), one corpus (one undergraduate physics textbook), **133 labelled queries**, HyDE on and frozen,
read-only. Two registered measurements:

* **v0 = T0** — the **full funnel**: base lane (64d) → full-dim re-score + cut to 500 → fusion pool →
  cross-encoder top-20.
* **v1 = T1** — the **product endpoint on the base lanes only** (same index, two fewer lanes).

⚠️ **Which lanes were actually live — stated because it is easy to assume otherwise.** The **dense**,
**sparse (SPLADE)** and **ColBERT** lanes are **fused** (reciprocal rank fusion). The **DA lane** is
**merged inside the fusion**, before dedup and MMR. The **graph lane is NOT fused** — its hits are
**appended to the pool after the fusion** (so they never pass through RRF, dedup or MMR, and cannot
displace a fused hit). **RAPTOR is in neither run**: it is absent from this index and the evaluation path
never calls it. In v1, DA and the graph lane are **off**; everything else is identical.

---

## 1. The headline

1. **Coverage — how much of the answer set the system returns — falls from 0.919 to 0.455 across the
   funnel.** The two big drops are the fusion pool (−0.154) and the last stage, pool → top-20 (−0.229).
2. **The last stage also destroys ordering.** nDCG, MAP and MRR all **peak at the fusion pool and fall**
   at the cross-encoder — and that is not a uniform effect: it is driven by **factual** queries.
3. **Overview is a different failure with a different fix** — and its raw number overstates it. It has the
   **worst recall** of the three types and the **best ordering** (a missing-lane problem, not a ranking
   problem) — but against its own recall ceiling it is at **47 % of achievable, not the 3× worse the raw
   figures suggest** (see §3).

---

## 2. v0 — the funnel, every metric at every stage

n = 133. `coverage` = share of a query's **reachable** labelled pages present at that stage (the ceiling
check). `pool` = pages available at that stage. All metrics page-deduped.

| stage | coverage | pool | R@20 | R@100 | P@20 | P-ceil | P@20 / ceil | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base — dense 64d lane | **0.9190** | 512.8 | 0.3548 | **0.8979** | 0.1624 | 0.4846 | 34 % | 0.1333 | 0.3931 | 0.2315 | 0.5875 | 0.8872 |
| full-dim re-score, cut 1000→500 | 0.8381 | 303.5 | 0.4242 | 0.8177 | 0.2049 | 0.4846 | 42 % | 0.1699 | 0.4919 | 0.2925 | 0.7242 | 0.9248 |
| fusion pool | 0.6845 | 86.5 | **0.4491** | 0.6706 | **0.2447** | 0.4846 | **51 %** | **0.1968** | **0.5506** | **0.3421** | **0.7687** | **0.9323** |
| cross-encoder → top-20 | **0.4553** | 19.9 | 0.4442 | 0.4442 † | 0.2398 | 0.4846 | 49 % | 0.1911 | 0.4946 | 0.2789 | 0.6668 | 0.9173 |

`P-ceil` is the **precision ceiling** — `min(labelled pages, 20) / 20`, the highest `P@20` this query can
produce — and it is a property of the **labels**, not of the system, so it is **identical in every row and
every arm**. ⚠️ **Read precision against its ceiling, never raw:** 0.240 looks like failure and is actually
**half of what is achievable**.

⚠️ **Recall carries a ceiling too — `R-ceil@20 = min(20, n)/n`, 0.7858 overall** — and it is the mirror of
`P-ceil`: whichever of *n* (answers that exist) and *k* (slots you show) is **smaller** sets the cap.
**45 of the 133 queries are recall-capped; 88 are precision-capped.** ⚠️ **This matters for how every
`R@20` in this report is read** — raw, overview (0.188) looks 3× worse than factual (0.557), but against
their own ceilings they are **47 % and 59 %**. The per-type table in §3 carries both. ⚠️ **Do not quote a
recall without its ceiling** any more than a precision.

⚠️ **A caveat on the `P@20 / ceil` column, because it is not one quantity.** Algebraically the ratio is
`|relevant ∩ top-20| / min(|labelled|, 20)`, so it resolves to **two different metrics depending on the
query**: for a query whose gold set is **smaller than 20**, `min(|labelled|, 20) = |labelled|` and the ratio
**is exactly `recall@20`** (verified: 0 violations over the 88 such queries × 4 stages); for a query with
**20 or more** labelled pages it **is precision itself**. ⇒ **the aggregate ratio mixes both regimes** and
should be read per query, or not at all — the honest headline stays `P@20` against `P-ceil`, which is what
the ratio column is there to make visible.

† The cross-encoder stage holds only the 20 reranked chunks, so `R@100` there equals `R@20` **by
construction**. The pool-recall figure comparable to v1's `R@100` is the **fusion row's 0.6706**.

**What the second row is, and what it is not.** It is a **coarse-to-fine cascade inside the dense lane**:
shortlist 1,000 candidates at **64 dimensions** (the first 64 of the same 768-dim vector, re-normalised —
a Matryoshka truncation), then **re-score those same 1,000 at all 768 dimensions** and keep the best 500.
Same embedding twice at two widths — **not** a second model, and **not** the cross-encoder, which is the
last row. ⚠️ **The row moves two things at once, in opposite directions:** the re-score **improves** the
ordering (nDCG 0.3931 → 0.4919, MRR 0.5875 → 0.7242) and top-20 inclusion (R@20 0.3548 → 0.4242), while
the **cut from 1,000 to 500 candidates is what costs the coverage** (0.9190 → 0.8381). Read the coverage
drop as the **cut**, not as a cost of re-scoring.

**Read the table in two halves, because they disagree — and that is the point of having both.**

| family | metrics | shape across the funnel |
|---|---|---|
| **inclusion** — *did we get the pages?* | coverage, R@100, R@20, Hit@20 | best early, **falls to the endpoint** |
| **ordering** — *are they in the right order?* | nDCG@20, MAP, MRR | **peak at the fusion pool**, then fall |

* **Ordering peaks at the pool and is thrown away at the last stage:** nDCG **0.5506 → 0.4946**,
  MAP **0.3421 → 0.2789**, MRR **0.7687 → 0.6668**.
* **Inclusion falls at the same stage:** coverage **0.6845 → 0.4553**, R@100 **0.6706 → 0.4442**.
* **Recall@20 barely moves** (0.4491 → 0.4442) and **Hit@20 barely moves** (0.9323 → 0.9173). So a
  recall-only report would have called this stage a non-event. It is the worst stage in the funnel.

**Precision@20 is ceiling-bound, not a quality signal — and the ceiling differs sharply by type.**

| type | labelled pages per query (min / median / max) | P-ceil |
|---|---|---|
| factual | 1 / 3 / 134 | **0.3000** |
| overview | **22 / 56.5 / 314** | **1.0000** |
| multihop | 1 / 3 / 13 | **0.2137** |

The ceiling is `min(labelled pages, 20) / 20`, averaged over the type — a property of the **gold labels**,
not of the system, so it is **identical in every stage and every arm**. **Overview queries carry at least
22 labelled pages each**, which is why their ceiling is a full 1.0 and why their raw `P@20` (0.51) looks
far better than factual's (0.14) while both sit at about the same fraction of what is achievable.

⚠️ **Read precision as a fraction of its ceiling, never raw.** Measured that way the system is remarkably
uniform — **every type sits at roughly half its ceiling** (endpoint: factual 45 %, overview 51 %, multihop
49 %; pool: 48 % / 53 % / 43 %). That is the honest reading: precision is **not** where the types differ,
and it is **not** a lever, because the ceiling moves with the labels rather than with the system.

---

## 3. v0 — per query type

**At the endpoint (cross-encoder top-20):**

| type | n | coverage | R@20 | P@20 | P-ceil | P@20 / ceil | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.5577 | 0.5574 | 0.1358 | **0.3000** | 45 % | 0.1633 | 0.4524 | 0.3206 | 0.5178 | 0.8679 |
| **overview** | 40 | **0.1937** | **0.1882** | 0.5125 | **1.0000** | 51 % | 0.2579 | 0.5379 | 0.1265 | **0.8021** | 1.0000 |
| multihop | 40 | 0.5813 | 0.5500 | 0.1050 | **0.2137** | 49 % | 0.1612 | 0.5072 | 0.3761 | 0.7291 | 0.9000 |

**At the fusion pool (the stage before it):**

| type | n | coverage | R@20 | R@100 | P@20 | P-ceil | P@20 / ceil | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.8115 | 0.5830 | 0.8110 | 0.1443 | 0.3000 | 48 % | 0.1733 | **0.5885** | **0.4689** | **0.7690** | 0.9057 |
| overview | 40 | 0.5221 | 0.2103 | 0.5084 | 0.5312 | 1.0000 | 53 % | 0.2817 | 0.5750 | 0.1557 | 0.8723 | 1.0000 |
| multihop | 40 | 0.6786 | 0.5106 | 0.6466 | 0.0912 | 0.2137 | 43 % | 0.1431 | 0.4761 | 0.3604 | 0.6646 | 0.9000 |

⚠️ **Recall has its own ceiling, and we had been quoting only precision's.** Recall is capped whenever a
query has **more** labelled pages than there are slots: `R-ceil@k = min(k, n)/n`. It stacks with
reachability, so the honest denominator is `min(k, |reachable|) / |labelled|`:

| type | R@20 | **R-ceil@20** | R@20 / R-ceil | P-ceil@20 |
|---|---|---|---|---|
| factual | 0.5574 | 0.9494 | **58.7 %** | 0.3000 |
| multihop | 0.5500 | 0.9556 | **57.6 %** | 0.2137 |
| **overview** | 0.1882 | **0.3992** | **47.2 %** | 1.0000 |
| all 133 | 0.4442 | 0.7858 | 56.5 % | 0.4846 |

⚠️ **This changes how overview's number must be read.** Raw, overview (0.188) looks ~3× worse than factual
(0.557) — but its recall ceiling is 0.399 against factual's 0.949, because overview queries carry 22–314
labelled pages and only 20 can be shown. **Against their own ceilings the three types are 47 %, 59 % and
58 %.** Overview is still the worst, and still needs its lane — but **the raw figures overstate that gap
by roughly 3×**, and any statement of the form "overview recall is 0.19" without the ceiling is
misleading. **45 of the 133 queries are recall-capped this way; 88 are precision-capped.**

**The pool → endpoint step, per type** — and the three types behave in **opposite directions**:

| type | R@20 | nDCG@20 | MAP | MRR | what it means |
|---|---|---|---|---|---|
| factual | 0.5830 → 0.5574 | **0.5885 → 0.4524** | **0.4689 → 0.3206** | **0.7690 → 0.5178** | recall holds, **ordering collapses** → a **ranking** problem |
| overview | 0.2103 → 0.1882 | 0.5750 → 0.5379 | 0.1557 → 0.1265 | 0.8723 → 0.8021 | **few pages to begin with** → a **retrieval** problem |
| multihop | 0.5106 → **0.5500** | 0.4761 → **0.5072** | 0.3604 → **0.3761** | 0.6646 → **0.7291** | **improves** at this stage |

⚠️ **This is the most decision-relevant table in the report.** The aggregate said "the last stage is the
worst"; the per-type split says the last stage is **hurting factual (53 queries), merely not helping
overview, and actively helping multihop (40 queries)**. Those need different fixes.

**Overview, read correctly.** It has the **lowest recall** of the three (R@20 0.1882) and the **highest
nDCG and MRR** (0.5379 / 0.8021) — i.e. *when it finds a relevant page it puts it first; it just rarely
finds one.* Low recall **with high nDCG** is a **retrieval** problem, not a ranking problem. The type's
own lane — RAPTOR summary nodes — is **absent from this index and not on the evaluation path at all**,
which is the obvious candidate cause.

---

## 4. v1 — the endpoint on the base lanes (and what the two extra lanes do)

Same index, same queries, same instrument. **Only difference: DA and the graph lane are off.**

| measurement | v0 (DA + graph ON) | v1 (base lanes only) |
|---|---|---|
| pool recall (`R@100` at the pool) | 0.6706 | 0.6279 |
| **endpoint R@20** | 0.4442 | 0.4513 |
| endpoint nDCG@20 | 0.4946 | 0.5023 |
| endpoint MAP | 0.2789 | 0.2828 |
| endpoint **MRR** | 0.6668 | **0.7805** |
| endpoint Hit@20 | 0.9173 | 0.9248 |
| endpoint P@20 | 0.2398 | 0.2470 |
| endpoint P-ceil (identical by construction) | 0.4846 | 0.4846 |
| endpoint P@20 / ceil | 49 % | **51 %** |
| endpoint **F1@20** | 0.1911 | **0.1957** |

**v1 per query type:**

| type | n | R@20 | R@100 | P@20 | P-ceil | P@20 / ceil | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.5782 | 0.7882 | 0.1415 | 0.3000 | 47 % | 0.1708 | 0.4641 | 0.3269 | 0.7693 | 0.8868 |
| overview | 40 | 0.1947 | 0.4316 | 0.5312 | 1.0000 | 53 % | 0.2668 | 0.5519 | 0.1319 | 0.8958 | 1.0000 |
| multihop | 40 | 0.5397 | 0.6120 | 0.1025 | 0.2137 | 48 % | 0.1575 | 0.5034 | 0.3751 | 0.6799 | 0.9000 |

**What the two extra lanes buy: more pages, worse ordering.** They raise pool recall (0.6279 → 0.6706)
but the endpoint does not follow — and **MRR falls sharply (0.7805 → 0.6668)**. The mechanism is visible
in the code: the DA lane's pages are merged **inside** the fusion and compete normally, but the **graph
lane's hits are appended after the fusion**, so they cannot be ordered by it. Adding pages the ranking
cannot place lowers the position of the first correct answer.

⚠️ **Caveat, stated:** this comparison spans **two runs** with the same instrument (both use the product's
own retrieval and metric functions, and both runs' instruments were pinned against registered anchors),
but the lane set is the only intended config difference. The direction agrees with the earlier measured
finding that the DA lane is a **harm** on top-20 recall.

---

## 5. Where the gap is — focus areas, in order

**1. ✅ ATTRIBUTED (T4, §I97) — the pool → top-20 step: it is the cross-encoder, and on factual queries
it is the HyDE hypothetical being used as the cross-encoder's query.**
The step's loss (nDCG 0.5885 → 0.4524, MAP 0.4689 → 0.3206, MRR 0.7690 → 0.5178 on 53 factual queries,
recall flat) has been separated into its three candidate causes, all measured, all resolved:

| cause | evidence | fix |
|---|---|---|
| **the CE reorders worse than the pool's own order** | removing it: nDCG **+0.0560**, MAP **+0.0631**, MRR **+0.1011** (n=133, all resolved); **recall and hit unchanged** | — |
| ⚠️ **the CE is fed the HyDE hypothetical, not the question** | the raw query instead: nDCG **+0.0430**, MAP **+0.0561**, MRR **+0.0699** (resolved) | **one line, `evaluate_rag.py:206`** |
| the 20-slot cut | widening to 50: coverage **+0.1451** (resolved) | a deliberate context budget — **no action** (§I67) |

⚠️ **And the fix is PER TYPE.** On **factual** queries the hypothetical is essentially the whole cause
(N−C nDCG +0.1361 and Q−C +0.1397, both resolved — Q ≈ N), so **feeding the CE the raw query recovers it
without removing the CE**. On **overview** the hypothetical is the *better* query (Q−C negative,
unresolved at n=40), so **do not apply the factual fix there**. On **multihop** HyDE is not used at all —
Q ≡ C **exactly, 40/40**, a free internal consistency check the run passed.
**Next action: a pre-registered before/after for the per-type rerank-query policy. No `src/` change yet.**

**2. Overview queries — a missing lane, not a ranking problem.**
R@20 0.1882 against 0.5574 (factual) and 0.5500 (multihop); coverage 0.1937. Its nDCG and MRR are
already the best of the three, so better ranking cannot help it. Its lane (RAPTOR summaries) is absent
from the index and never called on the evaluation path. **Next action: build the lane and wire it in.**

**3. Precision is ceiling-bound — and F1 inherits it. Do not optimise either directly.**
P@20 is 0.240 against a ceiling of 0.485 that moves with the gold set, not with the system. **F1@20
(0.1911) is the harmonic mean of that precision and a recall of 0.4442, so it is pinned by the precision
side** — it can only improve if precision does, and precision is capped by the labels. Both belong in the
report as context numbers. **No action.**

**4. The DA and graph lanes, as currently wired, are not paying for themselves.**
They add pool pages but lower MRR at the endpoint. **Action: reconsider the graph lane's placement** — it
bypasses the fusion by construction, so it can only ever append unordered candidates.

**5. The fusion pool's 100-slot cap costs 0.154 of coverage — and it is not a lever.**
Lifting the cap to 500 recovers that coverage at the pool, but a **prior measurement of the same change at
the endpoint returned no improvement**, and the last stage discards the extra pages anyway. **Recorded, no
action.**

---

## 6. Glossary — the metrics this report turns on

**Provenance, stated up front because two of these are not course metrics.** Checked against the course's
own documents (`Week_Summary/*.pdf`, `Slides/*.pdf` — all 21 searched):

* **`recall@k`, `precision@k`, `F1@k`, `MRR`, `MAP`, `nDCG@k` are the course's own metrics** — Week 7
  §3.1 (precision and recall), §3.4 (F1), §4.3 (MRR), §4.6 (MAP), §5.5 (nDCG).
* ⚠️ **`P-ceil` is also the course's** — Week 7 **§3.3 "The Mathematical Ceiling of Precision"**: *"when
  n < k, Precision@k has a hard ceiling of n/k … the total population of relevant documents n must always
  be reported alongside the metric."* Our ceiling is that quantity.
* ⚠️ **`coverage` is NOT a course metric, and the course uses the same word for something else** — Week 8
  §19.1: *"Coverage: The proportion of total user queries the system attempts to answer"* (the
  risk–coverage curve of abstention). **Ours must always be written in full** — *coverage of a query's
  reachable labelled pages* — never as bare "coverage".
* **The concept behind `coverage` is the course's, under a different name** — Week 10 §7.1, *"The Recall
  Ceiling"*: *"if the initial bucket scoop misses a marble entirely, absolutely no downstream sieve can
  recover it."* Our `coverage` is that doctrine as a per-stage number.

| metric | the question it answers | how to read it here |
|---|---|---|
| **coverage** | *Of the pages this stage could possibly reach, how many did it actually return?* | The ceiling check. It cannot exceed 1 and it never depends on the ordering. Use it to see **where pages are lost**; it says nothing about order. |
| **recall@k** | *Of the pages that contain the answer, how many are inside the top k?* | **Inclusion.** Rises to 0.449 at the pool and flattens at 0.444 — recall alone would call the last stage harmless. ⚠️ **It has a ceiling too**, `min(k, n)/n`, whenever a query has more labelled pages than slots: 0.9494 factual / 0.9556 multihop / **0.3992 overview**, so quote it against that. Always report with k. |
| **precision@k** | *Of the top k, how many are actually gold?* | The mirror of recall. **Must be quoted with its ceiling**, or it reads as failure when it is at capacity. The ceiling is `min(labelled pages, k)/k` — **0.4846 overall, but 0.3000 factual / 1.0000 overview / 0.2137 multihop**, because the types carry very different numbers of labelled pages. **Read the ratio:** every type sits at ~half its ceiling, so precision is uniform across types and is not a lever. |
| **F1@k** | *What is the balance of precision and recall in the top k?* | The harmonic mean of the two. ⚠️ **Derived, so it cannot tell you which side moved** — here it is pinned by precision (F1 0.1911 sits next to P@20 0.2398 and R@20 0.4442, so precision is the limiting side). Read it as a **summary**, never as a diagnosis. |
| **hit@k** | *Did the student get **anything** useful in the top k?* | The **floor**, not the quality: 0.92 here while coverage is 0.46. High hit@k means "never empty", not "answered". |
| **MRR** | *How high is the **first** correct page?* | **Ordering, first answer only.** 0.769 at the pool → 0.667 at the endpoint. Sensitive to one good page; blind to everything after it. |
| **MAP** | *How good is the ordering across **all** correct pages?* | **Ordering, breadth-aware.** 0.342 → 0.279. Falls when correct pages sit below incorrect ones, however many there are. |
| **nDCG@k** | *How good is the ordering, weighted by position?* | **Ordering, rank-weighted headline.** 0.551 → 0.495. Compare it against recall: **high nDCG with low recall = a retrieval problem; high recall with low nDCG = a ranking problem.** That pair is what splits overview from factual in §3. |

**Deliberately excluded, and why:** `context_precision` (chunk-unit with a denominator that moves with
the pool width — a diagnostic, not a decision metric); `AUC-PR` (a curve metric with no curve to report
at this scope).

**One convention to keep straight.** All metrics are **page-deduped** and counted as *pages of the top-k
chunks* — not "the top k pages". The two differ by ~0.02 and are not interchangeable. And at the
cross-encoder stage the pool holds only 20 chunks, so `R@100` there equals `R@20` by construction; the
pool-recall figure is the fusion row's.

---

## 7. What this report does NOT measure

Stated so the boundaries are not read as coverage we do not have.

* **The full funnel (v2 vs v3, all lanes).** Both measurements here are single-index. The cross-index
  comparison needs the DA and graph lanes to be queryable by **both** arms, which needs the per-space
  query-vector fix — the derived collections are 768d and a 1024d arm cannot query them.
* **The overview lane (RAPTOR).** Absent from this index and **never called on the evaluation path** —
  which is why the overview type's fix is a build, not a tuning.
* **The graph lane's own contribution.** It is **appended after the fusion by construction**, so it is not
  isolated by either run; the v0-vs-v1 difference measures the DA and graph lanes **together**.
* **The visual (ColPali) lane.** No page data for this document, and the 33 visual queries carry no labels
  (which is why the gold set is 133, not 166).
* **The generator stage.** No synthesis, no judge, no answer quality — retrieval only.
* **Graded relevance.** The labels are **binary**, so `nDCG` here is **rank-weighted recall**, not the
  graded apex metric. A page-level 0/1/2 scheme would be a **new artifact beside** these labels.
* **The label set is as-is.** 3 labels are contents-page *pointers* (measured effect below the floor);
  they are **unrepaired**, and no metric here is adjusted for them.
* **One document, one day, one funnel.** No claim beyond these two indexes.

---

## 8. Decisions

**Settled by these measurements.**

1. **The pooled index ships nothing at the endpoint.** Its base-lane advantage (+0.104; like-for-like
   +0.0362) is worth **+0.0039, unresolved**, ~6× below the resolution floor. **The funnel discards it.**
2. **The fusion's −0.154 loss is the 100-slot cap, and MMR is innocent** (MMR off at the shipped width:
   +0.0032, unresolved; at width 500: **exactly 0.000000**). ⚠️ **Do not ship the width** — the same
   change was already measured at the endpoint and returned no improvement.
3. **`P-ceil` and `R-ceil` are the course's own metrics** (Week 7 §3.3; the deck's slide 25) and are
   quoted beside every precision and recall. ⚠️ **`coverage` is ours** and must always be written in full
   — *coverage of a query's reachable labelled pages* — because the course uses "coverage" for the
   abstention rate.
4. **No bulk label rule.** **26 of the 29** contents-page labels are **correct** (5 of them are questions
   whose answer *is* the contents page); **3 are pointers**, and the measured effect of changing them is
   below the floor. **Deferred as hygiene.**
5. ✅ **The endpoint's loss is the cross-encoder, and on factual queries the cause is its query text**
   (T4, §I97, 14/14 guards, all three predictions confirmed). Removing the CE improves nDCG +0.056,
   MAP +0.063 and MRR +0.101 at **no recall cost**; feeding it the **raw query** instead of the HyDE
   hypothetical recovers 77 % of that on its own. ⚠️ **The fix is per type** — raw for factual, keep the
   hypothetical for overview — and **nothing in `src/` has been changed**: this licenses a separately
   pre-registered before/after, not an edit.

**Ranked next work.**

| # | action | what it moves | status |
|---|---|---|---|
| 1 | **Ship the per-type rerank-query policy** — the raw query for factual, keep the HyDE hypothetical for overview | **nDCG +0.14, MRR +0.26 on factual (n=53, resolved)**; overall +0.043 nDCG | **attributed by T4 (§I97); the largest measured lever so far.** Pre-register the before/after — **no `src/` change yet** |
| 2 | **Per-space query-vector fix**, then RAPTOR into the index and wired into the eval | unblocks the cross-index comparison; targets overview (R@20 0.188, ceiling 0.399) | build |
| 3 | **Lane ablation per type** | each lane's own contribution | pre-register |
| 4 | **Lane weighting** in the fusion | the model-independent lanes' dilution | after 1–3 |

**Explicitly no action:** precision and F1 (ceiling-bound — every type sits at ~half its ceiling, and the
ceiling moves with the labels); the fusion width (measured inert at the endpoint); the DA/graph lanes *as
currently wired* (they add pool pages and **lower MRR** 0.781 → 0.667 — the action is #2's re-placement,
not a tuning).

**Owner items still outstanding:** the `A2 .env` flip (every stage runs on env exports); signoff 3
(re-confirm Shape B); signoff 4 (accept the MRL-convention null); whether to re-run this report if any
label change is ever applied (comparability).
