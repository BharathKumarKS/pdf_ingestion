#!/usr/bin/env python3
"""R7 (PII) + R8 (injection/spotlighting) mutation proof.

Mutates one behaviour at a time, runs the intended test, asserts it FAILS, restores byte-identical.
An inert mutation (test still green) guards nothing and is reported as such.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_r7r8_mutation.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PII = ROOT / "src/core/guardrails/pii.py"
REQ = ROOT / "src/core/guardrails/request.py"
PY = str(ROOT / ".venv/bin/python")
TP = "tests/test_guardrails_pii.py"
TI = "tests/test_guardrails_injection.py"

# (id, file, old, new, test that MUST redden)
MUTATIONS = [
    ("M1 Luhn check disabled", PII,
     "return checksum % 10 == 0", "return True", f"{TP}::test_non_luhn_digit_run_is_kept"),
    ("M2 email pattern disabled", PII,
     r'r"\b[\w\.-]+@[\w\.-]+\.\w+\b"', r'r"NEVER_MATCH_EMAIL"', f"{TP}::test_email_is_redacted"),
    ("M3 overlap merge disabled", PII,
     'cur_r = cur_r if cur_r == repl else "[REDACTED_PII]"', "cur_r = cur_r",
     f"{TP}::test_overlapping_spans_merge"),
    ("M4 AWS key pattern disabled", PII,
     r'r"\bAKIA[0-9A-Z]{16}\b"', r'r"NEVER_MATCH_AWS"', f"{TP}::test_aws_key_is_redacted"),
    ("M5 GitHub token pattern disabled", PII,
     r'r"\bghp_[A-Za-z0-9]{20,}\b"', r'r"NEVER_MATCH_GH"', f"{TP}::test_github_token_is_redacted"),
    ("M6 injection patterns emptied", REQ,
     "_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]",
     "_INJECTION_RE = []", f"{TI}::test_known_jailbreak_phrases_are_flagged"),
    ("M7 spotlight disabled", REQ,
     'return marker.join(text.split(" "))', "return text",
     f"{TI}::test_spotlight_inserts_the_marker_between_words"),
]


def _run(test: str) -> int:
    return subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True).returncode


def main() -> int:
    originals = {PII: PII.read_text(), REQ: REQ.read_text()}
    reddened, inert = [], []
    try:
        for name, path, old, new, test in MUTATIONS:
            src = originals[path]
            assert src.count(old) == 1, f"{name}: anchor not unique ({src.count(old)})"
            path.write_text(src.replace(old, new))
            rc = _run(test)
            (reddened if rc != 0 else inert).append(name)
            print(f"  {'REDDENED' if rc != 0 else 'INERT   '}  {name}  → {test.split('::')[-1]}")
            path.write_text(originals[path])  # restore after each
    finally:
        for p, txt in originals.items():
            p.write_text(txt)

    for p, txt in originals.items():
        assert p.read_text() == txt, f"{p} not restored byte-identical"
    print(f"\n{len(reddened)}/{len(MUTATIONS)} mutations reddened their intended check; inert: {inert or 'none'}")
    if inert:
        print("RESULT: FAIL — an inert check guards nothing")
        return 1
    print("RESULT: PASS — every mutation reddens exactly its intended check, no inert check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
