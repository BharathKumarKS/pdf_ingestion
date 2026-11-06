"""C2 — the response-side tier-1 cheap heuristics (citation validity + numbers-in-evidence).

Discriminating tests:
  * ``test_cited_pages_reads_every_emitted_format`` — the §I115 fix (CJK bracket + U+202F);
  * ``test_citation_to_an_unretrieved_page_is_invalid`` — the "footnote that does not hold";
  * ``test_number_absent_from_evidence_is_unsupported`` — the fabrication disprover;
  * ``test_number_match_is_boundary_aware`` — '42' is not "found" inside '1042'.
"""
from __future__ import annotations

from src.core.guardrails.response import (
    check_citation_validity,
    check_numbers_in_evidence,
    cited_pages,
)


# ── Citation validity ────────────────────────────────────────────────────────

def test_cited_pages_reads_every_emitted_format():
    answer = "Energy is conserved [Page 5]. Momentum too 【Page 7】. And (page 9)."
    assert cited_pages(answer) == {5, 7, 9}


def test_cited_pages_handles_a_narrow_no_break_space():
    # U+202F between 'Page' and the number — the format that made the old metric vacuous (§I115).
    assert cited_pages("See [Page\u202f141].") == {141}


def test_all_cited_pages_retrieved_is_valid():
    v = check_citation_validity("see [Page 5] and [Page 6]", [5, 6, 7])
    assert v.all_valid is True and v.invalid == set()


def test_citation_to_an_unretrieved_page_is_invalid():
    v = check_citation_validity("see [Page 5] and [Page 9]", [5, 6, 7])
    assert v.all_valid is False
    assert v.invalid == {9}
    assert v.valid == {5}


def test_no_citations_is_vacuously_valid():
    assert check_citation_validity("no citation here", [1, 2]).all_valid is True


# ── Numbers in evidence ──────────────────────────────────────────────────────

def test_number_present_in_evidence_is_supported():
    c = check_numbers_in_evidence("The speed is 3.0 metres per second.", ["light travels at 3.0 m/s"])
    assert c.all_supported is True and c.numbers == ["3.0"]


def test_number_absent_from_evidence_is_unsupported():
    c = check_numbers_in_evidence("The mass of the proton is 1.67e-27 kg.", ["the electron mass is 9.1 kg"])
    assert c.unsupported, "a number in no passage is a fabrication"
    assert "1.67" in c.unsupported


def test_number_match_is_boundary_aware():
    # '42' must NOT be considered present because '1042' contains those digits.
    c = check_numbers_in_evidence("the answer is 42", ["the year 1042 was uneventful"])
    assert "42" in c.unsupported


def test_thousands_separators_are_normalised():
    c = check_numbers_in_evidence("about 1,000 joules", ["it is roughly 1000 J"])
    assert c.all_supported is True


def test_no_numbers_is_vacuously_supported():
    assert check_numbers_in_evidence("energy is conserved", ["conservation of energy"]).all_supported is True
