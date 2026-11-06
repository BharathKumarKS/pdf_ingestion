"""Mutation proof for the derived-embedder instruction fix. Mutates the REAL source, backup+restore.

Each mutation REPLACES with a wrong value (never deletes a line), so a failure is an assertion.
Uses the PROJECT venv interpreter.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CFG = ROOT / "src/core/config.py"
CE = ROOT / "src/pdf_ingestion/cluster_embedder.py"
TESTS = ROOT / "tests/test_derived_embedder_instruction.py"
OUT = Path(__file__).with_suffix(".json")

TESTS_LIST = [
    "test_derived_instruction_default_is_search_query",
    "test_derived_embedder_uses_the_derived_instruction",
    "test_arm_embedder_keeps_the_arms_instruction",
    "test_derived_instruction_is_overridable",
    "test_derived_embedder_dim_is_the_derived_dim",
]

MUTATIONS = [
    ("M1_derived_inherits_arm_instruction", CE,
     '                                     "dense_dim": cfg.derived_dense_dim,\n'
     '                                     "query_instruction": cfg.derived_query_instruction})',
     '                                     "dense_dim": cfg.derived_dense_dim})'),
    ("M2_default_is_not_search_query", CFG,
     '    derived_query_instruction: str = "search_query: "\n',
     '    derived_query_instruction: str = "Instruct: QWEN\\n"  # MUTATION\n'),
    ("M3_arm_uses_derived_instruction", CE,
     "        self._instruction = cfg.query_instruction\n",
     "        self._instruction = cfg.derived_query_instruction  # MUTATION\n"),
    ("M4_derived_dim_is_the_arms", CE,
     '                                     "dense_dim": cfg.derived_dense_dim,\n',
     '                                     "dense_dim": cfg.dense_dim,  # MUTATION\n'),
]


def _python() -> str:
    for cand in (ROOT / ".venv/bin/python", ROOT / ".venv/bin/python3"):
        if cand.exists():
            return str(cand)
    return sys.executable


def run_named() -> dict:
    e = dict(os.environ); e["PYTHONPATH"] = ""
    res = {}
    for t in TESTS_LIST:
        p = subprocess.run([_python(), "-m", "pytest", f"{TESTS}::{t}", "-q",
                            "-p", "no:cacheprovider", "--no-header"],
                           cwd=ROOT, capture_output=True, text=True, env=e, timeout=300)
        res[t] = "PASS" if p.returncode == 0 else "FAIL"
        if p.returncode != 0:
            for line in (p.stdout + p.stderr).splitlines():
                if line.lstrip().startswith("assert") or "AssertionError" in line:
                    res[t + "__why"] = line.strip()[:160]
                    break
    return res


def main() -> None:
    srcs = {CFG: CFG.read_text(), CE: CE.read_text()}
    backups = {f: f.with_suffix(f.suffix + ".bak_mut") for f in srcs}
    for f, b in backups.items():
        shutil.copy2(f, b)

    report = {"baseline": run_named(), "mutations": {}}
    try:
        for name, f, old, new in MUTATIONS:
            src = srcs[f]
            if old not in src:
                report["mutations"][name] = {"applied": False, "reason": "pattern not found"}
                continue
            mutated = src.replace(old, new, 1)
            assert mutated != src, "no-op substitution"
            f.write_text(mutated)
            report["mutations"][name] = {"applied": True, "results": run_named()}
            f.write_text(src)
    finally:
        for f, src in srcs.items():
            f.write_text(src)
            backups[f].unlink(missing_ok=True)

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    base = report["baseline"]
    allc = [k for k in base if not k.endswith("__why")]
    red = set()
    print("baseline:", {k: v for k, v in base.items() if not k.endswith("__why")})
    for m, r in report["mutations"].items():
        if not r.get("applied"):
            print(m, "NOT APPLIED"); continue
        rr = [k for k, v in r["results"].items() if not k.endswith("__why") and v == "FAIL"]
        red |= set(rr)
        print(f"{m}: {rr}")
    print(f"checks {len(allc)} reddened {len(red)} INERT: {sorted(set(allc) - red) or 'none'}")


if __name__ == "__main__":
    main()
