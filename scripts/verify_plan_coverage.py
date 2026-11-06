#!/usr/bin/env python3
"""Deterministic completeness gate for a plan's verification status table.

The problem this closes: a plan states a per-step verification contract (acceptance + independent
reviewer + stdlib verifier + mutation proof), but nothing checks the table against reality — so a
step with a MISSING reviewer looks exactly like a step with one, and the omission is invisible.

This gate is deterministic on purpose (no model, no judgment): for every ``✅ DONE`` row in a
plan's status table it asserts

  * the verifier cell is non-empty (not ``⬜``),
  * the mutation cell is non-empty (not ``⬜``),
  * the row resolves an independent reviewer — either a ``deleg_*`` id or a ``…review…`` artifact,
  * every backticked ``path/like/this`` token in the row EXISTS on disk.

A deterministic gate needs no verifier of its own. It is bound to the test suite
(``tests/test_plan_verification_coverage.py``) so it cannot itself be skipped.

    unset PYTHONPATH && .venv/bin/python scripts/verify_plan_coverage.py [plan.md ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_PLAN = Path(".hermes/plans/2026-11-05-p1-guardrails-course-aligned-SESSIONS.md")

_CODE_SPAN = re.compile(r"`([^`]*)`")                # a single backticked code span
_DELEG_ID = re.compile(r"deleg_[0-9a-f]{6,}")
_EMPTY = ("", "⬜")


def _is_path(token: str) -> bool:
    """True when a code span names a FILE path (has a '/' AND an extension in its last segment).

    Guards against false positives like the model id ``openai/gpt-oss-20b`` — a slash but no file
    extension — which is a name, not a path that must exist on disk.
    """
    if "/" not in token:
        return False
    return "." in token.rsplit("/", 1)[-1]


def _path_tokens(text: str) -> list[str]:
    """Every backticked code span in ``text`` that names a file path."""
    return [t for t in _CODE_SPAN.findall(text) if _is_path(t)]


def _status_rows(text: str) -> list[list[str]]:
    """The rows of the status table under '## 8. Status table' (5+ cells), as cell lists.

    The scan stops at the next '## ' heading, so a table in a later section is never mistaken for
    a status row.
    """
    start = text.find("## 8. Status table")
    if start == -1:
        raise ValueError("no '## 8. Status table' section found")
    body = text[start:]
    nxt = body.find("\n## ", 1)
    if nxt != -1:
        body = body[:nxt]
    rows: list[list[str]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and set("".join(cells)) <= set("-: "):
            continue  # the separator row
        if len(cells) >= 5 and cells[0] not in ("id",):
            rows.append(cells)
    return rows


def find_gaps(root: Path, plan_path: Path) -> list[str]:
    """Every completeness gap in the plan's status table, as human-readable strings."""
    root = Path(root)
    rows = _status_rows(Path(plan_path).read_text(encoding="utf-8"))
    gaps: list[str] = []

    for cells in rows:
        step_id, status, verifier, mutation = cells[0], cells[2], cells[3], cells[4]
        if "DONE" not in status.upper():
            continue
        if verifier in _EMPTY:
            gaps.append(f"{step_id}: DONE but no verifier recorded")
        if mutation in _EMPTY:
            gaps.append(f"{step_id}: DONE but no mutation proof recorded")
        row_text = " | ".join(cells)
        spans = _path_tokens(row_text)
        has_review = bool(_DELEG_ID.search(row_text)) or any(
            "review" in token.lower() and (root / token).exists() for token in spans
        )
        if not has_review:
            gaps.append(f"{step_id}: DONE but no resolvable independent reviewer "
                        "(no `deleg_*` id and no existing `…review…` artifact)")
        for token in spans:
            if not (root / token).exists():
                gaps.append(f"{step_id}: referenced path does not exist: {token}")
    return gaps


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    plans = [Path(a) for a in argv[1:]] or [DEFAULT_PLAN]
    all_gaps: list[str] = []
    for plan in plans:
        print(f"plan: {plan}")
        gaps = find_gaps(root, root / plan)
        all_gaps.extend(f"{plan}: {g}" for g in gaps)
        for g in gaps:
            print(f"  GAP  {g}")
        if not gaps:
            print("  OK   every DONE step has a verifier, a mutation proof and a reviewer")
    print(f"\n{len(all_gaps)} gap(s)")
    return 1 if all_gaps else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
