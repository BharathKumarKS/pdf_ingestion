#!/usr/bin/env python3
"""C2 mutation proof — every tier-1 cheap heuristic is guarded by a test that reddens when broken.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_c2_mutation.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/core/guardrails/response.py"
PY = str(ROOT / ".venv/bin/python")
T = "tests/test_guardrails_response_c2.py"

MUTATIONS = [
    ("M1 citation regex narrowed to ASCII-only",
     r'_CITATION_RE = re.compile(r"[\[【(]\s*[Pp]age\s*(\d+)\s*[\]】)]")',
     r'_CITATION_RE = re.compile(r"\[Page (\d+)\]")',
     f"{T}::test_cited_pages_reads_every_emitted_format"),
    ("M2 citation validity never flags an invalid page",
     "return CitationValidity(cited=cited, valid=cited & retrieved, invalid=cited - retrieved)",
     "return CitationValidity(cited=cited, valid=cited & retrieved, invalid=set())",
     f"{T}::test_citation_to_an_unretrieved_page_is_invalid"),
    ("M3 number match loses its boundary",
     r'if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.])", evidence_norm)',
     r'if not re.search(rf"{re.escape(n)}", evidence_norm)',
     f"{T}::test_number_match_is_boundary_aware"),
    ("M4 thousands separators not normalised",
     'n = m.group(0).replace(",", "")', "n = m.group(0)",
     f"{T}::test_thousands_separators_are_normalised"),
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
