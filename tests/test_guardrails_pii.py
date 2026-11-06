"""R7 — PII detect-and-redact. Ports the lab's patterns and adds the structured-secret layer.

Discriminating tests (each fails without its implementation):
  * ``test_luhn_valid_card_is_redacted`` vs ``test_non_luhn_digit_run_is_kept`` — the Luhn
    discriminator the lesson plan names (a bare 13–16 digit run is NOT enough);
  * ``test_aws_key_and_github_token_are_redacted`` — the structured secrets;
  * ``test_overlapping_spans_merge`` — the lab's merge behaviour;
  * ``test_clean_query_is_untouched`` — the false-positive guard.
"""
from __future__ import annotations

from src.core.guardrails.pii import PIIGuardrail, _luhn_ok, _merge_spans


def _guard() -> PIIGuardrail:
    return PIIGuardrail()  # spaCy absent → regex-only (the lab's fallback)


def test_email_is_redacted():
    assert "[REDACTED_EMAIL]" in _guard().apply("contact me at jane.doe@example.com please")


def test_ssn_is_redacted():
    assert "[REDACTED_SSN]" in _guard().apply("my number is 123-45-6789")


def test_aws_key_is_redacted():
    assert "[REDACTED_AWS_KEY]" in _guard().apply("key AKIAIOSFODNN7EXAMPLE here")


def test_github_token_is_redacted():
    out = _guard().apply("token ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    assert "[REDACTED_GITHUB_TOKEN]" in out


def test_luhn_valid_card_is_redacted():
    assert "[REDACTED_CARD]" in _guard().apply("card 4111111111111111 exp 12/26")


def test_non_luhn_digit_run_is_kept():
    """A 16-digit run that fails Luhn is NOT a card — the discriminator the course names."""
    assert _luhn_ok("4111111111111111") is True
    assert _luhn_ok("4111111111111112") is False
    out = _guard().apply("reference 4111111111111112")
    assert "[REDACTED_CARD]" not in out


def test_overlapping_spans_merge():
    # Two overlapping spans with different labels collapse to the generic PII token.
    merged = _merge_spans([(0, 5, "[REDACTED_EMAIL]"), (3, 8, "[REDACTED_PHONE]")])
    assert merged == [(0, 8, "[REDACTED_PII]")]
    # Disjoint spans are kept separate.
    assert _merge_spans([(0, 3, "A"), (5, 8, "B")]) == [(0, 3, "A"), (5, 8, "B")]


def test_detect_returns_typed_hits():
    hits = _guard().detect("mail a@b.com or call 555-123-4567")
    types = {h.pii_type for h in hits}
    assert "email" in types and "phone" in types


def test_clean_physics_query_is_untouched():
    q = "What is the difference between kinetic and potential energy?"
    assert _guard().apply(q) == q
    assert _guard().detect(q) == []
