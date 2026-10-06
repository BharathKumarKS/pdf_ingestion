# Funnel boundary recall + the full metric set (first measurement)

**2026-10-06** · embedder `nomic-ai/nomic-embed-text-v1.5` (MRL 768/64) · SPLADE + ColBERT
via the SV cluster · reranker `BAAI/bge-reranker-v2-m3` (zero-shot, **untrained**) ·
generator for HyDE `openai/gpt-oss-20b` · Qdrant server `10.0.10.65:6333`

First per-stage recall measurement. Previously only `recall@100` and `recall@20` were
reported — two points, which cannot say **which stage** loses the relevant pages, and that
is the question that decides whether the fix is chunking (loss at the wide end) or ranking
(loss at the narrow end).

## Method

The funnel runs server-side as **one nested Qdrant prefetch**, so intermediate pools are
invisible from a single call. `scripts/funnel_boundary_recall.py` replays each stage as its
own query, mirroring `store._qdrant_search` exactly. Recall is **page-level**: a boundary
"has" a page if any of its chunks is on that page.

| Boundary | what it is |
|---|---|
| B1 `dense64_1000` | `dense_64` ANN — the only stage facing the whole corpus |
| B2 `dense768_500` | full-resolution rescore of B1 |
| B3 `sparse_250` | SPLADE, independent lexical branch |
| B4 `rrf_union_100` | merge of B2+B3 by RRF, **no** late interaction |
| B5 `colbert_100` | ColBERT MaxSim over B2+B3 — **the merge the app uses** |
| **B5b `retriever_top20`** | **the retriever's OWN top-20, before reranking** |
| B6 `rerank_20` | the cross-encoder's top-20 |

**B5b is the control that makes this interpretable.** Without it, B6's drop from 0.811 is
confounded with pool size (67 pages → 15) and says nothing about whether reranking helped.

## Parameters (must match for a diff to be valid)

`n = 23` calibrated queries with labels (7 uncalibrated `visual` queries excluded) ·
`top_k = 20` · tenant `global` · `MIN_CONTENT_PAGE=30` (front matter filtered) ·
**`HYDE_ENABLED=true`** — HyDE is applied to `factual` + `overview` and changes both the
dense search vector and the cross-encoder's query.

## Results

| Boundary | pool (pages) | mean recall | queries missing ≥1 |
|---|---|---|---|
| B1 `dense64_1000` | 396 | **0.895** | 7 |
| B2 `dense768_500` | 236 | 0.895 | 7 |
| B3 `sparse_250` | 142 | 0.885 | 8 |
| B4 `rrf_union_100` | 60 | 0.856 | — |
| B5 `colbert_100` | 67 | 0.811 | 9 |
| **B5b `retriever_top20`** | 15 | **0.598** | — |
| **B6 `rerank_20`** | 15 | **0.561** | 16 |

### Final metrics (reranked top-20)

| Metric | Value |
|---|---|
| Precision@20 | **0.080** |
| Recall@20 | 0.561 |
| Hit@20 | 0.957 |
| R-precision | 0.234 |
| P@20 ceiling — `mean(min(\|rel\|,20)/20)` | **0.170** |
| → P@20 as % of achievable | **47%** |

## Findings

1. **The wide end is healthy (0.895).** Only 7 of 23 queries miss any relevant page even at
   the widest stage. The right pages are in the corpus and are being found — so **chunking
   is not the constraint**, and a re-ingest is not the first fix.
2. **The reranker provides no measurable gain over the retriever's own ordering**
   (0.561 vs 0.598), and may be slightly negative. It is a zero-shot generalist on physics
   text. **This is the bottleneck.**
3. **ColBERT is consistently slightly worse than plain RRF** — 0.811 vs 0.856 here, and
   0.832 vs 0.842 / 0.806 vs 0.819 in the two runs without the B5b control. Late
   interaction at K=100 is not earning its place.
4. **Hit@20 ≈ 0.96–1.00.** Nearly every query gets at least one relevant page in the top 20;
   it just doesn't get *enough* of what is labelled.
5. **Decomposition:** ranking gap (0.561 → 0.895 ceiling) ≈ **0.33**; retrieval gap
   (0.895 → 1.0) ≈ **0.10**. Ranking is the dominant lever by ~3×.

## Caveats — read before comparing

- **n = 23.** The reranker delta (0.037) is within noise. "No measurable gain" is supported;
  "definitely worse" is not.
- **HyDE is non-deterministic.** Two runs of the *same* command gave Recall@20 of **0.631**
  and **0.561** — a 0.07 spread from LLM sampling alone. **Any difference below ~0.07 is
  currently unresolvable**, independent of sample size. Pin HyDE (temperature/seed, or cache
  the hypotheticals) before running any A/B.
- **P@20 is label-count-limited.** At 47% of a ceiling set by `|relevant|` (mean 3.4, max 13),
  it moves with labelling effort as much as with ranking. Prefer Recall@20 / Hit@20 /
  R-precision for comparisons.
- **The gold set's labels are LLM-generated** (Qwen3-VL scan), never human-verified.

## Re-derive

```bash
QDRANT_HOST=10.0.10.65 uv run python scripts/funnel_boundary_recall.py --hyde \
    --json data/eval_results/funnel-boundary-recall_2026-10-06.json
```

Per-query pages at every boundary are in the companion `.json`. Drop `--hyde` to measure
the non-deployed path (recorded: B1 0.902 → B6 0.583, Hit@20 0.913, R@20 0.583).
