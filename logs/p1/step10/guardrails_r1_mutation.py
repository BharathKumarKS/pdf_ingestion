#!/usr/bin/env python3
"""R1 mutation proof — every sanitizer behaviour is guarded by a test that reddens when it breaks.

Each mutation disables exactly one behaviour in `src/core/guardrails/sanitize.py`, runs its intended
test, and asserts the test FAILS; the source is restored byte-identical after every mutation. A
mutation whose test still passes means the check is INERT (guards nothing) and is reported as such.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_r1_mutation.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/core/guardrails/sanitize.py"
PY = str(ROOT / ".venv/bin/python")

# (id, old, new, the test that MUST redden)
MUTATIONS = [
    ("M1 NFKC fold disabled",
     'normalized = unicodedata.normalize("NFKC", input_text)', "normalized = input_text",
     "tests/test_guardrails_sanitize.py::test_nfkc_folds_styled_homoglyphs"),
    ("M2 zero-width strip disabled",
     'return _ZERO_WIDTH.sub("", no_control)', "return no_control",
     "tests/test_guardrails_sanitize.py::test_zero_width_characters_are_stripped"),
    ("M3 control/bidi strip disabled",
     'no_control = _CONTROL_BIDI.sub("", normalized)', "no_control = normalized",
     "tests/test_guardrails_sanitize.py::test_control_and_bidi_overrides_are_stripped"),
    ("M4 base64 decode disabled",
     '("base64", _try_base64_decode),', '("base64", lambda t: (t, False)),',
     "tests/test_guardrails_sanitize.py::test_base64_payload_is_decoded"),
    ("M5 url decode disabled",
     '("url", _try_url_decode),', '("url", lambda t: (t, False)),',
     "tests/test_guardrails_sanitize.py::test_url_encoding_is_decoded"),
    ("M6 script-consistency disabled",
     'return bool(_LATIN.search(text)) and bool(_CYRILLIC.search(text))', "return False",
     "tests/test_guardrails_sanitize.py::test_cyrillic_salted_latin_is_flagged"),
]


def _run(test: str) -> int:
    return subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True).returncode


def main() -> int:
    original = SRC.read_text()
    reddened, inert = [], []
    try:
        for name, old, new, test in MUTATIONS:
            assert original.count(old) == 1, f"{name}: anchor not unique ({original.count(old)})"
            SRC.write_text(original.replace(old, new))
            rc = _run(test)
            (reddened if rc != 0 else inert).append(name)
            print(f"  {'REDDENED' if rc != 0 else 'INERT   '}  {name}  → {test.split('::')[-1]}")
    finally:
        SRC.write_text(original)

    assert SRC.read_text() == original, "source not restored byte-identical"
    print(f"\n{len(reddened)}/{len(MUTATIONS)} mutations reddened their intended check; "
          f"inert: {inert or 'none'}")
    if inert:
        print("RESULT: FAIL — an inert check guards nothing")
        return 1
    print("RESULT: PASS — every mutation reddens exactly its intended check, no inert check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
