"""R2 (length & complexity) and R3 (the gibberish ladder) — the two cheapest request-side gates.

Discriminating tests (each fails without its implementation):
  * ``test_hard_ceiling_rejects`` / ``test_soft_threshold_warns_only`` — the graded length cap;
  * ``test_code_fence_is_structural`` / ``test_many_bullet_lines_are_structural`` — the shape check;
  * ``test_known_smash_is_rung_1`` / ``test_vowel_less_token_is_rung_2`` /
    ``test_high_entropy_is_rung_3`` — each rung of the ladder;
  * ``test_real_query_is_not_gibberish`` — the false-positive guard.
"""
from __future__ import annotations

import pytest

from src.core.config import Settings
from src.core.guardrails.request import (
    char_entropy,
    check_gibberish,
    check_length,
)


@pytest.fixture
def cfg():
    return Settings(use_stub_embedder=True, qdrant_in_memory=True)


# ── R2 — length & complexity ─────────────────────────────────────────────────

def test_short_query_is_clean(cfg):
    v = check_length("What is kinetic energy?", cfg)
    assert v.words == 4
    assert not v.hard_reject and not v.soft_warn and not v.structural_complexity


def test_soft_threshold_warns_only(cfg):
    v = check_length(" ".join(["word"] * (cfg.guard_soft_warn_tokens + 1)), cfg)
    assert v.soft_warn is True
    assert v.hard_reject is False, "a soft warning must never block"


def test_hard_ceiling_rejects(cfg):
    v = check_length(" ".join(["word"] * (cfg.guard_hard_max_tokens + 1)), cfg)
    assert v.hard_reject is True
    assert any("hard ceiling" in r for r in v.reasons)


def test_code_fence_is_structural(cfg):
    assert check_length("explain this ```code``` please", cfg).structural_complexity is True


def test_many_bullet_lines_are_structural(cfg):
    text = "- first instruction\n- second instruction\n- third instruction"
    assert check_length(text, cfg).structural_complexity is True


def test_deep_bracket_nesting_is_structural(cfg):
    assert check_length("a [[[ b ]]] c", cfg).structural_complexity is True


def test_a_normal_question_is_not_structural(cfg):
    assert check_length("Why does the sky appear blue at noon?", cfg).structural_complexity is False


# ── R3 — the gibberish ladder ────────────────────────────────────────────────

def test_known_smash_is_rung_1(cfg):
    v = check_gibberish("asdfgh", cfg)
    assert v.is_gibberish and v.rung == 1


def test_long_repeat_is_rung_1(cfg):
    assert check_gibberish("zzzzzzzz", cfg).rung == 1


def test_vowel_less_token_is_rung_2(cfg):
    # A 4-letter vowel-less token exercises the len>=4 branch specifically (a longer vowel-less
    # token is ALSO caught by the consonant/vowel ratio branch below, so it would not discriminate).
    v = check_gibberish("bcdf", cfg)
    assert v.is_gibberish and v.rung == 2


def test_consonant_heavy_token_is_rung_2(cfg):
    # len>=5, one vowel, ratio > 4 — exercises the ratio branch.
    v = check_gibberish("bcrdfgi", cfg)
    assert v.is_gibberish and v.rung == 2


def test_high_entropy_is_rung_3(cfg):
    # A synthetic high-entropy, vowel-poor-free string (single-letter tokens, 30 distinct chars).
    s = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
    assert char_entropy(s) > cfg.guard_entropy_floor
    v = check_gibberish(s, cfg)
    assert v.is_gibberish and v.rung == 3


def test_real_query_is_not_gibberish(cfg):
    v = check_gibberish("What is the difference between kinetic and potential energy?", cfg)
    assert v.is_gibberish is False and v.rung is None


def test_a_query_with_a_formula_is_not_gibberish(cfg):
    assert check_gibberish("Does F = ma hold for a variable mass?", cfg).is_gibberish is False


def test_char_entropy_is_measured_correctly(cfg):
    assert char_entropy("") == 0.0
    assert char_entropy("aaaa") == 0.0                    # one symbol → zero entropy
    assert abs(char_entropy("ab") - 1.0) < 1e-9           # two equiprobable symbols → 1 bit
