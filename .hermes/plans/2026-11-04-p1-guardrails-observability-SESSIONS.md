# Guardrails + Observability — resumable plan (2026-11-04)

> **Written 2026-11-04** (session 33→34), before any code. Resumable in any new session: read this
> file, find the first ⬜, continue. **Every step carries its own acceptance check + independent
> verifier + mutation proof** (this repo's rule: one verifier per step, not one at the end — see the
> NiceGUI brief §3). Nothing here is measured until its artifact exists.

---

## 0. Why now, and what the plan already said

Two items the owner asked to add to the stack. Both were already **designed** in the repo — this
plan turns the design into buildable, verifiable steps.

* **Guardrails** — `ARCHITECTURE.md` **§12** ("Guardrails (planned — P2 spec)"): 4 input checks
  (injection, off-topic/non-physics, PII, oversized) + 5 output checks (grounding, answer leakage,
  citation validity, unsafe content, PII), with design constraints (fail-open vs fail-closed is a
  per-check decision; the guardrail itself must carry precision/recall; decisions must be counted).
  Cross-referenced by `README.md` Phase 5 and `HANDOFF.md` P2.
  ⚠️ **The original gate is now OPEN.** §12 says abstention "cannot be measured without negatives"
  and was gated on P0-9 — **P0-9 is DONE**: `data/eval_queries_v2.json` holds **34 negatives (17 %)**
  and `scripts/generate_negatives.py` exists. So an abstention/off-topic guardrail is measurable now.
* **Observability** — `src/core/telemetry.py` (Arize Phoenix / OpenTelemetry) already exists and is
  wired into the Streamlit app (`streamlit_app.py:34-36, 355-362`, gated by `PHOENIX_ENABLED`).
  Retrieval stages are traced. The gap is **§I4**: `src/core/llm.py` posts with raw `httpx` and the
  `openai` SDK is imported **nowhere** in `src/`, so `OpenAIInstrumentor()` patches a library that is
  never used — **synthesis, card generation and RAPTOR emit no span** (no latency, no token counts).
  `README.md` Phase 6 adds the cheap half: per-query latency/route logging + a teacher dashboard.

