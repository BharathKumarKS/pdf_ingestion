# Merge-mode A/B — ColBERT as judge vs ColBERT as voter

**2026-10-06** · 23 calibrated queries · pinned HyDE (`hyde_cache_2026-10-06.json`) ·
`top_k=20` · reranker `BAAI/bge-reranker-v2-m3` (zero-shot) unless stated

Follows `funnel-lane-ab_2026-10-06.md`, which found RRF (a fusion of two rankers) beating
ColBERT (a single MaxSim score) at the merge. Hypothesis: ColBERT was being used as the
**outer query**, so it *replaced* the dense+sparse fusion instead of adding to it. Fix
under test: make it a **third prefetch contributor** so RRF fuses three rankings.

## Results

| merge mode | R@20 | Hit@20 | P@20 | R-prec |
|---|---|---|---|---|
| ColBERT as outer query — **was current** | 0.600 | **1.000** | 0.080 | 0.231 |
| RRF over dense+sparse | 0.589 | 0.957 | 0.078 | 0.205 |
| RRF over dense+sparse+ColBERT | 0.569 | 0.957 | 0.076 | 0.201 |
| **RRF 3-way, NO reranker** | **0.651** | 0.957 | **0.089** | **0.256** |

## The finding: the fusion works, the reranker destroys it

| merge | B5b — retriever's own top-20 | B6 — after the reranker | reranker's effect |
|---|---|---|---|
| ColBERT outer | 0.598 | 0.600 | +0.002 |
| RRF 2-way | 0.615 | 0.589 | −0.026 |
| **RRF 3-way** | **0.651** ← best | **0.569** ← worst | **−0.082** |

Two conclusions, both measured:

1. **The hypothesis was right.** Fusing ColBERT as a voter gives the best candidate
   ordering of anything measured so far — **0.651 vs 0.598** for ColBERT-as-judge, and
   0.615 for RRF over two lanes. RRF combines independent rankings; one MaxSim score
   cannot. **ColBERT is worth keeping — as a voter, not as the judge.** Implemented in
   `store._qdrant_search`.

2. **The cross-encoder destroys the ordering it is given, and the harm scales with how
   good that ordering is.** +0.002 on the weakest input, −0.026 on the middle, **−0.082**
   on the best. Combined with the lane A/B (where it failed to beat the retriever's own
   top-20 in 2 of 3 configurations), the reranker is now the single clearest liability in
   the pipeline.

## The open decision — recall vs always-find-something

| | R@20 | Hit@20 |
|---|---|---|
| 3-way fusion **+** reranker | 0.569 | 0.957 |
| 3-way fusion **without** reranker | **0.651** | 0.957 |
| old config (ColBERT judge + reranker) | 0.600 | **1.000** |

The best recall is **3-way fusion with the reranker off** (+0.051 R@20 over the old
config, +0.009 P@20, +0.025 R-prec). The cost is Hit@20: the old configuration scored
**1.000** — every query found at least one relevant page — and the new one scores 0.957,
so one query in 23 loses its only relevant page. That is a product trade-off, not a
metric one, and it is not resolved here.

**Note the ordering constraint:** the fusion change must ship *together with* the
reranker decision. Applied alone it is a regression (0.600 → 0.569).

## Caveats

- **n = 23.** The 0.051 gain is deterministic for this query set but its generalisation is
  unestablished — roughly 1.2 standard errors on a paired test. Suggestive, not proven.
- The reranker is zero-shot and untrained; a fine-tuned one might reverse finding 2. The
  target it must beat is now **0.651**, not 0.598.
- Labels are LLM-generated (Qwen3-VL scan), never human-verified.

## Re-derive

```bash
export QDRANT_HOST=10.0.10.65
C=data/eval_results/hyde_cache_2026-10-06.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --merge colbert --json /tmp/a.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --merge rrf2    --json /tmp/b.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --merge rrf3    --json /tmp/c.json
uv run python scripts/funnel_boundary_recall.py --hyde --hyde-cache $C --merge rrf3 --no-reranker --json /tmp/d.json
```
