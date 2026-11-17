# Guardrail Eval Dataset Report

**Built**: 2026-11-05 (session 39). This clears R10's blocker (the gatehouse funnel +
tournament needed an eval dataset that did not exist).

**Dataset**: `data/guardrail_eval.jsonl` — **51 rows across 8 categories**:

| category | rows |
|---|---|
| benign_in_domain | 22 |
| off_domain | 12 |
| benign_edge | 5 |
| obfuscated | 3 |
| jailbreak | 3 |
| gibberish | 2 |
| in_domain_malice | 2 |
| loaded_question | 2 |
| **total** | **51** |

**Files**:
- `data/guardrail_eval.jsonl` (the dataset)
- `scripts/validate_guardrail_eval.py` (the validator)
- `tests/test_guardrail_eval_dataset.py` (the test)

**Validator output** (`.venv/bin/python scripts/validate_guardrail_eval.py data/guardrail_eval.jsonl`):

```
Per-category counts:
  benign_edge: 5
  benign_in_domain: 22
  gibberish: 2
  in_domain_malice: 2
  jailbreak: 3
  loaded_question: 2
  obfuscated: 3
  off_domain: 12
Validation succeeded.
```

**Pytest result** (run in repository root):

```
$ .venv/bin/python -m pytest tests/test_guardrail_eval_dataset.py -q
1 passed
```

⚠️ **Correction of record.** An earlier version of this report listed only two categories
(`benign_in_domain` 22 + `off_domain` 12 = 34 rows) — it was written before the adversarial
categories were added and did not match the file. Corrected 2026-11-05 to the 8-category,
51-row file above. The independent reviewer's dataset claim **S2-D1 was CONFIRMED** (counts
sum to 51) and **S2-D2 was REFUTED** ("cannot re-derive") — recorded in
`logs/p1/step10/session39_review.json`.

⚠️ **R10 itself (the funnel + tournament table) has NOT run** — this dataset is its input, not
its result. See the plan `.hermes/plans/2026-11-05-p1-guardrails-course-aligned-SESSIONS.md`
§8 (the R10 row).
