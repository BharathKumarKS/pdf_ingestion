# P1 — THE LEVERS: what moves which metric, where we stand, and where to move next

**Written 2026-10-30 (session 28).** This is the **consolidated** report. It supersedes the reading
of overview in `nomic_gap_report.md` §3 (see §7 below) and does not repeat that document's
methodology — it states the levers, their measured effects, and the current standing.

⚠️ **Every number here was re-read out of its artifact** (`t0_baseline.json`, `t4_endpoint.json`,
`lane_inclusion.json`, `fusion_attribution.json`, `order_waste_decomp.json`) before this document was
written, not copied from prose. Sources are named per section.

---

## 1. Headline

* **The endpoint's ranking loss is closed.** The product's endpoint nDCG@20 is **0.5503**, against the
  fused pool's own ordering of **0.5506**. Before the shipped per-type rerank policy it was **0.4946**.
* **The two remaining levers are the pool's COVERAGE (0.1734) and the pool's ORDER (0.1791).** The
  cross-encoder is worth **0.0050** overall, and it **helps** multihop.
* **Overview is an ordering problem, not a retrieval problem.** Its pool holds 31.4 gold pages of
  88.9 — enough to fill all 20 slots — so the pool supports 94 % of its ceiling. The loss is the
  order.
* **The pool's order has never been tested.** That is the next run (pre-registration committed
  `e8dda1a`).

---

## 2. Where we stand now

Product: `knowledge_base_v3` (nomic-embed-text-v1.5, 768d, pooled), 133 gold queries, endpoint =
cross-encoder top-20, the per-type rerank policy shipped. Source: `lane_inclusion.json` arm F0.

| type | n | coverage | R@20 | R-ceil@20 | P@20 | P-ceil@20 | nDCG@20 | MAP | MRR@20 | Hit@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| factual | 53 | 0.5882 | 0.5879 | 0.9494 | 0.1292 | 0.3000 | 0.5921 | 0.4754 | 0.7809 | 0.9057 |
| **overview** | 40 | **0.1937** | **0.1882** | **0.3992** | 0.5125 | 1.0000 | 0.5379 | 0.1265 | **0.8021** | 1.0000 |
| multihop | 40 | 0.5813 | 0.5500 | 0.9556 | 0.1050 | 0.2137 | 0.5072 | 0.3761 | 0.7291 | 0.9000 |
| all 133 | 133 | 0.4675 | 0.4563 | 0.7858 | 0.2372 | 0.4846 | 0.5503 | 0.3406 | 0.7717 | 0.9323 |

⚠️ **Read every recall against its ceiling.** Overview's raw 0.1882 looks ~3× worse than factual's
0.5879; against their own ceilings it is **47 % vs 62 %**. The raw gap overstates it. Both ceilings
are the report's §3 convention, `min(k, |reachable|)/|labelled|`.

**Overview, read correctly:** it has the **lowest recall** of the three types and the **highest nDCG
and MRR** — when it finds a relevant page it puts it first; it just finds few. Low recall **with**
high ordering is normally a retrieval problem — but §3 below shows the pool already holds the gold,
so here it is an ordering problem.

---

## 3. The loss decomposition — where the endpoint's top-20 goes

Source: `order_waste_decomp.json` (harness `order_waste_decomp.py`, verifier 42/42, mutation-proved
42/42 with no inert check). `oracle` = the best any ranker could do on the pool the product actually
built — an **upper bound**, not a target.

| type | R-ceil@20 | pool-oracle | pool's own order | product | waste_pool | **waste_order** | waste_ce |
|---|---|---|---|---|---|---|---|
| factual | 0.9557 | 0.8052 | 0.5830 | 0.5574 | 0.1505 | **0.2222** | 0.0256 |
| **overview** | 0.3992 | **0.3755** | 0.2103 | 0.1882 | **0.0236** | **0.1652** | 0.0221 |
| multihop | 1.0000 | 0.6466 | 0.5106 | **0.5500** | 0.3534 | 0.1360 | **−0.0394** |
| all 133 | 0.8016 | 0.6283 | 0.4491 | 0.4442 | **0.1734** | **0.1791** | **0.0050** |

