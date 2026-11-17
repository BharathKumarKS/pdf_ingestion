# Guardrails — course-aligned build plan (2026-11-05)

> **Source of truth for the CODE: the Week-6 lab materials**, not a re-implementation.
> * `Labs/Week_6/response_grounding/src/response_grounding/*.py` — the response-side (Act II) pipeline.
> * `dev/Week6/guradrails_req_side.py` — the request-side sanitizer (Act I outer wall).
> * `Week_Plan/week-6-summer-lesson-plan.pdf` ("The Two Gates of the Gatehouse", Asif Qamar) — the
>   specification for the request-side stages the labs describe but do not ship as code (gibberish
>   ladder, language ID, domain gate, injection, session-level, refusal doors, conformal abstention).
>
> **Resumable:** read this file, find the first ⬜, continue. **Every step carries its own acceptance
> check + a DETERMINISTIC stdlib verifier (a program that re-derives every reported cell from the raw
> per-item array; the independent different-family reviewer is the SECOND check, never the first) +
> a mutation proof.** Nothing is "done" without a verdict; nothing is committed without a verdict.
> **Owner approved the direction 2026-11-05; implement only after approval of this plan.**

---

## 0. The frame (from the lesson plan — these are load-bearing, not decoration)

* **Two gates, two virtues.** Request side = *security* (faces an adversary; keeps bad questions out;
  posture **fail-closed**). Response side = *integrity* (faces our own confabulation; keeps bad
  answers in; posture **disclose / hedge**). Collapsing them into one "guardrails" box is the sin the
  course exists to prevent.
* **Swiss cheese + cheapest-first.** Every check is an imperfect slice; order the stack *cheapest
  first* (counter → regex → small classifier → guard model → LLM judge) so cheap layers clear the
  field before expensive ones spend latency. Safety is enough imperfect slices that their holes stop
  aligning — and the errors must be *uncorrelated*.
* **Every gate is measured.** Precision, recall, **and latency**, on a set salted with *benign edge
  cases* (the false-positive tax compounds: 16 gates at 1 % ≈ 15 % of legitimate queries lost). A
  gate without a P/R number is trusted on faith — the failure mode §I114 already caught for G1.
* **Record the decision.** Every block/pass/hedge is counted into an artifact, or its metric effect
  is invisible (ARCHITECTURE §12).

## 1. Reuse map (do not rebuild what exists)

| need | existing asset | use |
|---|---|---|
| intent / domain classification | `src/core/intent_router.py` (sklearn, `dense_dim` schema) | R5 — extend with `out_of_scope` (retrain) |
| claim-level faithfulness (LLM judge) | `evaluate_rag.compute_faithfulness` + `make_judge_fn` | C3/C5 — the tier-3 judge |
| citation validity | `evaluate_rag.compute_citation_accuracy`, `_cited_page_numbers` | C4 |
| abstention signal | `evaluate_rag._looks_like_abstention` | R5/H1 (reuse the phrase + score-floor logic) |
| per-query trace | `src/core/query_trace.py` (O2) | cross-cutting telemetry |
| LLM call | `src/core/llm.py` (`call_llm`) | C1 decomposition, R6 sanitizer, C5 refiner |
| per-space query vector | `store` resolver (§A/§I104) | exploratory retriever (C5) |

## 2. Dependency map (measured 2026-11-05)

| dep | state | the lab's fallback when absent |
|---|---|---|
| `sentence-transformers` 5.6.1 | ✅ installed | — (NLI + MiniLM filter run as-is) |
| `transformers` 4.57.6 | ✅ installed | — |
| `spacy` (`en_core_web_sm`) | ⬜ MISSING | `PIIGuardrail` falls back to **regex-only** — port unchanged |
| `detoxify` | ⬜ MISSING | `ToxicityGuardrail` falls back to a **keyword heuristic** — port unchanged |
| `fasttext` (language ID) | ⬜ MISSING | R4 ships a **stdlib script-ratio** language gate first; fastText optional |
| `presidio-analyzer` | ⬜ MISSING | R7 ships the lab's regex+optional-spaCy path |

