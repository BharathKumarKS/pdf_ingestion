#!/usr/bin/env python
"""Simple verifier for the min_chunk_tokens A/B experiment.

The verifier expects a JSON artifact produced by the A/B run.  It checks that the child
counts for each arm match the expected numbers from the pre‑registration and reports any
mismatches.  It supports a ``--check`` flag that exits with status 1 when a mismatch is
found.

The script is intentionally lightweight and uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXPECTED_COUNTS = {
    "C": 3796,
    "T0": 5715,
    "T16": None,  # not evaluated by the harness
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify min_chunk_tokens results")
    parser.add_argument("--artifact", type=Path, default="logs/p1/step10/min_chunk_tokens_ab.json")
    parser.add_argument("--check", action="store_true", help="exit with non‑zero on mismatch")
    args = parser.parse_args()
    if not args.artifact.exists():
        print(f"artifact {args.artifact} not found", file=sys.stderr)
        return 1
    try:
        data = json.loads(args.artifact.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"failed to parse JSON: {exc}", file=sys.stderr)
        return 1
    mismatches = []
    for arm, exp in EXPECTED_COUNTS.items():
        got = data.get("children_counts", {}).get(arm)
        if exp is None:
            continue
        if got != exp:
            mismatches.append((arm, exp, got))
    if mismatches:
        for arm, exp, got in mismatches:
            print(f"mismatch arm {arm}: expected {exp}, got {got}")
        if args.check:
            return 1
    else:
        print("all child counts match expected values")
    return 0

if __name__ == "__main__":
    sys.exit(main())
