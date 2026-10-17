"""Round 2 — hand the verifier its own round-1 finding back, on the fixed module.

Round 1 (``verdict.json``) returned ``passed: false`` on one logic_error: the zero-token-parent
branch called ``self._embed_isolated``, which does not exist (the method is ``embed_isolated``).
That is a REAL defect — it would raise AttributeError at runtime — and it is fixed. This round
asks the verifier to confirm the fix and to say whether anything else in the module is wrong.

Run:  uv run python logs/p1/step4/verify_readjudicate.py
Writes logs/p1/step4/verdict2.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODULE = (ROOT / "src/pdf_ingestion/late_chunk_embedder.py").read_text()
ROUND1 = (HERE / "verdict.json").read_text()

PROMPT = f"""You are an INDEPENDENT VERIFIER on a SECOND ROUND. Your round-1 verdict is below.

ROUND 1 FOUND: one logic_error — the zero-token-parent branch of ``embed_parent`` called
``self._embed_isolated(c)``, a method that does not exist. The author agrees: it is a real
AttributeError, it is fixed to ``self.embed_isolated(c)``, and a regression test was added
(``test_parent_that_tokenizes_to_zero_tokens_falls_back_to_isolation``). Every other claim was
confirmed.

YOUR TASK THIS ROUND — do not simply re-confirm. Check, against the CURRENT code:
  1. Is the reported defect actually fixed everywhere (grep the module for any remaining call to
     a method that is not defined)?
  2. Does the new regression test actually exercise that branch, or does it pass for the wrong
     reason (e.g. the parent being skipped earlier, or the fake tokenizer not being used)?
  3. Did the fix introduce any new defect?
  4. Is there any OTHER silent wrong answer in the module — a wrong value produced with no
     exception and no log line? Look specifically at: the token-index arithmetic
     (``te > start and ts < end``), the merge of ``token_span`` bounds, the normalisation
     order (normalise-then-slice vs slice-then-normalise), and ``embed_children``'s grouping.

ROUND-1 VERDICT:
<round1>
{ROUND1}
</round1>

CURRENT MODULE:
<module>
{MODULE}
</module>

Be terse in your reasoning: you have already read this code once. FAIL-CLOSED RULES:
- logic_errors non-empty -> passed false
- passed true ONLY when logic_errors is empty

Return ONLY this JSON:
{{
  "passed": true or false,
  "claims": [{{"id": "C1", "verdict": "confirmed|refuted|unverified", "reason": "..."}}],
  "logic_errors": ["..."],
  "suggestions": ["..."],
  "summary": "one sentence"
}}
"""


def main() -> int:
    t0 = time.time()
    r = httpx.post(
        "http://10.0.10.70:8000/v1/chat/completions",
        json={
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 32768,
            "temperature": 0,
        },
        timeout=1800,
    )
    dt = time.time() - t0
    body = r.json()
    ch = body["choices"][0]
    msg = ch["message"]
    content = msg.get("content") or ""
    print(
        f"status={r.status_code} time={dt:.0f}s finish={ch.get('finish_reason')} "
        f"tokens={body.get('usage', {}).get('prompt_tokens')}/"
        f"{body.get('usage', {}).get('completion_tokens')} "
        f"reasoning_chars={len(msg.get('reasoning_content') or msg.get('reasoning') or '')}"
    )
    try:
        verdict, _ = json.JSONDecoder().raw_decode(content[content.index("{"):])
        (HERE / "verdict2.json").write_text(json.dumps(verdict, indent=2))
        print(json.dumps(verdict, indent=2))
    except Exception as exc:  # noqa: BLE001
        print("PARSE FAIL:", exc)
        (HERE / "verdict2_raw.txt").write_text(content)
        print(repr(content[:800]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
