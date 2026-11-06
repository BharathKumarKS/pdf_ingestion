#!/usr/bin/env python3
"""R5 mutation proof — every domain-gate behaviour is guarded by a test that reddens when it breaks.

Mutates `src/core/intent_router.py` one behaviour at a time, runs the intended test, asserts it
FAILS, restores byte-identical. An inert mutation (test still green) guards nothing and is reported.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_r5_mutation.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/core/intent_router.py"
PY = str(ROOT / ".venv/bin/python")
T = "tests/test_guardrails_domain_gate.py"

MUTATIONS = [
    ("M1 out_of_scope route gains a lane",
     "Intent.OUT_OF_SCOPE: RouteConfig(use_vector=False, use_raptor=False, use_graph=False, use_colpali=False),",
     "Intent.OUT_OF_SCOPE: RouteConfig(use_vector=True, use_raptor=False, use_graph=False, use_colpali=False),",
     f"{T}::test_out_of_scope_route_refuses"),
    ("M2 is_refusal always False",
     "return not (route.use_vector or route.use_raptor or route.use_graph or route.use_colpali)",
     "return False",
     f"{T}::test_out_of_scope_route_refuses"),
    ("M3 reject threshold disabled",
     "if p_out >= self._cfg.guard_domain_out_conf:", "if False:",
     f"{T}::test_gate_rejects_when_confidently_off_domain"),
    ("M4 admit threshold disabled",
     "if p_out <= self._cfg.guard_domain_in_conf:", "if False:",
     f"{T}::test_gate_admits_when_confidently_in_domain"),
    ("M5 no-class neutrality inverted",
     'return GateDecision(intent, "in", 0.0, False)', 'return GateDecision(intent, "out", 1.0, True)',
     f"{T}::test_gate_is_neutral_without_the_class"),
    ("M6 prototype-mode refusal disabled",
     "refuse = intent is Intent.OUT_OF_SCOPE", "refuse = False",
     f"{T}::test_gate_refuses_in_prototype_mode_on_an_explicit_label"),
    ("M7 ambiguous band rejects",
     'return GateDecision(intent, "ambiguous", p_out, False)', 'return GateDecision(intent, "out", p_out, True)',
     f"{T}::test_gate_escalates_in_the_uncertainty_band"),
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
