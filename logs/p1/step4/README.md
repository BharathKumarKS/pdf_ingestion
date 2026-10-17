# P1 Step 4 — E3 late chunking (`late_chunk_embedder.py`) — 2026-10-17

The plan's Step 4 (`.hermes/plans/2026-10-16-p1-reingest-plan.md` §5) demanded the **alignment
probe first**, then the module, then independent verification. This directory is the evidence.

## Files

| File | What it is |
|---|---|
| `probe_qwen3_alignment.py` → `alignment.json` | **The FIRST ACTION.** Live probe: does the local Qwen3 tokenizer align 1:1 with the cluster's per-token vectors? |
| `probe_late_chunk_cost.py` → `cost.json` | Per-token cost on `test_book.pdf`, extrapolated to 968 pages; pooled-vs-per-token payload and wall time. |
| `probe_child_units.py` → `child_units.json` | The child-size distribution at `min_chunk_tokens=32` (the plan's "is 32 still the right unit" question). |
| `verify_evidence.py` → `evidence.json` | The author's evidence pack: pooling **recomputed independently** from the raw endpoint response over all 66 fixture children. |
| `verify_singleturn.py` → `verdict.json` | Independent verifier, round 1. |
| `verify_readjudicate.py` → `verdict2.json` | Round 2, on the fixed module. |

## Verdict

**Alignment CONFIRMED for Qwen3** — the plan's fallback (jina for the token path) was not needed,
so R2's 1024d + 64d design stands. Details in `IMPROVEMENTS.md` §E3b.

## The independent review — and the part worth remembering

Verifier model: **`openai/gpt-oss-20b`** on the cluster (`http://10.0.10.70:8000`), a *different*
model from the author's (`deepseek/deepseek-v4.1-flash`). Single-turn, evidence embedded, no tools
(the documented multi-turn limit: the model's harmony control tokens leak into message content and
the server rejects the replayed history).

**Round 1: `passed: false`, one `logic_error` — and it was REAL.**

> the code calls a non-existent method `self._embed_isolated(c)` when offsets are empty. The
> intended method is `self.embed_isolated(c)`.

The zero-token-parent branch (`if not offsets`) called a method that does not exist. The author had
renamed `_embed_isolated` → `embed_isolated` earlier in the session with two targeted patches and
believed both call sites were updated; `grep` showed line 194 still had the old name. It is an
**AttributeError on a reachable path** (a parent whose text tokenizes to zero tokens), and it was
the one branch with no test — exactly the class of defect an independent read catches and a green
suite does not.

Fixed, and a regression test added
(`test_parent_that_tokenizes_to_zero_tokens_falls_back_to_isolation`, which injects a tokenizer
returning an empty `offset_mapping`).

**Round 2: `passed: true`, `logic_errors: []`** — the verifier confirmed the fix, that the new test
exercises the intended branch, and that no other silent wrong answer remains.

### Round 2's first attempt produced no verdict

It ran 216 s, hit `finish_reason=length` (126,818 reasoning characters ≈ 32k tokens of hidden
reasoning), and returned empty content. Per the project rule, **a protocol failure is no verdict,
never a pass** — the prompt was trimmed (drop the test source) and re-run, which returned the
verdict above. Budget `max_tokens ≥ 32k` for the reviewer, and expect a single-turn round to be a
coin-flip on a 300-line input: **two** rounds may be needed.

### Claims the verifier confirmed (round 1, all eight)

C1 alignment, C2 the alignment evidence is sound, C3 pooling (0 difference over 66 children),
C4 the strip is behaviour-neutral and its value is the assertion, C5 MRL linearity, C6 the guards,
C7 the small fixture effect size (median cosine 0.9997), C8 the cost accounting.

## What the numbers actually say (do not overclaim)

- **Late chunking changes the vector by little on `test_book.pdf`** — late-vs-isolation cosine
  min 0.914 / median 0.9997. The acceptance case (a child opening on a dangling *"This"*) gives
  0.850. The fixture has tiny parents (max 547 tokens), so a child already contains most of its
  parent's context. The book's parents reach 5000 tokens, so the effect should be larger — a
  **prediction to re-measure at Step 10**, not a result.
- **The trailing-special-vector strip changes no vector.** The extra vector is last, so an
  offset-derived index list never includes it. Its value is the count assertion. Stated plainly in
  the module docstring and in §E3b rather than presented as a correctness fix.
