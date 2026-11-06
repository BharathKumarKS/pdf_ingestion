# §G3 sensitive re-measurement — pre-registration (2026-11-05)

> Written BEFORE the re-derivation runs. Read-only over two artifacts already on disk.

## Why

§I51 recorded §G3's entity-resolution merge as **measured-and-null on its pre-registered endpoint** —
but the endpoint (the median of the retrieved top-5 `matched_concepts`) is **INERT**: it stayed at
**1.0** because the median can only leave 1.0 when *more than half* of the 200 queries need a top-5
median ≥ 2, and only **14** do. §I51 states this explicitly: *"Do not read this null as 'entity
resolution does not help retrieval'; it is a null about a metric that could not have moved."*
Re-pre-registering a **sensitive** endpoint was an owner decision, now taken (§G3 task, 2026-11-05).

## The endpoint (pre-registered)

**Primary — `ge2_count`:** for each query, the number of chunks matching **≥ 2** of the query's
top-8 concepts, over the **whole** `matched_concepts` histogram (the artifacts record it with **no
LIMIT**, so the distribution is not truncated). Paired across the 200 queries, before vs after the
merge.

**Secondary — `share_ge_2`:** the same quantity as a share of the query's chunks that match ≥ 1
concept, corpus-level, reported alongside.

## Reading rule (fixed now)

- **Paired** `delta = after − before`, per query. **RESOLVED** iff the **95 % CI on the mean paired
  delta excludes 0**; otherwise **UNRESOLVED**.
- Report the full vector: n, mean delta, SD, CI, W/L, and the corpus `share_ge_2` before/after.
- A **zero-width CI** (`[0,0]`) is a statement about the instrument, not the treatment — report it
  as such, never as "no effect".

## Falsification clause

If the primary endpoint does **not** resolve, the merge's query-side effect stays **unmeasured at
this instrument** — that is a result, not a failure. It does **not** licence the claim "entity
resolution does not help retrieval" (the endpoint measures *matched-concept multiplicity*, not
retrieval quality). Any retrieval-quality claim still needs the endpoint ablation.

## Artifacts (inputs, read-only)

| | path | model |
|---|---|---|
| BEFORE | `logs/p1/step10/g3_query_side_baseline_2026-10-22.json` | Qwen3-Embedding-0.6B (1024d) |
| AFTER | `logs/p1/step10/g3_query_side_baseline_2026-10-22_post_merge.json` | same |

Both: 200 queries, `queries_file = data/eval_queries_v2.json`, `retrieval_limit 5`, `top_k_concepts 8`,
no LLM calls. ⚠️ The earlier `g3_query_side_baseline.json` (2026-10-20) is the **768d** arm and is
**NOT** comparable — §I49 moved the collection to the dense lane; it is excluded.

## Out of scope

The **retrieval-quality ablation** (does the merge improve retrieval?) — needs the full retrieval
path, BLOCKED while the cluster's sparse + rerank lanes are down.
