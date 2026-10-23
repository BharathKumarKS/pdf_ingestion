# P1 — Phase E: the authoritative full run on `knowledge_base_v2` (pre-registration)

> **Written 2026-10-22, session 11, BEFORE any number exists.** Owner decision (this session):
> run Phase E next. This file fixes what Phase E measures and how its numbers may be read, so
> the result cannot be interpreted after the fact (§D1's rule).
>
> Read first: `IMPROVEMENTS.md` §I57 (the question and the confounds), §I58 (ceiling
> normalisation), §I55 (the reranker's fallback), §I56 (the DA lane), `HANDOFF.md`.

---

## 1. The question

**Does the rebuilt system (`knowledge_base_v2`, doc `7ba61432`) beat the deployed one
(`knowledge_base`, doc `6d55c52b`) on the product endpoints?**

§I57 established that **no valid answer exists yet**: the only cross-system pair is confounded
six ways, and — the decisive gap — **the new index has never had generation metrics**. The only
v2 run was retrieval-only (§3d). Phase E is that missing run.

## 2. What Phase E IS, and is NOT

| | |
|---|---|
| **IS** | the authoritative `scripts/evaluate_rag.py` run in FULL mode (retrieval + synthesis + judge) against `knowledge_base_v2` |
| **IS NOT** | a clean A/B — the old arm is a *different run on a different day*, not a paired arm under one instrument |
| **IS NOT** | a re-ingest, a graph write, a Qdrant write, or a §G2 wiring (the summaries stay unwired until V5) |

## 3. Scope decision (recorded, so it is a confound not an accident)

**Visual queries are EXCLUDED (`--skip-visual`).** Reasons, all measured:
- §D12's own artifact shows `n / cal = 133/133` — the deployed run's metrics rows are the 133
  text queries; the visual lane contributed no metrics row. Excluding it **matches** §D12.
- The visual lane scores against a **separate** collection (`visual_knowledge_base`, doc
  `b2d9fb56`) whose points are **3× duplicated** (§B4b) — it is not the text index and is not
  what §I57 asks about.
- So Phase E executes **167 queries** (133 answerable text + 34 negatives) and reports **133**
  metrics rows.

## 4. Settings (pinned)

| setting | value | why |
|---|---|---|
| `QDRANT_HOST` | `10.0.10.65` | `.env` leaves it blank → the default is the LOCAL embedded store (§I49 Finding 1) |
| `QDRANT_COLLECTION` | `knowledge_base_v2` | the new index |
| generator | `openai/gpt-oss-20b` | the shipped generator (§D12 used it) |
| `JUDGE_MODEL` | `Qwen/Qwen3-VL-8B-Instruct` | **cross-family from the generator** — the standing rule. `JUDGE_MODEL` is unset in `.env`, so without this the judge would be the generator grading itself |
| `--query-file` | `data/eval_queries_v2.json` | the current gold set (200 entries) |
| `--skip-visual` | set | §3 |

## 5. Endpoints (pre-registered)

| # | endpoint | role | why |
|---|---|---|---|
| **P1** | **Faithfulness** (judge) | **primary** | the half of the eval **never measured on v2** — §I57 item 5 |
| **P2** | **Answer Relevance** (judge) | **primary** | the second half of the step-4 pair (§D12: 0.661 / 0.852) |
| S1 | R@100, R@20, Hit@20, Ctx.Prec, MRR, NDCG@20 | secondary | **ceiling-normalised** (§I58: the two indexes' achievable maxima differ — 0.9545 new vs 0.8806 old) |
| S2 | abstention on the 34 negatives | secondary | §D15: the mode differs from §D12's, so it is reported, not compared |
| G1 | `reranker.reranked_metrics_valid` (§I55) | **guard** | if the reranker fell back, the reranked order is not a reranked order |

## 6. Pre-registered reading rule

1. **The comparison to §D12 is CONFOUNDED and must be labelled so.** Six confounds (§I57) plus
   the §3 scope decision plus any HyDE difference. Deltas are **descriptive**, never causal.
2. **Ceiling-normalise every retrieval number** before comparing (§D9/§I58). Raw R@20 across the
   two indexes compares different denominators.
3. **A fallback query is flagged, not silently averaged.** If `reranked_metrics_valid` is false,
   name the query/queries (§I55) and report the headline both with and without them.
4. **Do not claim the new system is better or worse** unless the endpoint resolves under a paired
   test on the SAME instrument. Phase E gives the **new system's numbers**; it does not by itself
   create a paired arm.
5. **A run-integrity gap is a result.** If synthesis or faithfulness is missing for a query, that
   is reported — not smoothed over (every artifact before the §I55/P0 fixes had this defect).

## 7. Guards (each must be able to FAIL)

| # | check |
|---|---|
| E1 | the artifact's `config_snapshot.retriever.collection == "knowledge_base_v2"` — a run against the wrong store is unverifiable (§I49) |
| E2 | the judge is **cross-family** and **named** in the artifact, with its call/failure counts (§D11) |
| E3 | **133** metrics rows and **34** negatives — the counts §D12 also had |
| E4 | `reranked_metrics_valid` is recorded, and any fallback query is named (§I55) |
| E5 | the aggregate numbers re-derive from the **per-query JSON twin** (§I57) — i.e. the run must emit the `.json`, and the aggregates must match it |

**E5 is the check that the §I57 fix earns its place.** If the twin is absent, E5 cannot run.

## 8. Verifier

One independent, **cross-family** reviewer (the project's standing rule; the author is
DeepSeek-family). It must: read the artifact, re-derive the aggregates from the `.json` twin,
confirm E1–E5, and look for a query silently excluded from a denominator.

## 9. Cost

One cluster session: ~167 synthesis calls + ~4–6k judge calls (§D12 measured 4,876 with 0
failures). No re-ingest, no graph write, no Qdrant write. **Serialize against other cluster-LLM
work** (§I23: shared-GPU contention collapsed a build's throughput ~8×).
