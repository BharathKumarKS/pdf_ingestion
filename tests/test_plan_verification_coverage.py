"""The verification-completeness gate — bound to the suite so it cannot be skipped.

The contract ("every step carries an acceptance check + independent reviewer + stdlib verifier +
mutation proof") used to live only as prose in the plan, so a step with a MISSING reviewer was
indistinguishable from a step with one. This test makes that failure mechanical: it parses each
plan's status table and fails if any ``✅ DONE`` row lacks a verifier, a mutation proof, a resolvable
reviewer, or names a path that does not exist.

The gate is deterministic (no model, no judgment), which is why it needs no verifier of its own —
and it is a test, which is why it cannot be forgotten. Every plan with a status table is listed in
``PLANS`` below; add a plan here when its status table is created, so it is policed from day one.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_plan_coverage import find_gaps  # noqa: E402

PLANS = [
    ".hermes/plans/2026-11-05-p1-guardrails-course-aligned-SESSIONS.md",
    ".hermes/plans/2026-11-06-p1-visual-lane-aperture-SESSIONS.md",
]


def test_every_done_step_has_verifier_mutation_and_reviewer():
    gaps: list[str] = []
    for plan in PLANS:
        gaps.extend(f"{plan}: {g}" for g in find_gaps(ROOT, ROOT / plan))
    assert gaps == [], "verification completeness gaps:\n" + "\n".join(gaps)


def test_every_listed_plan_exists_and_has_a_status_table():
    """A plan listed above must exist AND expose a parseable status table — otherwise the gate is
    silently guarding nothing for that plan."""
    from scripts.verify_plan_coverage import _status_rows
    for plan in PLANS:
        text = (ROOT / plan).read_text(encoding="utf-8")
        assert _status_rows(text), f"{plan}: no status rows parsed"


def test_the_gate_catches_a_missing_reviewer(tmp_path):
    """The gate must actually redden — a check that cannot fail guards nothing."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## 8. Status table\n\n"
        "| id | step | status | verifier | mutation |\n"
        "|---|---|---|---|---|\n"
        "| X1 | a done step | ✅ **DONE** | ✅ `tests/foo.py` 3/3 | ✅ mutation 3/3 |\n",
        encoding="utf-8",
    )
    gaps = find_gaps(ROOT, plan)
    assert any("no resolvable independent reviewer" in g for g in gaps), gaps


def test_the_gate_catches_a_missing_artifact(tmp_path):
    """A row that names a verifier artifact which does not exist must be caught."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## 8. Status table\n\n"
        "| id | step | status | verifier | mutation |\n"
        "|---|---|---|---|---|\n"
        "| X2 | a done step | ✅ **DONE** | ✅ `logs/does_not_exist_xyz.py` 3/3; reviewer `deleg_abcdef` | ✅ mutation 3/3 |\n",
        encoding="utf-8",
    )
    gaps = find_gaps(ROOT, plan)
    assert any("referenced path does not exist" in g for g in gaps), gaps


def test_a_blank_step_is_not_required_to_have_anything(tmp_path):
    """Rows that are not DONE are out of scope — the gate only polices finished work."""
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## 8. Status table\n\n"
        "| id | step | status | verifier | mutation |\n"
        "|---|---|---|---|---|\n"
        "| X3 | not started | ⬜ | ⬜ | ⬜ |\n",
        encoding="utf-8",
    )
    assert find_gaps(ROOT, plan) == []
