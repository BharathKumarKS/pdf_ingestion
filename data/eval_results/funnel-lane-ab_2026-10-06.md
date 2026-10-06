# Lane A/B — reranker × ColBERT, four combinations, **pinned HyDE**

**2026-10-06** · same index, same 23 calibrated queries, same `top_k=20` as
`funnel-boundary-recall_2026-10-06.md` · reranker `BAAI/bge-reranker-v2-m3` (zero-shot,
**untrained**) · ColBERT `colbert-ir/colbertv2.0` via the SV cluster

**HyDE is pinned.** `call_llm` hardcodes `temperature 0.3`, so the earlier runs varied by
0.07 on Recall@20 from LLM sampling alone. Every configuration below reuses one cached set
of hypotheticals (`--hyde-cache`), so the only variable is the lane under test.

## Results

| Configuration | R@20 | Hit@20 | P@20 | R-prec |
|---|---|---|---|---|
| reranker + ColBERT — **current** | 0.600 | **1.000** | 0.080 | 0.231 |
| **no reranker** + ColBERT | 0.598 | 0.870 | 0.074 | 0.179 |
| reranker + **no ColBERT** | 0.589 | 0.957 | 0.078 | 0.205 |
| **no reranker + no ColBERT** | **0.615** | 0.957 | **0.085** | **0.246** |

| Boundary | B1 | B2 | B3 | B4 RRF | B5 merge | B5b retriever-20 | B6 final |
|---|---|---|---|---|---|---|---|
| reranker + ColBERT | 0.895 | 0.895 | 0.885 | 0.842 | 0.811 | 0.598 | 0.600 |
| no reranker + ColBERT | 0.895 | 0.895 | 0.885 | 0.842 | 0.811 | 0.598 | 0.598 |
| reranker + no ColBERT | 0.895 | 0.895 | 0.885 | 0.842 | **0.842** | 0.615 | 0.589 |
| no reranker + no ColBERT | 0.895 | 0.895 | 0.885 | 0.842 | **0.842** | 0.615 | **0.615** |

## Findings

1. **No lane change is a meaningful win.** All four configurations land between 0.589 and
   0.615 R@20 — a 0.026 spread, on 23 queries. The differences are now *deterministic*
   (HyDE pinned) but far too small to justify changing the pipeline on this evidence.

2. **The cross-encoder does not earn its place.** Against the pool it is given:
   - ColBERT pool: reranker 0.600 vs retriever's own 0.598 → **+0.002**
   - RRF pool: reranker 0.589 vs retriever's own 0.615 → **−0.026**

   It is neutral in one configuration and negative in the other. The best configuration
   removes it entirely.

3. **ColBERT consistently *reduces* recall at the merge.** 0.811 (ColBERT) vs 0.842 (RRF),
   and this reproduces in every measurement so far — 5 for 5. This **contradicts the
   course's guidance**, which prefers "rescoring with a stronger common judge" over
   rank-based fusion. Before removing the lane, **verify the multivector embeddings are
   sane** — this lane's output has never been validated, and a broken encoder would look
   exactly like this.

4. **The reranker buys Hit@20, not recall.** With ColBERT + reranker, Hit@20 = **1.000**
   (every query gets ≥1 relevant page) but R@20 = 0.600. Without the reranker, R@20 rises
   to 0.615 while Hit@20 falls to 0.957. So the reranker is trading "always find something"
   for "find more of what's labelled". That is a product decision, not purely a metric one.

5. **The reranker's target has moved.** It is no longer "beat 0.598" — the best
   lane-free configuration scores **0.615**. A fine-tuned reranker that cannot beat 0.615
   should be dropped, not shipped.

## Caveats

- **n = 23.** Differences are exact for this query set but their generalisation is not
  established. 0.026 is not a result to act on; it is a signal to investigate.
- **ColBERT embeddings unvalidated.** Finding 3 is only actionable once that lane's output
  has been checked — otherwise it may be a broken component, not a bad idea.
- Labels are LLM-generated (Qwen3-VL scan), never human-verified.

## Re-derive

```bash
export QDRANT_HOST=10.0.10.65
C=data/eval_results/hyde_cache_2026-10-06.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --json /tmp/a.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --no-reranker   --json /tmp/b.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --no-colbert    --json /tmp/c.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --no-reranker --no-colbert --json /tmp/d.json
```