⚠️ The `R-ceil@20` column here is the **label** ceiling `min(k,n_rel)/n_rel`; §2's is
reachability-adjusted. They agree for overview and differ slightly elsewhere (see §I99).

**What it says.** For **overview**, `waste_pool` is only 0.0236 — the pool holds **31.4 labelled pages
of 88.9**, enough to fill all 20 slots, so the pool supports **0.3755 of the 0.3992 ceiling (94 %)**.
The loss is `waste_order` **0.1652**. For **factual**, the order costs even more in absolute terms
(0.2222) with a real pool gap behind it (0.1505). For **multihop**, the pool genuinely lacks the gold
(0.3534) and the cross-encoder is a **gain** (−0.0394).

**The funnel behind it** (T0, coverage of a query's reachable labelled pages, overall):
base **0.9189** → full-dim cut **0.8381** → fusion **0.6845** → cross-encoder top-20 **0.4553**.

---

## 4. The levers — one row each

| lever | what it moves | measured effect | verdict |
|---|---|---|---|
| **Ingestion: pooled re-embed** (drop late chunking) | base-lane coverage | **+0.1547 RESOLVED** (nomic pooled − nomic late-chunked, L=500) | ✅ **SHIPPED** — v3 is the pooled index |
| **Embedder: nomic/768 vs qwen3/1024** | base-lane coverage | like-for-like **+0.0362 RESOLVED** for nomic; at the product endpoint **−0.0012 unresolved** | ⚪ the oracle gain does not survive the funnel |
| **Per-type rerank-query policy** (raw query for factual) | factual ordering | **factual nDCG +0.1397, MRR +0.26 RESOLVED**; overall +0.043 nDCG | ✅ **SHIPPED** — confirmed live (L1 133/133) |
| **Cross-encoder removal** | ordering, all types | nDCG **+0.0560 RESOLVED**, MRR +0.1011; R@20 and Hit@20 **unchanged** | ⚪ superseded — the policy recovers 77 % of it with no removal |
| **Cross-encoder fine-tune** | ordering, per type | ceiling = `waste_ce`: **0.026 factual / 0.022 overview / nothing multihop** | 🅿️ **LAST RESORT, priced** |
| **Fusion width / cap** (100 → 500) | pool coverage | **+0.1835 RESOLVED at the pool**; **NULL at the endpoint** (+0.0032) | ❌ **NO ACTION** — measured inert at the endpoint |
| **MMR** | pool coverage and order | coverage **+0.0032 unresolved**; at width 500 **exactly 0** (never fires) | ❌ **NO ACTION** — refuted as a suspect |
| **Lane: DA** | — | fusing it: **every metric unresolved** vs today's wiring | ❌ **NO ACTION** — a null at every placement |
| **Lane: graph** | ordering | lowers MRR **0.781 → 0.667**; fusing it does **not** recover MRR | ❌ **NO ACTION** — the cost is content, not placement |
| **Lane: RAPTOR** | overview | as a fusion participant: overview nDCG **−0.0383 RESOLVED** | ❌ **NO ACTION** — a resolved harm; page-less candidates displace |
| **Content filter** | base-lane page ranking | **−0.0063 unresolved** (19 chunks reachable, not 263) | ❌ **NO ACTION** |
| **20-slot endpoint cut** | coverage | coverage **+0.1451 RESOLVED** when widened to 50 | ⚪ a **deliberate context budget**, not a defect |
| **Fusion's ORDER** | ordering, all types | **RAN — NO ORDER INTERVENTION MOVES IT.** O1 (MMR off) +0.0004 nDCG · O2 (no ColBERT) −0.0012 · O3 (dense-only) **−0.0182, RESOLVED NEGATIVE on multihop** · O4 (level-1 weights) −0.0004; all unresolved | ❌ **NO ACTION — CLOSED** (§I100) |
| **§A per-space query vector** | — | not a lever; unblocks the v2-vs-v3 comparison | ▶ queued |

---

## 5. Per type — what is actually wrong, and what is not

**factual (53 queries) — WAS a ranking problem; now largely fixed.**
The cross-encoder collapsed factual's ordering: the pool's own order gives nDCG@20 **0.5885**, the
CE's gives **0.4524** (−0.136). T4 attributed it: the CE was being fed the **HyDE hypothetical**, not
the question. Removing the CE recovered **+0.1361**; feeding it the raw query recovered **+0.1397** —
so the hypothetical was essentially the whole cause. The policy shipped, and factual's endpoint nDCG
is now **0.5921**, level with its own pool. What remains is `waste_order` 0.2222 — the pool's order,
which the fusion-order run targets.

**overview (40 queries) — an ordering problem, and the lane answer is closed.**
Pool coverage 0.5221 is the lowest of the three types, which is why it was read as a retrieval
problem. It is not: the pool holds 31.4 gold pages of 88.9 and supports 94 % of the ceiling. The loss
is `waste_order` 0.1652. The lane cannot help — RAPTOR as a fusion participant is a **resolved harm**
(−0.0383 nDCG), and a summary carries no `page_number`, so it can only displace a page, never add
one. ⚠️ **Caveat:** overview's label sets are broad (mean 73.8 pages = 7.6 % of the corpus), so part
of that order loss is the metric being unable to reward a reasonable 20-slot answer to a broad
question. It is real recoverable space, not all of it recoverable.

**multihop (40 queries) — nothing to fix here.**
The cross-encoder **helps** (+0.0394 nDCG). Its real gap is the pool's coverage (0.3534), which is a
retrieval problem, and its `waste_order` is the smallest of the three (0.1360).

---

## 6. The lanes — what happened, and where they stand today

**Today's wiring.** The vector lanes (dense + sparse + ColBERT) are fused **client-side** inside
`_qdrant_search` (level-1 RRF, `rrf_k=1`, unweighted). The **DA** lane is appended *after* that
fusion, so it never participates in RRF. The **graph** lane is appended by the caller *after*
dedup/MMR, and **only for multihop**, with a fabricated `score`. **RAPTOR** is carried in v3 but is
not called on the evaluation path. A lane that is appended **can never displace a fused hit** — it
can only add unordered candidates, which is why the graph lane lowers MRR.

**What the lane-inclusion run measured** (source: `lane_inclusion.json`; all deltas vs the
vector-only fusion F0f unless stated):

| lane | result |
|---|---|
| **DA** | fusing it: nDCG −0.0047, MAP −0.0020, MRR +0.0168 — **all unresolved**; vs today's wiring **every metric unresolved**. A **NULL**. |
| **graph** | fusing it: nDCG **−0.0209**, R@20 **−0.0051**, precision **−0.0147** — **RESOLVED negative**; MRR −0.0103 unresolved. **It does not recover MRR**, so the cost is **content, not placement**. |
| **RAPTOR** | as a fusion participant: overview nDCG **−0.0383**, MAP **−0.0148**, coverage **−0.0030** — **RESOLVED negative**. |
| all three (F4) | the **worst arm on every ranking metric**. |
| **today's wiring vs vector-only** | nDCG **−0.0046 unresolved**, precision **−0.0060 RESOLVED negative**. The append pattern is not *earning* anything measurable — but that is an unresolved direction, **not** a licence to delete the lanes. |

**Where they stand.** DA and the graph lane remain wired as they are — **nothing ships and nothing is
removed**. RAPTOR is carried in the index but off the evaluation path. The lanes are a closed
question at the endpoint: none of the three improves it, in any placement tested.

---

## 7. What this changes in the earlier report

`nomic_gap_report.md` §3 concluded overview was **"a retrieval problem"** from its low pool coverage
(0.5221). §3 here shows the pool holds enough gold to fill all 20 slots, so the correct reading is an
**ordering** problem. The §3 text is not edited (it is a shipped artifact); this document and §I99
supersede that one conclusion. **Everything else in that report stands.**

---

## 8. What is NOT measured

* **The generator stage** — every number here is retrieval only.
* **Score-based fusion** (a normalised score sum instead of rank-based RRF) — needs cross-lane score
  normalisation across incomparable scores (cosine / SPLADE / maxsim); a separate design.
* **The v2-vs-v3 comparison under identical labels** — blocked on §A (the per-space query vector).
* **Any per-type confidence interval for the decomposition in §3** — n=40 per non-factual type; the
  ordering claim is a **size argument**, and the fusion-order run is what gives it a CI.
* **Lane weighting as a ship candidate** — F4 is exploratory.
* **The visual lane** — 33 visual queries carry no labels; not on this gold set.

---

## 9. Where to move next, in order

1. **▶ RUN THE FUSION-ORDER TEST.** Pre-registration committed **ALONE** as `e8dda1a` (D6.1). Five
   arms, one mechanism each: O0 the product (reference); O1 `mmr_enabled=False` (order-only, no code);
   O2 `colbert_enabled=False`; O3 dense-only; O4 level-1 RRF weights (dense 1.0, sparse 0.5,
   colbert 0.5 — ~1 line, inert by default). Read-only, ~28 min, verifier per stage, mutation-proved
   **before** the run. **This is the largest untested lever (0.1791 overall, 0.1652 overview).**
2. **§A — the per-space query-vector fix.** Not a lever; it is the enabler for the v2-vs-v3
   comparison under the same labels, which is the only controlled test of whether the embedder or
   ingestion changed reachability.
3. **Re-scope the old "pool → top-20 ranking step" item.** Its ranking half is closed (the shipped
   policy took the endpoint to the pool's own ordering); its remaining half is the 20-slot cut, a
   deliberate budget. Do not run it as written.
4. **Cross-encoder fine-tune — LAST RESORT, and priced.** Its absolute ceiling is `waste_ce`: 0.026
   on factual, 0.022 on overview, and **nothing** on multihop. Not worth a fine-tune until a
   re-measurement shows the CE is costing more than that.

⚠️ **NO ACTION, and say so:** the lanes (§I98), the fusion width (§I67), the cap and MMR (§I92), the
content filter (§I71), the 20-slot cut (a budget), and the CE fine-tune (priced at 0.026 max).

---

## 10. Glossary

* **coverage of a query's reachable labelled pages** — of the gold pages that exist in the index
  window, how many the stage returned. ⚠️ **Ours**, not the course's: the course uses the word
  "coverage" for the abstention rate.
* **R@k / P@k** — of the labelled pages, how many are in the top k / of the top k, how many are
  labelled. **Both carry a ceiling** (`R-ceil = min(k,n)/n`, `P-ceil = min(n,k)/k`), a property of
  the labels, identical in every arm. **P-ceil and R-ceil are the COURSE'S** (W7 §3.3).
* **nDCG@20 / MAP / MRR@20** — ordering metrics. **Low recall with high ordering = a retrieval
  problem; high recall with low ordering = a ranking problem.** That pair is what splits the types.
* **`mrr_at_20`** — the endpoint MRR. ⚠️ **Structurally blind to a page-less lane** (§I98); never
  quote it for one.
* **pool-oracle** — the best any ranker could do on the pool the product actually built. An upper
  bound, **not** a target.
* **waste_pool / waste_order / waste_ce** — the split of the loss into "the pool lacks the gold" /
  "the pool's order buries gold it holds" / "the cross-encoder buries it further".

## 11. Provenance

* **The course's metrics:** `P-ceil`, `R-ceil` (W7 §3.3, deck slide 25).
* **House metrics:** *coverage of a query's reachable labelled pages*, `pool-oracle`, the
  `waste_*` split, `mrr_at_20`.
* **Sources:** `logs/p1/step10/{t0_baseline,t4_endpoint,lane_inclusion,fusion_attribution,order_waste_decomp}.json`.
* **Register:** `IMPROVEMENTS.md` §I99 (this document's decomposition), §I98 (lanes), §I97 (T4),
  §I92 (cap/MMR), §I87–§I89 (ingestion), §I67 (width).
