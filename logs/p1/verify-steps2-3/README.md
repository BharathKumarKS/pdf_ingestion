# Independent verification of P1 Steps 2–3 — 2026-10-17

Review of `9a788a2` (Step 2, `parent_chunker.py` + `models.py`) and `7a776cb` (Step 3,
`chunker.py` → chonkie `SemanticChunker`). The adjudicated fixes landed in `7781d30`.

## Setup

Verifier model: **`openai/gpt-oss-20b`** on the cluster (`http://10.0.10.70:8000`) — a *different*
model from the author's (`deepseek/deepseek-v4.1-flash`). Configured as `delegation.model` in
`~/.hermes/config.yaml`; `delegation.fallback_providers` was set to `[]` so a cluster outage fails
loudly instead of silently degrading the verifier into the author's own model.

**The verifier runs single-turn with the evidence embedded.** The first attempt was a tool-using
subagent: it worked for 25 API calls (independently re-deriving C1 from Docling objects) and then
the provider rejected the request as malformed — the model's harmony control tokens
(`<|channel|>commentary`) had leaked into message content and the server could not parse the
replayed history. Single-turn tool calling on the same endpoint works, so it is a multi-turn
protocol limit, not a capability one.

## Files

| File | What it is |
|---|---|
| `verify_evidence.py` → `evidence.json` | Author's evidence pack for claims C1–C7 |
| `diag_e3.py` | The corrected C2 check (per parent, its OWN elements, forward-only cursor) |
| `counter_evidence.py` → `counter.json` | Counter-evidence for the three logic_errors |
| `diag_disagree.py` → `diag.json` | The per-character oracle check that settles C2 |
| `verify_singleturn.py` → `verdict.json` | Verifier round 1 |
| `verify_readjudicate.py` → `verdict2.json` | Verifier round 2 (counter-evidence handed back) |

## Outcome

Verifier round 1: C1/C4/C5/C6 confirmed; **C2 refuted**; C3/C7 unverified; three logic_errors.

Adjudication:

| Finding | Verdict | Evidence |
|---|---|---|
| A parent with no provenance silently gave children `page_number=None` | **REAL — fixed** | `_to_parent` now warns; test added. Found by a direct probe, not the subagent. |
| "formula elements are not added to `page_map`" | **Rejected** | 15/15 formula pages present in the map; `if span and start >= span` cannot fire when `span == 0` |
| "`_page_for_offset` is not defined" | **Rejected** | Defined at `chunker.py:251`; the verifier was shown a diff |
| "the merge keeps a stale `page_number`" | **By design, pre-existing** | `page_number` is the page of the chunk's START everywhere here; now stated in a comment |
| C2 refuted | **Withdrawn** | Its basis (20 "mismatches") was 20/20 elements that are NOT members of the parent tested |

## The part worth remembering

C2 took **four** attempts to check, and the first two checks were wrong:

```
1st  all elements x all parents           -> 20 / 194   wrong: 20/20 were non-members
2nd  each parent's own elements           -> 0 / 169    right, element-granularity only
3rd  per sampled character, single page   -> 114 / 5555 wrong: a page-spanning element has 2 pages
4th  per character, per-charspan oracle   -> 0 / 5555   correct
```

The oracle throughout is Docling's own per-element `prov` — independent of the code under test.
The verifier's suspicion that the corrected check had been "shaped to agree with the code" was
worth having; only evidence answered it.

**Caveat on round 2.** The re-adjudication that flipped C2 to `confirmed` took **6 s and 1,157
tokens** against 57–92 s and 10k+ for round 1, and withdrew all three findings at once. That is
cheap agreement after being handed counter-evidence, not reasoning. **The mechanical checks settle
C2, not the reversal.**
