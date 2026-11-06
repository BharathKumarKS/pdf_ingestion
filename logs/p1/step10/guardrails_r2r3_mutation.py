#!/usr/bin/env python3
"""R2 + R3 mutation proof — every gate behaviour is guarded by a test that reddens when it breaks.

Each mutation disables one behaviour in `src/core/guardrails/request.py`, runs its intended test,
and asserts it FAILS; the source is restored byte-identical after each. A mutation whose test still
passes is INERT (guards nothing) and is reported as such.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_r2r3_mutation.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/core/guardrails/request.py"
PY = str(ROOT / ".venv/bin/python")
T = "tests/test_guardrails_request.py"

MUTATIONS = [
    ("M1 hard ceiling disabled",
     "hard = words > cfg.guard_hard_max_tokens", "hard = False",
     f"{T}::test_hard_ceiling_rejects"),
    ("M2 soft threshold disabled",
     "soft = words > cfg.guard_soft_warn_tokens", "soft = False",
     f"{T}::test_soft_threshold_warns_only"),
    ("M3 structural check disabled",
     "structural = _FENCE in text or bullets >= 3 or depth >= 3", "structural = False",
     f"{T}::test_code_fence_is_structural"),
    ("M4 long-repeat rung disabled",
     "if _REPEAT.search(lowered):", "if False:",
     f"{T}::test_long_repeat_is_rung_1"),
    ("M5 membership rung disabled",
     "hits = [t for t in tokens if t in _KNOWN_SMASHES]", "hits = []",
     f"{T}::test_known_smash_is_rung_1"),
    ("M6 vowel-less rung disabled",
     "if len(t) >= 4 and _vowel_ratio(t) == 0.0:", "if False:",
     f"{T}::test_vowel_less_token_is_rung_2"),
    ("M7 entropy rung disabled",
     "if entropy > cfg.guard_entropy_floor:", "if False:",
     f"{T}::test_high_entropy_is_rung_3"),
    ("M8 consonant/vowel ratio rung disabled",
     "if len(t) >= 5 and (1 - _vowel_ratio(t)) / max(_vowel_ratio(t), 1e-9) > 4.0:", "if False:",
     f"{T}::test_consonant_heavy_token_is_rung_2"),
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
    print(f"\n{len(reddened)}/{len(MUTATIONS)} mutations reddened their intended check; inert: {inert or 'none'}")
    if inert:
        print("RESULT: FAIL — an inert check guards nothing")
        return 1
    print("RESULT: PASS — every mutation reddens exactly its intended check, no inert check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
