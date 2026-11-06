#!/usr/bin/env python3
"""Independent cross-family review of the three session-37 steps that had NO reviewer recorded:
P0 (config revert + width guard), R8 (injection + spotlighting) and C2 (tier-1 cheap heuristics).

Assembles an evidence pack and asks a DIFFERENT model family (``openai/gpt-oss-20b`` on the cluster
router, vs the author's deepseek) to CONFIRM or REFUTE each numbered claim by RE-DERIVING it.
Writes ``logs/p1/step10/guardrails_p0_r8_c2_review.json``.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_p0_r8_c2_review.py
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "logs" / "p1" / "step10" / "guardrails_p0_r8_c2_review.json"
ROUTER = "http://10.0.10.70:8000/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"

CLAIMS = """\
P1. (P0-a) config.py's DENSE defaults are the neutral Qwen-1024 world: dense_model is
    "Qwen/Qwen3-Embedding-0.6B", dense_dim is 1024, query_instruction is the "Instruct: ..." form,
    and document_prefix is "" (empty).
P2. (P0-b) .env carries the DEPLOYED nomic-768 values (DENSE_MODEL, DENSE_DIM, QUERY_INSTRUCTION,
    DOCUMENT_PREFIX) — the intended mechanism.
P3. (P0-c) the read-path width guard (store._assert_query_width) RAISES on a model/collection
    width mismatch on the main dense lane, instead of letting a 1024d query silently 400.
P4. (P0-d) tests/conftest.py pins the dense env so the suite is hermetic from a developer's .env.
P5. (P0-e) the P0 verifier passes 14/14.

R8a. check_injection is a regex pattern pass over known jailbreak phrases, returning a verdict with
     a boolean and the list of matched patterns.
R8b. spotlight is LOSSLESS datamarking: the marker REPLACES each space, so replacing the marker
     with a space restores the original text exactly.
R8c. SPOTLIGHT_MARKER is U+2063 (INVISIBLE SEPARATOR).
R8d. tests/test_guardrails_injection.py contains 5 tests and they pass.

C2a. cited_pages reads every citation format the generator emits — "[Page N]", the CJK bracket
     form, and "(page N)" — with ANY whitespace between the word and the number.
C2b. check_citation_validity separates cited pages that were retrieved (valid) from those that
     were not (invalid).
C2c. check_numbers_in_evidence is boundary-aware ('42' is NOT considered present inside '1042')
     and normalises thousands separators.
C2d. tests/test_guardrails_response_c2.py contains 10 tests, and the C2 mutation reddens 4/4 with
     no inert mutation.
"""

INSTRUCTIONS = """\
You are a meticulous, INDEPENDENT code reviewer. You did NOT write this code. For EACH numbered
claim below, output CONFIRMED or REFUTED, citing the specific line(s) or artifact value you
re-derived it from. Do NOT agree by default: actively look for the claim that is wrong. If a
claim's stated COUNT disagrees with what you can count in the evidence, REFUTE it and give the
correct number. End with a one-line summary "CONFIRMED n/13".
Format: "Px: CONFIRMED|REFUTED — <evidence>", one line per claim.
"""


def _section(path: Path, start_marker: str, end_marker: str | None = None) -> str:
    text = path.read_text()
    i = text.find(start_marker)
    if i == -1:
        return f"(marker not found: {start_marker})"
    j = text.find(end_marker, i) if end_marker else -1
    return text[i:j] if j != -1 else text[i:]


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout


def _count_tests(path: Path) -> int:
    return len(re.findall(r"^def test_", path.read_text(), flags=re.MULTILINE))


def main() -> int:
    py = str(ROOT / ".venv/bin/python")
    config = ROOT / "src/core/config.py"
    store = ROOT / "src/pdf_ingestion/store.py"
    request = ROOT / "src/core/guardrails/request.py"
    response = ROOT / "src/core/guardrails/response.py"

    r8_tests = ROOT / "tests/test_guardrails_injection.py"
    c2_tests = ROOT / "tests/test_guardrails_response_c2.py"

    evidence = {
        "CLAIMS": CLAIMS,
        "COUNTED: R8 tests": str(_count_tests(r8_tests)),
        "COUNTED: C2 tests": str(_count_tests(c2_tests)),
        "config.py — dense defaults (P1)": _section(config, "dense_model", "\n\n    # -- Phase"),
        "config.py — guardrail fields (P3)": _section(config, "# -- Guardrails (Week-6", "\n    # Phase 3"),
        "store.py — _assert_query_width (P3)": _section(store, "def _assert_query_width", "\ndef "),
        "store.py — the guard call site (P3)": _section(store, "_assert_query_width(query_vector", "\n")[:400],
        "tests/conftest.py — the dense env pin (P4)": _section(
            ROOT / "tests/conftest.py", "# ── §I119", "\n\n\n@"),
        "request.py — R8 injection + spotlight (R8a/R8b/R8c)": _section(request, "# ── R8 —"),
        "response.py — C2 tier-1 heuristics (C2a/C2b/C2c)": response.read_text()[:3600],
        "test_guardrails_injection.py (R8d)": r8_tests.read_text(),
        "test_guardrails_response_c2.py (C2d)": c2_tests.read_text(),
        "P0 VERIFIER OUTPUT (P5)": _run([py, "logs/p1/step10/p0_config_guard_verifier.py"]),
        "R7R8 MUTATION OUTPUT": _run([py, "logs/p1/step10/guardrails_r7r8_mutation.py"]),
        "C2 MUTATION OUTPUT (C2d)": _run([py, "logs/p1/step10/guardrails_c2_mutation.py"]),
        "TEST RUN (R8 + C2 + the other session-37 files)": _run(
            [py, "-m", "pytest", str(r8_tests), str(c2_tests), "-q"]),
    }
    prompt = INSTRUCTIONS + "\n\n" + "\n\n".join(
        f"===== {k} =====\n{v}" for k, v in evidence.items())

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
