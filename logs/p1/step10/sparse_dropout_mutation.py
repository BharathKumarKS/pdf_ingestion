"""Mutation proof for the sparse-lane dropout counter (§I96).

Proves each new check DISCRIMINATES: apply one targeted string substitution to the REAL
store.py, run each sparse test individually, record pass/fail, restore. A check that no
mutation reddens is inert. Mutations REPLACE with a no-op (never delete a line) so a failure
is an assertion, not a syntax/collection error.

Writes logs/p1/step10/sparse_dropout_mutation.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "src/pdf_ingestion/store.py"
TESTS = ROOT / "tests/test_lane_dropout_counters.py"
OUT = Path(__file__).with_suffix(".json")

SPARSE_TESTS = [
    "test_sparse_failure_increments_the_counter",
    "test_sparse_success_does_not_increment",
    "test_sparse_counter_accumulates_across_queries",
    "test_counters_start_at_zero",
]

MUTATIONS = [
    ("M1_counter_not_incremented_on_failure",
     "                self.sparse_dropouts += 1\n",
     "                pass  # MUTATION\n"),
    ("M2_counter_incremented_on_success_too",
     '                lane_names.append("sparse")\n',
     '                lane_names.append("sparse")\n'
     '                self.sparse_dropouts += 1  # MUTATION\n'),
    ("M3_starts_at_one",
     "        self.sparse_dropouts: int = 0\n",
     "        self.sparse_dropouts: int = 1  # MUTATION\n"),
]


def _python() -> str:
    """The PROJECT venv interpreter — never the agent's own python (no project deps there)."""
    for cand in (ROOT / ".venv/bin/python", ROOT / ".venv/bin/python3"):
        if cand.exists():
            return str(cand)
    return sys.executable


def run_named() -> dict:
    """Run each sparse test individually so we know exactly which passed/failed."""
    e = dict(os.environ)
    e["PYTHONPATH"] = ""
    res = {}
    for t in SPARSE_TESTS:
        p = subprocess.run(
            [_python(), "-m", "pytest", f"{TESTS}::{t}", "-q", "-p", "no:cacheprovider",
             "--no-header"],
            cwd=ROOT, capture_output=True, text=True, env=e, timeout=300)
        res[t] = "PASS" if p.returncode == 0 else "FAIL"
        if p.returncode != 0:
            for line in (p.stdout + p.stderr).splitlines():
                if "Error" in line or line.lstrip().startswith("assert"):
                    res[t + "__why"] = line.strip()[:200]
                    break
    return res


def main() -> None:
    src = STORE.read_text()
    backup = STORE.with_suffix(".py.bak_mut")
    shutil.copy2(STORE, backup)

    report = {"baseline": run_named(), "mutations": {}}
    try:
        for name, old, new in MUTATIONS:
            if old not in src:
                report["mutations"][name] = {"applied": False, "reason": "pattern not found"}
                continue
            mutated = src.replace(old, new, 1)
            assert mutated != src, "no-op substitution"
            STORE.write_text(mutated)
            report["mutations"][name] = {"applied": True, "results": run_named()}
            STORE.write_text(src)  # restore before the next
    finally:
        STORE.write_text(src)
        backup.unlink(missing_ok=True)

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
