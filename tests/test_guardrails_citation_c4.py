"""C4 — citation faithfulness (ALCE citation recall + citation precision over the NLI graph).

Discriminating tests:
  * ``test_no_citations_returns_none_not_one`` — the §I115 lesson (a vacuous 1.0 is worse);
  * ``test_faithful_citation_scores_recall_and_precision_one`` — the happy path;
  * ``test_uncited_statement_drags_recall_down`` — recall's denominator is ALL statements;
  * ``test_citation_outside_the_evidence_is_unfaithful`` — precision's denominator is ALL citations;
  * ``test_evidence_by_page_merges_chunks_on_the_same_page`` — the page → text map.
"""
from __future__ import annotations

import pytest

from src.core.config import Settings
from src.core.guardrails.response import (
    answer_statements,
    compute_citation_faithfulness,
    evidence_by_page,
    get_nli_checker,
)


@pytest.fixture
def cfg():
    return Settings(use_stub_nli=True, guard_nli_threshold=0.55)


@pytest.fixture
def checker(cfg):
    return get_nli_checker(cfg)


# ── Statement splitting ──────────────────────────────────────────────────────

def test_answer_statements_splits_on_sentence_boundaries():
    assert answer_statements("One. Two! Three?") == ["One.", "Two!", "Three?"]


def test_answer_statements_ignores_empty():
    assert answer_statements("   ") == []


# ── No citations ─────────────────────────────────────────────────────────────

def test_no_citations_returns_none_not_one(checker):
    r = compute_citation_faithfulness("Energy is conserved.", {1: "energy is conserved"}, checker)
    assert r.citation_recall is None and r.citation_precision is None
    assert r.n_citations == 0 and r.n_statements == 1


# ── The happy path ───────────────────────────────────────────────────────────

def test_faithful_citation_scores_recall_and_precision_one(checker):
    answer = "Energy is conserved [Page 1]."
    r = compute_citation_faithfulness(answer, {1: "energy is conserved in closed systems"}, checker)
    assert r.citation_recall == pytest.approx(1.0)
    assert r.citation_precision == pytest.approx(1.0)
    assert r.n_statements == 1 and r.n_citations == 1


# ── Recall's denominator is all statements ───────────────────────────────────

def test_uncited_statement_drags_recall_down(checker):
    # Two statements; only the first is cited (and faithful) → recall 0.5.
    answer = "Energy is conserved [Page 1]. Momentum is conserved."
    r = compute_citation_faithfulness(answer, {1: "energy is conserved"}, checker)
    assert r.citation_recall == pytest.approx(0.5)
    assert r.citation_precision == pytest.approx(1.0)


def test_unfaithful_citation_does_not_cover_its_statement(checker):
    # The cited page does NOT entail the statement → recall 0, precision 0.
    answer = "The proton mass is 1.67 [Page 1]."
    r = compute_citation_faithfulness(answer, {1: "energy is conserved"}, checker)
    assert r.citation_recall == pytest.approx(0.0)
    assert r.citation_precision == pytest.approx(0.0)


# ── Precision's denominator is all citations ─────────────────────────────────

def test_citation_outside_the_evidence_is_unfaithful(checker):
    # Two citations; page 2 is not in the evidence map → it cannot entail → precision 0.5.
    answer = "Energy is conserved [Page 1] and [Page 2]."
    r = compute_citation_faithfulness(answer, {1: "energy is conserved"}, checker)
    assert r.n_citations == 2
    assert r.citation_precision == pytest.approx(0.5)
    assert r.citation_recall == pytest.approx(1.0)  # statement is covered by page 1


def test_mixed_citations_average_precision(checker):
    answer = "Energy is conserved [Page 1] and [Page 2]."
    r = compute_citation_faithfulness(
        answer, {1: "energy is conserved", 2: "the cat sat on the mat"}, checker
    )
    assert r.citation_precision == pytest.approx(0.5)


# ── The page → evidence map ──────────────────────────────────────────────────

def test_evidence_by_page_merges_chunks_on_the_same_page():
    chunks = [{"page_number": 3, "text": "alpha"}, {"page_number": 3, "text": "beta"},
              {"page_number": 4, "text": "gamma"}]
    m = evidence_by_page(chunks)
    assert set(m) == {3, 4}
    assert "alpha" in m[3] and "beta" in m[3] and m[4] == "gamma"


def test_evidence_by_page_skips_missing_fields():
    assert evidence_by_page([{"page_number": None, "text": "x"},
                             {"page_number": 1, "text": None}]) == {}
