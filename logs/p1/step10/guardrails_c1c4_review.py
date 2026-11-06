#!/usr/bin/env python3
"""Independent cross-family review of the C1/C4 port (read-only).

Assembles an evidence pack (the ported code, the tests, the live-probe artifact, the verifier and
mutation outputs) and asks a DIFFERENT model family (``openai/gpt-oss-20b`` on the cluster router,
vs the author's deepseek) to CONFIRM or REFUTE each numbered claim by RE-DERIVING it — not by
agreeing. Writes the verdict to ``logs/p1/step10/guardrails_c1c4_review.json``.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_c1c4_review.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "logs" / "p1" / "step10" / "guardrails_c1c4_review.json"
ROUTER = "http://10.0.10.70:8000/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"

RESPONSE_PY = ROOT / "src/core/guardrails/response.py"
C1_TEST = ROOT / "tests/test_guardrails_response_c1.py"
C4_TEST = ROOT / "tests/test_guardrails_citation_c4.py"
PROBE = ROOT / "logs/p1/step10/c1_live_probe.json"

CLAIMS = """\
C1. The five lab modules are ported faithfully: ClaimExtractor (with the lab's sentence-split
    fallback), ClaimDocumentMatrixBuilder (the Cartesian product, keys claim_index/document_index/
    claim/document), SemanticSimilarityFilter (keeps only cosine > threshold, annotates
    semantic_similarity), NLIEntailmentChecker (entailment = the softmax prob of the model's
    entailment head; is_entailing = prob >= threshold), GroundednessEvaluator (a claim is grounded
    iff at least one retained edge entails it; score = grounded_count / len(claims)).
C2. The ONLY deviations from the lab are (a) the LLM client: call_llm replaces instructor+OpenAI,
    keeping the same ClaimExtraction schema and the same fallback; (b) the encoder/checker are
    injectable so an offline stand-in can be used. No algorithmic change to the lab's logic.
C3. _resolve_entailment_class_index is verbatim from the lab and resolves the model's own
    entailment head. The REAL model's id2label is {0: contradiction, 1: entailment, 2: neutral}.
C4. The offline stand-ins are deterministic and used ONLY under USE_STUB_NLI; the fast test suite
    never downloads a model.
C5. C4 (compute_citation_faithfulness) implements ALCE: citation recall = the fraction of ALL
    statements with at least one entailing citation; citation precision = the fraction of ALL
    citations that entail; both are None when the answer cites nothing.
C6. The live probe's ASSERTED checks (A1,A2,A4,A5,A6) pass; the REPORTED cells show the unrelated
    passage scoring entailment 0.99476, ABOVE the supporting passage's 0.99240 (separation gap
    -0.002359) — i.e. the base DeBERTa NLI model does NOT separate unrelated from entailing text.
C7. The verifier (guardrails_c1c4_verifier.py) is independent — its own statement splitter, its own
    citation regex, its own ALCE arithmetic — and passes 14/14.
C8. The mutation proof reddens 13/13 mutations with NO inert mutation.
C9. The two test files contain 33 tests in total.
"""

INSTRUCTIONS = """\
You are a meticulous, INDEPENDENT code reviewer. You did NOT write this code. For EACH numbered
claim below, output a verdict of CONFIRMED or REFUTED, and cite the specific line(s) or artifact
value you re-derived it from. Do NOT agree by default: actively look for the claim that is wrong.
If a claim's stated count or number disagrees with what you can count in the evidence, REFUTE it
and give the correct number. Finish with a one-line summary "CONFIRMED n/9".
Output plain text, one block per claim: "Cx: CONFIRMED|REFUTED — <evidence>".
"""


def _slice(path: Path, marker: str) -> str:
    text = path.read_text()
    idx = text.find(marker)
    return text[idx:] if idx != -1 else text


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout


def main() -> int:
    py = str(ROOT / ".venv/bin/python")
    evidence = {
        "CLAIMS": CLAIMS,
        "PORTED CODE (src/core/guardrails/response.py, C1 section onward)":
            _slice(RESPONSE_PY, "# C1 — the assertion"),
        "TEST FILE tests/test_guardrails_response_c1.py": C1_TEST.read_text(),
        "TEST FILE tests/test_guardrails_citation_c4.py": C4_TEST.read_text(),
        "LIVE PROBE ARTIFACT logs/p1/step10/c1_live_probe.json":
            PROBE.read_text() if PROBE.exists() else "(missing)",
        "VERIFIER OUTPUT": _run([py, "logs/p1/step10/guardrails_c1c4_verifier.py"]),
        "MUTATION OUTPUT": _run([py, "logs/p1/step10/guardrails_c1c4_mutation.py"]),
        "TEST RUN": _run([py, "-m", "pytest", str(C1_TEST), str(C4_TEST), "-q"]),
    }
    prompt = INSTRUCTIONS + "\n\n" + "\n\n".join(
        f"===== {k} =====\n{v}" for k, v in evidence.items()
    )

    import httpx
    resp = httpx.post(ROUTER, json={
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 4000,
    }, timeout=600)
    resp.raise_for_status()
    verdict = resp.json()["choices"][0]["message"]["content"]
    OUT.write_text(json.dumps({"model": MODEL, "verdict": verdict}, indent=2), encoding="utf-8")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
