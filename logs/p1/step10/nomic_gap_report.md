# nomic retrieval evaluation — where the gap is

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
3. **Overview is a different failure with a different fix.** It has the **worst recall** of the three
   types and the **best ordering** — a missing-lane problem, not a ranking problem.

---

## 2. v0 — the funnel, every metric at every stage

n = 133. `coverage` = share of a query's **reachable** labelled pages present at that stage (the ceiling
check). `pool` = pages available at that stage. All metrics page-deduped.

| stage | coverage | pool | R@20 | R@100 | P@20 | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| base — dense 64d lane | **0.9190** | 512.8 | 0.3548 | **0.8979** | 0.1624 | 0.1333 | 0.3931 | 0.2315 | 0.5875 | 0.8872 |
| full-dim re-score, cut 1000→500 | 0.8381 | 303.5 | 0.4242 | 0.8177 | 0.2049 | 0.1699 | 0.4919 | 0.2925 | 0.7242 | 0.9248 |
| fusion pool | 0.6845 | 86.5 | **0.4491** | 0.6706 | **0.2447** | **0.1968** | **0.5506** | **0.3421** | **0.7687** | **0.9323** |
| cross-encoder → top-20 | **0.4553** | 19.9 | 0.4442 | 0.4442 † | 0.2398 | 0.1911 | 0.4946 | 0.2789 | 0.6668 | 0.9173 |

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

**Precision@20 is ceiling-bound, not a quality signal.** It reads 0.240 at the endpoint against a
**ceiling of 0.485** — the ceiling is a property of the gold labels (how many pages each query has), not
of the system. It must always be quoted with the ceiling; on its own it looks like failure.

---

## 3. v0 — per query type

**At the endpoint (cross-encoder top-20):**

| type | n | coverage | R@20 | P@20 | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.5577 | 0.5574 | 0.1358 | 0.1633 | 0.4524 | 0.3206 | 0.5178 | 0.8679 |
| **overview** | 40 | **0.1937** | **0.1882** | 0.5125 | 0.2579 | 0.5379 | 0.1265 | **0.8021** | 1.0000 |
| multihop | 40 | 0.5813 | 0.5500 | 0.1050 | 0.1612 | 0.5072 | 0.3761 | 0.7291 | 0.9000 |

**At the fusion pool (the stage before it):**

| type | n | coverage | R@20 | R@100 | P@20 | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.8115 | 0.5830 | 0.8110 | 0.1443 | 0.1733 | **0.5885** | **0.4689** | **0.7690** | 0.9057 |
| overview | 40 | 0.5221 | 0.2103 | 0.5084 | 0.5312 | 0.2817 | 0.5750 | 0.1557 | 0.8723 | 1.0000 |
| multihop | 40 | 0.6786 | 0.5106 | 0.6466 | 0.0912 | 0.1431 | 0.4761 | 0.3604 | 0.6646 | 0.9000 |

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
| endpoint **F1@20** | 0.1911 | **0.1957** |

**v1 per query type:**

| type | n | R@20 | R@100 | P@20 | F1@20 | nDCG@20 | MAP | MRR | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.5782 | 0.7882 | 0.1415 | 0.1708 | 0.4641 | 0.3269 | 0.7693 | 0.8868 |
| overview | 40 | 0.1947 | 0.4316 | 0.5312 | 0.2668 | 0.5519 | 0.1319 | 0.8958 | 1.0000 |
| multihop | 40 | 0.5397 | 0.6120 | 0.1025 | 0.1575 | 0.5034 | 0.3751 | 0.6799 | 0.9000 |

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

**1. The pool → top-20 step, for factual queries. This is the biggest single loss and it is
unattributed.**
nDCG 0.5885 → 0.4524, MAP 0.4689 → 0.3206, MRR 0.7690 → 0.5178, while recall is flat. Two candidate
causes, with **different fixes**: the **cross-encoder ranks the right page too low**, or the **20-slot
cut discards it**. Nothing measured so far separates them. **Next action: one run that separates them.**
This is the highest-value work in the programme.

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

| metric | the question it answers | how to read it here |
|---|---|---|
| **coverage** | *Of the pages this stage could possibly reach, how many did it actually return?* | The ceiling check. It cannot exceed 1 and it never depends on the ordering. Use it to see **where pages are lost**; it says nothing about order. |
| **recall@k** | *Of the pages that contain the answer, how many are inside the top k?* | **Inclusion.** Rises to 0.449 at the pool and flattens at 0.444 — recall alone would call the last stage harmless. Always report with k. |
| **precision@k** | *Of the top k, how many are actually gold?* | The mirror of recall. **Must be quoted with its ceiling** (0.485 here), or it reads as failure when it is at capacity. |
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