**Out of scope here (deferred, stated so they are decisions not omissions):** PPR, semantic caching,
OKF cards (P2 remainder); the DeBERTa unsafe-content head and the PII NER pass (§12 — the costly
classifiers; do them after the cheap signal-reuse guards); the teacher dashboard (Phase 6's UI half).

---

## 1. Status table — read this first

| id | step | cost | files (owner) | status | verifier |
|---|---|---|---|---|---|
| **O1** | §I4 — manual LLM spans around `call_llm` | **cheapest** | `src/core/llm.py` (+ reads `telemetry.py`) | ✅ **DONE 2026-11-04** | ✅ `logs/p1/step10/llm_span_verifier.py` **9/9 PASS**; `llm_span_mutation.py` **8 mutations, 9/9 checks reddened, NO inert** |
| **O2** | per-query route/latency log line + Status surface | low | `scripts/evaluate_rag.py`, `src/frontend/*` | ✅ **DONE 2026-11-04** | ✅ `src/core/query_trace.py`; verifier `logs/p1/step10/query_trace_verifier.py` **12/12**; mutation `query_trace_mutation.py` **11 mutations, 12/12 reddened, no inert**; smoke: `run_retrieval` emits a trace; status test 7 passed |
| **G1** | input guardrail: off-topic/abstention (`out_of_scope` intent + refusal), measured on the 34 negatives | medium | `src/core/intent_router.py`, new `src/core/guardrails.py` | ⚠️ **RE-SCOPED 2026-11-04** — see §6 | ⬜ |
| **G2** | output guardrail: grounding floor + citation validity, decisions counted | medium | new `src/core/guardrails.py`, `scripts/evaluate_rag.py` | ⬜ | ⬜ |

Order = **cheapest first** (O1 → O2 → G1 → G2). O1 and O2 touch disjoint files and can run in
parallel; G1 and G2 share `src/core/guardrails.py` and are therefore **serialized** (G1 first).

---

## 2. Workstream O — Observability

### O1 (cheapest) — make Phoenix trace the LLM stage (§I4)

**Change:** emit a manual span around the real HTTP call in `call_llm`'s two backends
(`_call_openai`, `_call_ollama` in `src/core/llm.py`), reusing `telemetry.span()` / `set_attr()`
(both already no-op safely when Phoenix is off). Attributes: backend, model, `json_mode`,
`prompt_chars`, `response_chars`, `latency_ms`, `ok`. Span name `llm.call`.
* ⚠️ **Put the span BELOW any monkeypatch.** `raptor_context_eval.py` and others replace the
  module-level `call_llm`; the span must live in the real call path (`_call_openai`/`_call_ollama`)
  or it is bypassed in exactly the measured runs.
* ⚠️ **No behaviour change.** Failure contract is unchanged (`""` on failure); the span is
  additive and must not add a dependency when Phoenix is off (the `span()` CM is a no-op then).

**Acceptance:** with `PHOENIX_ENABLED=true` and a Phoenix server up, one `call_llm` produces a
child span `llm.call` carrying `latency_ms` and `response_chars`; with Phoenix off, `call_llm`'s
return and timing are **bit-identical** to today (no-op path).

**Verifier:** `logs/p1/step10/llm_span_verifier.py` — (a) asserts the span is emitted with the
required attributes when a fake tracer is installed (no Phoenix server needed); (b) asserts the
no-op path adds **no** measurable overhead and returns the same value; (c) a **mutation proof**
(`llm_span_mutation.py`) that reddens each check (e.g. drop an attribute → attribute check reddens;
force the span to swallow an exception → the "span failure never breaks the call" check reddens).

### O2 — per-query route/latency log line (Phase 6 cheap half)

**Change:** have `run_retrieval` / the ask path emit one structured line per query: route (intent),
lanes fired, k, per-stage latency (embed / search / rerank / synthesize), and the top-1 score.
Surface the last N lines (or a rolling summary) in the Status tab.

**Acceptance:** N queries → N structured records with the required keys; a killed cluster yields a
record marked `error` rather than a hang.

**Verifier:** a stdlib verifier re-deriving the record count and the per-stage sum from a raw run
log + a mutation proof.

---

## 3. Workstream G — Guardrails (ARCHITECTURE §12, cheap-signal reuse first)

### G1 — input guardrail: off-topic / abstention

**Change:** extend `IntentRouter` with an `out_of_scope` outcome (§12: "the intent router already
classifies; extend it with an `out_of_scope` class") and add a pre-retrieval gate that, when the
query is out-of-scope **or** the top retrieved score is below a configured floor, returns a clean
refusal instead of synthesising.

**Acceptance / measurement (the whole point):** run the **34 negatives** + the 166 answerable
queries through the gate and report **precision / recall of the refusal** on the negatives, plus
the **false-refusal rate** on the answerables. Artifact `logs/p1/step10/g1_guardrail.json`.

**Verifier:** independent stdlib verifier re-deriving precision/recall/false-refusal from the raw
per-query gate decisions; mutation proof reddening each cell.

### G2 — output guardrail: grounding floor + citation validity

**Change:** after synthesis, apply (i) a **grounding floor** using the existing claim-level
faithfulness judge signal (§12: "the judge lane already computes claim-level faithfulness — caveat
or block below a threshold") and (ii) **citation validity** via `compute_citation_accuracy`
(already 1.000 today). Record **blocked / not blocked** per query into the artifact (§12: "record
the decision in the artifact").

**Acceptance:** decisions counted; a synthetic ungrounded answer trips the floor; a valid answer
does not.

**Verifier:** stdlib verifier re-deriving the decision from the raw score + threshold; mutation
proof.

---

## 4. The verification contract (per step — copied from the NiceGUI brief §3)

1. **Acceptance check** run by the author, raw output read.
2. **Independent reviewer** — a **different model family**, read-only, given the diff + numbered
   claims, told to re-derive rather than agree.
3. For any **measurement**: an independent stdlib **verifier** re-deriving every cell from the raw
   per-item array, **plus a mutation proof** where every check is reddened by ≥1 mutation and no
   check is inert.
4. A step with no verdict is **not done** and is **not committed**. Record the outcome in this file
   + `HANDOFF.md`, and register the number in `IMPROVEMENTS.md`.

## 5. Parallelism / file ownership (avoid edit conflicts)

| workstream | exclusive files |
|---|---|
| O1 | `src/core/llm.py` |
| O2 | `scripts/evaluate_rag.py`, `src/frontend/streamlit_app.py`, `src/frontend/nicegui_app.py` |
| G1, G2 | `src/core/guardrails.py` (new), `src/core/intent_router.py` (G1), `scripts/evaluate_rag.py` (G2 — coordinate with O2) |

⚠️ `scripts/evaluate_rag.py` is touched by **both O2 and G2** — serialize those two edits.

---

## 6. ⚠️ G1 RE-SCOPED (2026-11-04) — the pre-flight diagnostic refutes the cheap-signal gate

**Read first:** `IMPROVEMENTS.md` **§I114**; artifact `logs/p1/step10/g1_negatives_diagnostic.json`
(harness `g1_negatives_diagnostic.py`). **Read-only, over the existing `v3_judged_full` artifact — no run.**

**What was measured.** The 34 negatives are **three different problems**, and the top-1 CE score does
**not** separate them from the answerables (AUC 0.774; to catch 1/3 of the negatives the floor refuses
~9 % of answerables; best F1 0.500 at a 0.40 false-refusal rate):

| subclass | n | the problem | can an INPUT signal fix it? |
|---|---|---|---|
| `neg-out` | 12 | off-domain ("capital of France") | yes — a domain / `out_of_scope` signal |
| `neg-in` | 12 | in-domain physics the book doesn't cover | **no** — needs a grounding judgment |
| `neg-nea` | 10 | in-domain, book lacks the specific value | **no** — needs a grounding judgment |

⇒ **22 of 34 negatives are near-domain and only G2's grounding floor can separate them.** An
`out_of_scope` classifier's recall ceiling is **12/34 = 0.353**. And the gate is **undefined for the 33
`vis-*` queries** (no chunk-level top-1) — it must be defined **per route**.

**⇒ Proposed reorder (owner decision, not yet taken):**
* **G1 narrows** to the **off-domain input gate** (the `neg-out` 12) → needs the router's
  `out_of_scope`, i.e. a **classifier RETRAIN** (D6.5 precedent), **not** a score floor.
* The **22 in-domain negatives move to G2** (the grounding floor already specced there).
* **Do NOT ship a bare score floor** — measured F1 0.50 / false-refusal 0.40.

⚠️ Until the owner decides, **G1's implementation is on hold**; the O1/O2 workstream is unaffected.
