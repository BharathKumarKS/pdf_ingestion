"""Tests for the Session-5 verification sheet tooling (Task 7).

The scorer produces the number that goes into the report, so its counting is pinned here:
which verdicts count as errors, that blanks are refused rather than silently shrinking the
denominator, and that a row whose query text contains an escaped pipe still parses.
"""
from __future__ import annotations

import pytest

from scripts.build_review_sheet import _pages_to_check
from scripts.score_review_sheet import ERROR_VERDICTS, parse, summarize, wilson

_SHEET = """\
# Gold v2 — human verification sheet

## How to check each row

| stratum | population | sampled |
|---|---|---|
| factual | 53 | 2 |

## factual (answerable)

*Is the answer on the listed page?*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| gold-001 | What is \\|x\\| for a vector? | 1 | 30 | OK | |
| gold-002 | Second one | 1 | 44 | WRONG | not on page |

## negatives (must be unanswerable)

*Is the book genuinely unable to answer this?*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| neg-out-001 | Who wrote Pride and Prejudice? | 0 | — | OK | |
| neg-in_-001 | Schrödinger equation for hydrogen? | 0 | — | ANSWERABLE | found on p. 900 |
"""


def test_parse_keeps_only_sample_sections():
    sections = parse(_SHEET)
    assert list(sections) == ["factual (answerable)", "negatives (must be unanswerable)"]
    assert sections["factual (answerable)"] == [("gold-001", "OK"), ("gold-002", "WRONG")]


def test_parse_survives_an_escaped_pipe_in_the_query():
    """A '|' inside a cell is escaped as '\\|'; the row must still split into 6 cells."""
    (qid, verdict), _ = parse(_SHEET)["factual (answerable)"]
    assert (qid, verdict) == ("gold-001", "OK")


def test_errors_are_wrong_missing_page_and_answerable():
    assert ERROR_VERDICTS == {"WRONG", "MISSING-PAGE", "ANSWERABLE"}
    result = summarize(parse(_SHEET))
    assert result["total"] == 4
    assert result["errors"] == 2                    # gold-002 WRONG + neg-in_-001 ANSWERABLE
    by_name = {s["stratum"]: s for s in result["per_stratum"]}
    assert by_name["factual (answerable)"]["errors"] == 1
    assert by_name["negatives (must be unanswerable)"]["errors"] == 1


def test_blank_rows_are_reported_not_silently_dropped():
    blank = _SHEET.replace("| 30 | OK |", "| 30 |  |")
    result = summarize(parse(blank))
    assert result["unfilled"] == ["gold-001"]
    assert result["total"] == 3                     # the blank row is excluded from scoring
    assert result["errors"] == 2


def test_unrecognised_verdict_is_flagged_and_excluded():
    odd = _SHEET.replace("| 30 | OK |", "| 30 | PROBABLY |")
    result = summarize(parse(odd))
    assert result["unknown"] == [("gold-001", "PROBABLY")]
    assert result["total"] == 3
    assert result["errors"] == 2


def test_verdict_is_case_insensitive():
    result = summarize(parse(_SHEET.replace("| 30 | OK |", "| 30 | ok |")))
    assert result["errors"] == 2
    assert result["unknown"] == []


# ── the interval ───────────────────────────────────────────────────────────

def test_wilson_zero_errors_still_has_a_finite_upper_bound():
    """The rule-of-three case: 0/30 must NOT be reported as 'the rate is 0'."""
    lo, hi = wilson(0, 30)
    assert lo == 0.0
    assert 0.10 < hi < 0.13          # ~11.4%


def test_wilson_matches_known_values():
    lo, hi = wilson(3, 30)           # 10% observed
    assert round(lo, 3) == 0.035
    assert round(hi, 3) == 0.256
    lo, hi = wilson(0, 6)            # per-stratum worst case
    assert round(hi, 2) == 0.39


def test_wilson_is_safe_at_the_edges():
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(5, 5)
    assert lo < 1.0 and hi == 1.0


# ── the builder's page selection ───────────────────────────────────────────

@pytest.mark.parametrize("pages,expected", [
    ([], []),
    ([30], [30]),
    ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]),                 # <=5: all of them
    ([10, 20, 30, 40, 50, 60], [10, 20, 30, 50, 60]),   # >5: first, last, evenly spaced
])
def test_pages_to_check(pages, expected):
    assert _pages_to_check(pages) == expected


def test_pages_to_check_caps_the_burden_on_huge_label_sets():
    """An overview query can carry 314 labelled pages — never list them all."""
    huge = list(range(1, 315))
    check = _pages_to_check(huge)
    assert len(check) <= 5
    assert check[0] == 1 and check[-1] == 314
    assert check == sorted(set(check))