⚠️ **Model downloads** (NLI `cross-encoder/nli-deberta-v3-base`, MiniLM `all-MiniLM-L6-v2`) happen on
first use, CPU, no cluster needed. Tests must **stub** them (the repo's `USE_STUB_*` convention) so the
fast suite stays offline. ⚠️ The cluster's sparse + rerank are DOWN — irrelevant here (all local).

## 3. Package layout

```
src/core/guardrails/
  __init__.py
  sanitize.py     # R1 — port of dev/Week6/guradrails_req_side.py + base64/hex/URL decode
  request.py      # R2–R8 — the gatehouse funnel (cheapest-first), one class per stage
  response.py     # C1–C5 — port of the response_grounding lab modules, adapted to cfg/store/judge
  refusal.py      # H1–H3 — three doors, verbalized uncertainty, conformal abstention
  pipeline.py     # R10 — the ordered funnel + the tournament hook
prompts/claim_extractor_system_prompt.md   # copied from the lab
```
Alternative (repo's flat style): a single `src/core/guardrails.py`. **Recommend the package** — the
lab is ~8 modules and a flat file would be 1,500+ lines. (Owner call.)

---

## 4. Workstream R — the Gatehouse (request side, Act I / Labs 1–6)

| id | step | lab source | new cfg | deps |
|---|---|---|---|---|
| **R1** | **Deobfuscate-then-inspect**: NFKC fold, strip zero-width + control/bidi, decode base64/hex/URL and re-feed; log the presence of any obfuscation | `dev/Week6/guradrails_req_side.py` | — | stdlib |
| **R2** | **Length & complexity bounds**: hard ceiling (~500 tok) reject, soft warn (~100 tok) raise scrutiny, structural-complexity check (nested delimiters, multi-instruction) | §"Cheapest Structural Gate" | `guard_hard_max_tokens`, `guard_soft_warn_tokens` | stdlib |
| **R3** | **Gibberish ladder**: rung1 hash-set membership (keyboard smashes) → rung2 char stats (consonant/vowel, repeats) → rung3 entropy + OOV rate → rung4 tiny classifier (optional) | Lab 1 | `guard_entropy_floor` | stdlib (+optional model) |
| **R4** | **Language ID + policy**: detect script/language; served-language allowlist; unserved → decline or translate-and-re-run | Lab 2 | `guard_served_languages` | stdlib ratio first |
| **R5** | **Domain/intent gate** (`out_of_scope`) — the re-scoped **G1**: retrain `IntentRouter` with an `out_of_scope` class (D6.5 precedent), three-band escalation (confident-in admit / confident-out reject / ambiguous → escalate) | Lab 3, §"Cheap First Gate" | `guard_domain_conf_band` | sklearn (local) |
| **R6** | **Toxicity three-band**: score → hard-reject `>0.9` / flag `0.5–0.9` / pass `<0.5`; in-domain malice the domain gate waves through | `toxicity_guardrail.py` | `guard_toxicity_*` | detoxify (optional; keyword fallback) |
| **R7** | **PII detect-and-redact** at the request boundary (regex: email/phone/SSN/card/AKIA/ghp_; optional spaCy NER) — redact span, log the TYPE never the value | `pii_guardrail.py` | — | spaCy (optional; regex fallback) |
| **R8** | **Injection detection + spotlighting**: pattern pass + datamarking of retrieved text at the prompt boundary; optional canary token | Lab 4 | `guard_spotlight` | stdlib |
| **R9** | **Session-level** (optional/deferred): rate limit (429 + Retry-After), near-duplicate (hash + cosine>0.95), multi-turn drift | Lab 5 | `guard_rate_*` | stdlib |
| **R10** | **Gatehouse integration + tournament table**: assemble the ordered funnel, measure end-to-end latency vs the <100 ms budget, and **ablate each stage** (safety vs usability) | Lab 6 | — | — |

## 5. Workstream C — the Conscience (response side, Act II / Lab 7)
| id | step | lab source | notes |
|---|---|---|---|
| **C1** | **Assertion–evidence bipartite graph**: `ClaimExtractor` (LLM, Pydantic) → `ClaimDocumentMatrixBuilder` → `SemanticSimilarityFilter` (MiniLM, τ 0.5) → `NLIEntailmentChecker` (cross-encoder, τ 0.55) → `GroundednessEvaluator` | lab `claim_extractor.py`, `claim_document_matrix_builder.py`, `semantic_similarity_filter.py`, `nli_entailment_checker.py`, `groundedness_evaluator.py` + the prompt | port **verbatim**, swap the OpenAI client for `call_llm`; isolated-left-node = caught hallucination |
| **C2** | **Tier-1 cheap heuristics** (cost ≈0): citation validity (does every cited page exist in the retrieved set?), number-in-evidence (every number appears somewhere in evidence) | §"Escalation Ladder" Tier 1 | stdlib; runs before any model |
| **C3** | **Two-verifier cascade**: NLI (cheap, high-recall) clears the grounded majority; the existing LLM judge (`make_judge_fn`) settles only the residue | §"Two Verifiers" | reuse `compute_faithfulness` |
| **C4** | **Citation faithfulness (ALCE)**: citation recall + citation precision, both as NLI reads of the same graph | §"Citation Faithfulness" | reuse `_cited_page_numbers` |
| **C5** | **RAGAS triad wiring + disposition**: faithfulness / answer_relevance / context_relevance as one readout; disposition policy (regenerate / drop / hedge / refuse) with `ResponseRefiner`; optional exploratory self-healing (`ExploratoryRetriever` → Qdrant) | lab `response_refiner.py`, `exploratory_retriever.py`, `response_grounding_pipeline.py` | — |

## 6. Workstream H — Refusal & humility (Act III / Lab 8)

| id | step | notes |
|---|---|---|
| **H1** | **Three doors**: security (say nothing), permission (decline, don't confirm existence), grounding (explain + redirect) — three distinct surfaces | reuse `_looks_like_abstention` for the grounding door |
| **H2** | **Verbalized uncertainty**: templated hedges mapped to real thresholds (grounded / inferred / unknown), signal from retrieval thinness + groundedness residue | never the model's self-report |
| **H3** | **Conformal abstention**: nonconformity score = groundedness residue; quantile threshold at α on a calibration set; **verify the coverage guarantee** on a held-out set; reliability diagram + ECE | the capstone |

## 7. Cross-cutting

* **Dataset** `data/guardrail_eval.jsonl`: adversarial (obfuscated, gibberish, jailbreak, off-domain,
  in-domain-slur, loaded-question) **+ benign edge cases** (the "hate-speech policy" question, queries
  with numbers, frustrated-but-legit). The 34 eval negatives feed the off-domain and grounding rows;
  §I114's three subclasses (`neg-out` 12 / `neg-in` 12 / `neg-nea` 10) are the labelled spine.
* **Measurement**: every stage reports **precision / recall / latency** + the false-positive rate on
  benign traffic; R10 produces the tournament table.
* **Telemetry**: extend `query_trace` with one `guardrail.decision` field per gate (block/pass/hedge)
  + a Phoenix span per stage (reuse O1's pattern).
* **Per-check fail-open/closed** is an explicit decision recorded per stage (§12): request side
  fail-closed; response side fails *toward disclosure*.

## 8. Status table (the resume point)

| id | step | status | verifier | mutation |
|---|---|---|---|---|
| **P0** | config revert + `.env` + read-path width guard (owner-approved) | ✅ **DONE 2026-11-05** | ✅ `logs/p1/step10/p0_config_guard_verifier.py` **14/14**; independent cross-family reviewer `openai/gpt-oss-20b` **13/13 CONFIRMED** (`logs/p1/step10/guardrails_p0_r8_c2_review.json`) | n/a (config/test step) — suite back to the documented 4 failed pre-existing set |
| R1 | sanitize / deobfuscate | ✅ **DONE 2026-11-05** | ✅ `tests/test_guardrails_sanitize.py` 13/13; `logs/p1/step10/guardrails_r1_mutation.py` **6/6 reddened, no inert**; independent reviewer **7/7 CONFIRMED** (`deleg_47143c16`) | ✅ mutation 6/6 |
| R2 | length & complexity bounds | ✅ **DONE 2026-11-05** | ✅ `tests/test_guardrails_request.py` **15/15**; `logs/p1/step10/guardrails_r2r3_mutation.py` **8/8 reddened, no inert**; independent reviewer `deleg_c52fe343` **4 CONFIRMED, 2 REFUTED** (C5 refuted = the test count was 15, not 14 — author error, corrected; C1 refuted = a wording misread, behaviour intended) | ✅ mutation 8/8 |
| R3 | gibberish ladder | ✅ **DONE 2026-11-05** | ✅ same tests/mutation as R2; independent reviewer: same as R2 (`deleg_c52fe343`) | ✅ |
| R4 | language ID + policy | ⬜ | ⬜ | ⬜ |
| R5 | domain gate / `out_of_scope` (G1) | 🟡 **CODE DONE 2026-11-05** — enum + refusal route + prototypes + three-band `gate()` + training-script support; ⬜ **the RETRAIN is a separate run** | ✅ `tests/test_guardrails_domain_gate.py` 9/9; `logs/p1/step10/guardrails_r5_mutation.py` **7/7 reddened, no inert**; independent reviewer **7/7 CONFIRMED** (`deleg_f6d77193`, counted the 9 tests itself) | ✅ mutation 7/7 |
| R6 | toxicity three-band | ⬜ | ⬜ | ⬜ |
| R7 | PII detect-and-redact | ✅ **DONE 2026-11-05** | ✅ `tests/test_guardrails_pii.py` 9/9; `logs/p1/step10/guardrails_r7r8_mutation.py` **7/7 reddened, no inert**; independent reviewer **6/6 CONFIRMED** (`deleg_17b55979`) (port of the lab `pii_guardrail.py` + Luhn/AKIA/ghp_) | ✅ |
| R8 | injection + spotlighting | ✅ **DONE 2026-11-05** | ✅ `tests/test_guardrails_injection.py` 5/5 (pattern pass + datamarking, lossless); independent cross-family reviewer `openai/gpt-oss-20b` **13/13 CONFIRMED** (`logs/p1/step10/guardrails_p0_r8_c2_review.json`) | ✅ `logs/p1/step10/guardrails_r7r8_mutation.py` **7/7 reddened, no inert** (shared with R7) |
| R9 | session-level (rate/near-dup/multi-turn) | ⬜ optional | ⬜ | ⬜ |
| R10 | integration + tournament | ⬜ — ⚠️ its blocker is CLEARED 2026-11-05: the eval dataset is BUILT (`data/guardrail_eval.jsonl`, 51 rows, 8 categories; validator `scripts/validate_guardrail_eval.py`, test `tests/test_guardrail_eval_dataset.py` passes). The funnel + tournament are **not** run | ⬜ | ⬜ |
| C1 | bipartite grounding graph | ✅ **DONE 2026-11-05** (5 lab modules ported; live-model probe run) — ⚠️ the lab's NLI model does NOT separate unrelated from entailing text (§I121) | ✅ `tests/test_guardrails_response_c1.py` 23/23 + live probe `logs/p1/step10/c1_live_probe.py` (asserted A1/A2/A4/A5/A6 pass); stdlib verifier `guardrails_c1c4_verifier.py` **14/14**; independent cross-family reviewer **`openai/gpt-oss-20b` 9/9 CONFIRMED** (`logs/p1/step10/guardrails_c1c4_review.json`) | ✅ `logs/p1/step10/guardrails_c1c4_mutation.py` **13/13 reddened, no inert** (M9 initially inert — fixture strengthened) |
| C2 | cheap-heuristics tier | ✅ **DONE 2026-11-05** | ✅ `tests/test_guardrails_response_c2.py` 10/10; `logs/p1/step10/guardrails_c2_mutation.py` **4/4 reddened, no inert**; independent cross-family reviewer `openai/gpt-oss-20b` **13/13 CONFIRMED** (`logs/p1/step10/guardrails_p0_r8_c2_review.json`) | ✅ |
| C3 | two-verifier cascade | ⬜ | ⬜ | ⬜ |
| C4 | citation faithfulness (ALCE) | ✅ **DONE 2026-11-05** | ✅ `tests/test_guardrails_citation_c4.py` 10/10; stdlib verifier `guardrails_c1c4_verifier.py` **14/14** (independent ALCE re-derivation); independent cross-family reviewer **`openai/gpt-oss-20b` 9/9 CONFIRMED** (`logs/p1/step10/guardrails_c1c4_review.json`) | ✅ `guardrails_c1c4_mutation.py` **13/13 reddened, no inert** |
| C5 | triad + disposition | ⬜ | ⬜ | ⬜ |
| H1 | three doors | ⬜ | ⬜ | ⬜ |
| H2 | verbalized uncertainty | ⬜ | ⬜ | ⬜ |
| H3 | conformal abstention | ⬜ | ⬜ | ⬜ |

## 9. Verification contract (per step — the repo's rule, one verifier per step)

1. **Acceptance check** run by the author; raw output read.
2. **Independent reviewer** — different model family, read-only, given the diff + numbered claims,
   told to re-derive rather than agree.
3. For any **measurement**: an independent **stdlib verifier** re-deriving every cell from the raw
   per-item array, **plus a mutation proof** where every check is reddened by ≥1 mutation and no check
   is inert.
4. A step with no verdict is **not done** and is **not committed**. Record the outcome here +
   `HANDOFF.md`, and register the number in `IMPROVEMENTS.md`.
5. **The completeness gate (`scripts/verify_plan_coverage.py` + `tests/test_plan_verification_coverage.py`).**
   The four rules above lived only as prose, so a step with a MISSING reviewer was indistinguishable
   from a step with one — measured 2026-11-05: **P0, R8 and C2 were all marked ✅ with no reviewer**,
   a consistent omission nothing caught. The gate is **deterministic** (no model, no judgment) and
   asserts, for every `✅ DONE` row in §8, that the verifier cell is non-empty, the mutation cell is
   non-empty, an independent reviewer **resolves** (a `deleg_*` id, or a `…review…` artifact that
   exists), and every backticked `path/like/this` token exists on disk. It is bound to the test
   suite, so it cannot itself be skipped — a deterministic gate needs no verifier of its own. Run it
   standalone: `unset PYTHONPATH && .venv/bin/python scripts/verify_plan_coverage.py`.

## 10. Decisions (settled 2026-11-05)

* **Package** — `src/core/guardrails/` (owner-approved).
* **Scope of this pass** — the cheap-first core: **R1, R2, R3, R5, R7, R8, C1, C2, C4** (all
  cluster-free). R4/R6/R9/H* after.
* **R5 retrain** — in scope: `out_of_scope` is added to the live `IntentRouter` (§I116 shows the eval
  bypasses the router, so the gate's product effect is separable from the metrics).
* **G1 is SUPERSEDED, not separately needed.** §I114 split it: the off-domain half (12/34 negatives)
  → **R5**; the in-domain half (22/34: `neg-in` 12 + `neg-nea` 10) → the response-side grounding floor
  (**C1/C4** now, C5 later). G1's score-floor variant is deliberately **not shipped** (§I114 measured
  F1 0.50 at a 0.40 false-refusal rate). The old plan's G1 row in
  `2026-11-04-p1-guardrails-observability-SESSIONS.md` is therefore closed by R5 + the C-workstream.
