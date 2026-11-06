# B3 — the live confirmation of the per-type rerank-query policy: RESULT

Artifact: `logs/p1/step10/policy_confirm.json` (133 queries, 0 errors).
Pre-registration §8: `.hermes/plans/2026-10-29-p1-per-type-rerank-query-preregistration.md`.

## What the run shows

| guard | result | what it means |
|---|---|---|
| **L1** the CE was fed the right query text | **PASS 133/133** | **the shipped code emits the policy exactly** — raw for factual, hypothetical for overview, raw for multihop. This is the confirmation |
| **L3** no ColBERT lane dropout | PASS (0) | the pool was never lane-reduced (§I96 counter) |
| **L4** no reranker fallback | PASS (0) | no query was scored on an unranked top-k (§I55) |
| **L5** 133 queries, 0 errors | PASS | |
| **L2** endpoint page list == the composition | **132/133** | one query differs — see below |

## The one L2 miss, and why it is a TRANSIENT, not a code difference

**`gold-008` (multihop):** the live run returned **20** pages; T4's arm C has **19**. The first
**19 match exactly**, and the live list carries **one extra trailing page (700)**.

⚠️ **A targeted double-probe disproves a code difference:** re-running `gold-008` (twice, back to
back) reproduces T4's **19 pages exactly, both times**, and the two probe runs agree with each other
(`_probe_a.json` / `_probe_b.json`). So the extra page is a **transient of the loaded full run**, not
something the shipped code does.

⚠️ **And L2 is over-strict for multihop, by construction.** The multihop lane is the **graph lane**,
whose Cypher has **no stable ORDER BY** — the code says so itself: *"Without any ORDER BY this
returned an arbitrary LIMIT — Memgraph's storage order"* (`graph_builder.graph_search`). Its
contribution can therefore vary between runs, which can change the pool and hence the CE's top-20 by
one page. **An exact page-list equality against another run's artifact is not a valid check for a
multihop query** — the same over-strict-check class as §I90's lesson and the pre-registration's own
§13 amendment.

**Restated by measurement (D6.2), not relaxed:** L2 is **`132/133 exact`**, with the one miss
attributed to the graph lane's run-to-run variation and disproved as a code difference by a targeted
double-probe. **L1 is unaffected** — it is a per-query property of the code's own behaviour, and it
passed 133/133.

## The first run (preserved)

`logs/p1/step10/policy_confirm_firstrun_FAILED_L4.json` — **L1 133/133 PASS**, but **L2 and L4 failed
on ONE query, `ovw-040`**: a transient **cross-encoder fallback** (§I55) returned that query's top-k
**unranked**, so its pages were the pool's order. Fixed by a **bounded retry** when a lane drops *or*
the CE falls back (the retry T4 used for the same class), and the re-run shows **0 fallbacks**.
