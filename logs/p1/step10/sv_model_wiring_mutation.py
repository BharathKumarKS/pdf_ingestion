#!/usr/bin/env python3
"""Mutation proof for the §I117 wiring verifier — every check reddened by >=1 mutation.

Each mutation edits the REAL source, runs the verifier in a FRESH subprocess (so the mutated
module is re-imported), records the checks that go red, then restores the file BYTE-IDENTICAL.

Run:  .venv/bin/python logs/p1/step10/sv_model_wiring_mutation.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VER = ROOT / "logs/p1/step10/sv_model_wiring_verifier.py"
FILES = {
    "colbert": ROOT / "src/pdf_ingestion/colbert_embedder.py",
    "splade": ROOT / "src/pdf_ingestion/splade_embedder.py",
    "config": ROOT / "src/core/config.py",
}

COLBERT_OR = "cfg.sv_colbert_model or cfg.colbert_model"
SPARSE_OR = "cfg.sv_sparse_model or cfg.splade_model"

MUTATIONS = [
    ("MA colbert: drop the sv_colbert_model preference", "colbert", COLBERT_OR, "cfg.colbert_model"),
    ("MB colbert: break the EMPTY fallback", "colbert", COLBERT_OR, 'cfg.sv_colbert_model or "BOGUS"'),
    ("MC colbert: drop the model from the payload", "colbert",
     'json={"model": self._model, "input": batch, "is_query": is_query}',
     'json={"model": "WRONG", "input": batch, "is_query": is_query}'),
    ("MD sparse: drop the sv_sparse_model preference", "splade", SPARSE_OR, "cfg.splade_model"),
    ("ME sparse: break the EMPTY fallback", "splade", SPARSE_OR, 'cfg.sv_sparse_model or "BOGUS"'),
    ("MF sparse: drop the model from the payload", "splade",
     'json={"model": self._model, "input": batch}', 'json={"model": "WRONG", "input": batch}'),
    ("MG config: make the sv_colbert_model default non-empty", "config",
     'sv_colbert_model: str = ""', 'sv_colbert_model: str = "X"'),
    ("MH config: make the sv_sparse_model default non-empty", "config",
     'sv_sparse_model: str = ""', 'sv_sparse_model: str = "X"'),
]


def _run_verifier() -> dict[str, bool]:
    out = subprocess.run([sys.executable, str(VER)], capture_output=True, text=True).stdout
    res: dict[str, bool] = {}
    for line in out.splitlines():
        s = line.strip()
        if s.startswith(("PASS", "FAIL")):
            parts = s.split()
            res[parts[1]] = parts[0] == "PASS"
    return res


def main() -> int:
    baseline = _run_verifier()
    if not baseline or not all(baseline.values()):
        print("BASELINE NOT GREEN:", [k for k, v in baseline.items() if not v])
        return 1
    print(f"baseline green ({len(baseline)} checks)\n")

    reddened = {k: 0 for k in baseline}
    for label, key, old, new in MUTATIONS:
        path = FILES[key]
        original = path.read_bytes()
        text = original.decode()
        n = text.count(old)
        if n != 1:
            print(f"  {label:<52} -> SKIPPED (anchor found {n}x, expected 1)")
            continue
        try:
            path.write_text(text.replace(old, new))
            res = _run_verifier()
        finally:
            path.write_bytes(original)          # restore byte-identical
        assert path.read_bytes() == original, f"FAILED TO RESTORE {path}"
        red = [k for k, ok in res.items() if not ok]
        for k in red:
            reddened[k] += 1
        print(f"  {label:<52} -> reddened {len(red)}: {', '.join(sorted(red)) or 'NONE'}")

    inert = [k for k, v in reddened.items() if v == 0]
    print(f"\nchecks reddened by >=1 mutation: {sum(1 for v in reddened.values() if v)}/{len(reddened)}")
    if inert:
        print("INERT CHECK(S):", inert)
        return 1
    print("MUTATION PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
