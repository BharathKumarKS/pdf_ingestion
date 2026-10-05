#!/usr/bin/env python3
"""
Eval gate — fail when a retrieval metric regresses against a committed baseline.

P0 item 6. The project's headline numbers were once compared across incompatible
scales (v9 measured Recall@20, v10 Recall@100) and against a dirty index, so part
of a reported "improvement" was a measurement artefact. This gate:

  - refuses to compare two artifacts whose metric column uses a different K,
    because a wider candidate pool is not a better system; and
  - fails (exit 1) when the candidate drops more than ``--tolerance`` below the
    baseline on the chosen metric.

It reads the ``## Summary`` table of an ``evaluate_rag.py`` artifact, so it needs
no Qdrant / models and runs anywhere (locally or in CI).

Usage:
  uv run python scripts/eval_gate.py \\
      --baseline  data/eval_results/p0-plumbing-check_2026-10-04_0440.md \\
      --candidate data/eval_results/<new-run>.md

Exit codes:
  0  candidate is within tolerance of the baseline (pass)
  1  candidate regressed beyond tolerance (fail the build)
  2  the artifacts are not comparable (mismatched K, or metric missing)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# metric key -> pattern matched against a summary header cell; a capture group
# means the metric carries a K (e.g. "Recall@100" -> k=100).
_METRIC_PATTERNS = {
    "recall":    r"recall@(\d+)",
    "mrr":       r"mrr",
    "precision": r"precision@(\d+)",
    "ndcg":      r"ndcg@(\d+)",
}


def _summary_rows(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """Return (header_cells, {scope_name: row_cells}) from the ## Summary table."""
    m = re.search(r"##\s+Summary\s*\n(.*?)(?:\n##|\Z)", text, re.S)
    if not m:
        raise ValueError("no '## Summary' section found")

    lines = [ln for ln in m.group(1).splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        raise ValueError("summary table has no data rows")

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = cells(lines[0])
    body: dict[str, list[str]] = {}
    for line in lines[1:]:
        row = cells(line)
        if row and row[0]:
            body[row[0]] = row
    return header, body


def _metric(header: list[str], row: list[str], metric: str) -> tuple[float | None, int | None]:
    """Return (value, k) for the metric in a header/row pair, or (None, k)."""
    pat = _METRIC_PATTERNS[metric]
    for i, cell in enumerate(header):
        m = re.match(pat + r"$", cell.strip(), re.I)
        if not m:
            continue
        k = int(m.group(1)) if m.groups() else None
        raw = row[i] if i < len(row) else "—"
        if raw in ("—", "-", ""):
            return None, k
        return float(raw), k
    return None, None


def main() -> int:
    p = argparse.ArgumentParser(description="Fail on a retrieval-metric regression")
    p.add_argument("--baseline", required=True, help="reference artifact (.md)")
    p.add_argument("--candidate", required=True, help="artifact under test (.md)")
    p.add_argument("--metric", default="recall", choices=sorted(_METRIC_PATTERNS))
    p.add_argument("--scope", default="Overall", help="summary row to compare (default Overall)")
    p.add_argument("--tolerance", type=float, default=0.02,
                   help="allowed absolute drop before failing (default 0.02)")
    args = p.parse_args()

    try:
        b_head, b_body = _summary_rows(Path(args.baseline).read_text())
        c_head, c_body = _summary_rows(Path(args.candidate).read_text())
    except (OSError, ValueError) as exc:
        print(f"CANNOT COMPARE: {exc}")
        return 2

    if args.scope not in b_body or args.scope not in c_body:
        print(f"CANNOT COMPARE: scope '{args.scope}' missing from "
              f"{'baseline' if args.scope not in b_body else 'candidate'}")
        return 2

    b_val, b_k = _metric(b_head, b_body[args.scope], args.metric)
    c_val, c_k = _metric(c_head, c_body[args.scope], args.metric)

    if b_val is None or c_val is None:
        print(f"CANNOT COMPARE: metric '{args.metric}' is absent/empty for scope "
              f"'{args.scope}'")
        return 2

    if b_k != c_k:
        print(f"CANNOT COMPARE: baseline measures {args.metric}@{b_k} but candidate "
              f"measures {args.metric}@{c_k} — different candidate pools are not "
              f"comparable (widen/narrow the funnel deliberately, not silently)")
        return 2

    k = f"@{b_k}" if b_k is not None else ""
    delta = c_val - b_val
    print(f"scope     : {args.scope}")
    print(f"baseline  : {args.metric}{k} = {b_val:.4f}   ({Path(args.baseline).name})")
    print(f"candidate : {args.metric}{k} = {c_val:.4f}   ({Path(args.candidate).name})")
    print(f"delta     : {delta:+.4f}   (fail if < -{args.tolerance:.4f})")

    if delta < -args.tolerance:
        print(f"\nFAIL: {args.metric}{k} regressed by {abs(delta):.4f} "
              f"(tolerance {args.tolerance:.4f})")
        return 1

    print("\nPASS: candidate is within tolerance of the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
