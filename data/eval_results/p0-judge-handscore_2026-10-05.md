# p0-judge — hand-scoring the judge (agreement check)

**2026-10-05** · judge `Qwen/Qwen3-VL-8B-Instruct` · generator `openai/gpt-oss-20b`

P0-8 produced the first generation metrics this repo has had. Before trusting them, 10
answers were hand-scored against **the exact passages the judge saw**. Method: an
instrumented run that logged every judge prompt and verdict (406 judge calls, 0 failures);
claims were checked by hand against the passage they were tested against.

## Agreement

| Query | Judge faithfulness | Hand | Verdict |
|---|---|---|---|
| vec-001 | 0.571 | ~0.57–0.71 | agreement (±1 claim) |
| vec-003 | 0.333 | ~0.67 | **judge low** |
| vec-005 | 0.750 | ~0.75 | agreement |
| vec-007 | 0.875 | 1.00 | **judge low** |
| vec-008 | 1.000 | 1.00 | exact |
| vec-010 | 0.833 | 0.83 | exact |
| raptor-002 | 0.250 | ~0.42 | **judge low** |
| raptor-004 | 0.583 | 0.58 | exact |
| graph-004 | 0.417 | ~0.58 | **judge low** |
| graph-005 | 0.889 | 0.89 | exact |
| **mean** | **0.650** | **~0.73** | **judge ≈0.08 low** |

Exact agreement on 4/10 (vec-008, vec-010, raptor-004, graph-005); **6/10 within ±0.02**.
Every disagreement is in the same direction: the judge says NO where the passage does
support the claim. **Faithfulness is a floor, not a point estimate.** Ans.Relevance and
Citation Acc. were not systematically wrong.

Re-derive with `scripts/instrument_judge.py` from the `llm-judge-validation` skill:
`summarize()` on the scores above returns mean delta −0.079 and "judge biased LOW".

## The three misses (with page evidence)

1. **LaTeX notation vs the PDF's mangled plaintext.**
   - vec-007: claim `F = -G m₁m₂/r³ · r` judged NO against p243, which reads
     `F = -Gm 1 m 2 r /r 3` — the same law.
   - vec-001: claim `K = ½mv²` judged NO against p228's `1 2 mv 2`.
   - vec-003: claim `Planck's constant equals 62606896 × 10⁻³⁴ J·s` judged NO against
     p965's `h | 62606896 × 10 - 34 Js`.
2. **Near-verbatim paraphrase.** raptor-002: claim "energy appears in electrical,
   mechanical, radiant, heat forms" judged NO against p209, which lists exactly those.
   graph-004: "angular momentum is conserved when no external torque acts" judged NO
   against p344, which states it almost word for word.
3. **Meta/citation claims.** Claim extraction emits "This value appears on page 965" —
   no passage can *state* that, so it is always NO. An ill-formed claim, not a retrieval
   miss, and it depresses the metric.

## Consequence

Report 0.701 (canonical run) as **≥0.70, indicative**, not as a calibrated score. Do not
read a faithfulness delta under ~0.05 between two runs as a real change.

## Harness residual

Claim extraction returned unparseable JSON (`Invalid \escape`, LaTeX backslashes) for
2/23 queries (vec-003, graph-003), which scored `None`. That is P0-2 behaving correctly
(logged, not silently 1.0), but it loses ~9% of the measurement.