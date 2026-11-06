"""Mutation proof for §G5/§I2 (graph multi-hop). Mutates the REAL source in place, backup+restore.

Each mutation REPLACES with a no-op / wrong value (never deletes a line), so a failure is an
assertion, not a syntax/collection error. Runs each test individually and records the vector.
Uses the PROJECT venv interpreter (.venv/bin/python) — the agent's own python has no deps and
would give a red baseline that makes every mutation look discriminating.
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
GB = ROOT / "src/pdf_ingestion/graph_builder.py"
TESTS = ROOT / "tests/test_graph_multihop.py"
OUT = Path(__file__).with_suffix(".json")

TESTS_LIST = [
    "test_default_setting_is_one",
    "test_default_path_emits_no_traversal",
    "test_expansion_traverses_and_reports_real_hops",
    "test_hop_distance_is_not_constant",
    "test_hop_bound_is_clamped",
    "test_seed_only_when_max_hops_is_zero",
]

# (name, file, old, new)
MUTATIONS = [
    ("M1_default_setting_is_two", CFG,
     "    graph_max_hops: int = 1\n",
     "    graph_max_hops: int = 2  # MUTATION\n"),
    ("M2_branch_always_legacy", GB,
     "        if max_hops == 1:\n",
     "        if True:  # MUTATION\n"),
    ("M3_clamp_removed", GB,
     '        max_hops = max(1, min(int(getattr(self._cfg, "graph_max_hops", 1) or 1), 2))\n',
     '        max_hops = max(1, int(getattr(self._cfg, "graph_max_hops", 1) or 1))  # MUTATION\n'),
    ("M4_hop_distance_hardcoded_zero", GB,
     '                    "hop_distance": int(r["hop_distance"]),\n',
     '                    "hop_distance": 0,  # MUTATION\n'),
    ("M5_branch_inverted_default_traverses", GB,
     "        if max_hops == 1:\n",
     "        if max_hops != 1:  # MUTATION\n"),
]


def _python() -> str:
    for cand in (ROOT / ".venv/bin/python", ROOT / ".venv/bin/python3"):
        if cand.exists():
            return str(cand)
    return sys.executable


def run_named() -> dict:
    e = dict(os.environ)
    e["PYTHONPATH"] = ""
    res = {}
    for t in TESTS_LIST:
        p = subprocess.run(
            [_python(), "-m", "pytest", f"{TESTS}::{t}", "-q", "-p", "no:cacheprovider",
             "--no-header"],
            cwd=ROOT, capture_output=True, text=True, env=e, timeout=300)
        res[t] = "PASS" if p.returncode == 0 else "FAIL"
        if p.returncode != 0:
            for line in (p.stdout + p.stderr).splitlines():
                if line.lstrip().startswith("assert") or "AssertionError" in line:
                    res[t + "__why"] = line.strip()[:160]
                    break
    return res


def main() -> None:
    srcs = {CFG: CFG.read_text(), GB: GB.read_text()}
    backups = {}
    for f in srcs:
        b = f.with_suffix(f.suffix + ".bak_mut")
        shutil.copy2(f, b)
        backups[f] = b

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
            f.write_text(src)  # restore before the next
    finally:
        for f, src in srcs.items():
            f.write_text(src)
            backups[f].unlink(missing_ok=True)

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
