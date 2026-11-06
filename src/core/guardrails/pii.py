"""R7 — PII detect-and-redact at the request boundary (Week 6, Act I Family C).

Ported from the lab `Labs/Week_6/response_grounding/src/response_grounding/pii_guardrail.py`
(regex patterns + optional spaCy NER, overlapping spans merged), and extended with the lesson
plan's structured-secret recognizers: a **Luhn-valid** card check, **AKIA** AWS keys and **ghp_**
GitHub tokens.

**Why at the boundary.** "The blast radius grows at every hop": an errant paste becomes the
pipeline's compliance incident the instant it is logged, embedded, and forwarded. Redact the span,
replace it with a typed placeholder, and log the TYPE — never the value.

⚠️ spaCy is optional: without it the guardrail is regex-only (the lab's own fallback), which is
exactly this repo's stub convention.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

_DEFAULT_SPACY_MODEL = "en_core_web_sm"

# The lab's four patterns, plus the lesson plan's structured secrets.
_REGEX_PATTERNS: list[tuple[str, str, str]] = [
    ("email",        r"\b[\w\.-]+@[\w\.-]+\.\w+\b",                              "[REDACTED_EMAIL]"),
    ("phone",        r"\b(?:\+?\d{1,2}\s*)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b", "[REDACTED_PHONE]"),
    ("ssn",          r"\b\d{3}-\d{2}-\d{4}\b",                                   "[REDACTED_SSN]"),
    ("aws_key",      r"\bAKIA[0-9A-Z]{16}\b",                                    "[REDACTED_AWS_KEY]"),
    ("github_token", r"\bghp_[A-Za-z0-9]{20,}\b",                                "[REDACTED_GITHUB_TOKEN]"),
]

# Card numbers are handled separately: a 13–16 digit run that must ALSO pass Luhn.
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

# spaCy NER labels treated as person / location-like PII (the lab's sets).
_NER_LABELS_NAME = frozenset({"PERSON"})
_NER_LABELS_ADDRESS = frozenset({"GPE", "LOC", "FAC"})


@dataclass
class PIIHit:
    """A detected PII span. ``value`` is NEVER logged by callers — only ``pii_type`` is."""
    pii_type: str
    start: int
    end: int
    value: str


def _luhn_ok(digits: str) -> bool:
    """The Luhn checksum — the lesson plan's "Luhn-valid card numbers" discriminator."""
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(nums)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _merge_spans(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Merge overlapping intervals; mixed replacement labels become a generic PII token.

    Byte-for-byte the lab's `_merge_spans`.
    """
    if not spans:
        return []
    spans_sorted = sorted(spans, key=lambda x: (x[0], x[1]))
    merged: list[tuple[int, int, str]] = []
    cur_s, cur_e, cur_r = spans_sorted[0]
    for start, end, repl in spans_sorted[1:]:
        if start < cur_e:
            cur_e = max(cur_e, end)
            cur_r = cur_r if cur_r == repl else "[REDACTED_PII]"
        else:
            merged.append((cur_s, cur_e, cur_r))
            cur_s, cur_e, cur_r = start, end, repl
    merged.append((cur_s, cur_e, cur_r))
    return merged


class PIIGuardrail:
    """Detects and redacts common PII from text using regex and optional spaCy NER."""

    def __init__(self, spacy_model: str | None = None) -> None:
        model = spacy_model or os.getenv("PII_SPACY_MODEL", _DEFAULT_SPACY_MODEL)
        self._nlp: Any | None = None
        try:
            import spacy
            self._nlp = spacy.load(model)
        except Exception:  # noqa: BLE001 — absent spaCy → regex-only (the lab's fallback)
            self._nlp = None

    def detect(self, text: str) -> list[PIIHit]:
        """All PII spans found, typed — for logging the TYPE, never the value."""
        hits: list[PIIHit] = []
        for pii_type, pattern, _ in _REGEX_PATTERNS:
            for m in re.finditer(pattern, text):
                hits.append(PIIHit(pii_type, m.start(), m.end(), m.group(0)))
        for m in _CARD_CANDIDATE.finditer(text):
            if _luhn_ok(m.group(0)):
                hits.append(PIIHit("card", m.start(), m.end(), m.group(0)))
        if self._nlp is not None:
            for ent in self._nlp(text).ents:
                if ent.label_ in _NER_LABELS_NAME:
                    hits.append(PIIHit("name", ent.start_char, ent.end_char, ent.text))
                elif ent.label_ in _NER_LABELS_ADDRESS:
                    hits.append(PIIHit("address", ent.start_char, ent.end_char, ent.text))
        return hits

    def apply(self, text: str) -> str:
        """Replace detected PII substrings with fixed typed redaction tokens (the lab's shape)."""
        spans: list[tuple[int, int, str]] = []
        for pii_type, pattern, replacement in _REGEX_PATTERNS:
            for m in re.finditer(pattern, text):
                spans.append((m.start(), m.end(), replacement))
        for m in _CARD_CANDIDATE.finditer(text):
            if _luhn_ok(m.group(0)):
                spans.append((m.start(), m.end(), "[REDACTED_CARD]"))
        if self._nlp is not None:
            for ent in self._nlp(text).ents:
                if ent.label_ in _NER_LABELS_NAME:
                    spans.append((ent.start_char, ent.end_char, "[REDACTED_NAME]"))
                elif ent.label_ in _NER_LABELS_ADDRESS:
                    spans.append((ent.start_char, ent.end_char, "[REDACTED_ADDRESS]"))

        merged = _merge_spans(spans)
        out = text
        for start, end, replacement in sorted(merged, key=lambda x: x[0], reverse=True):
            out = out[:start] + replacement + out[end:]
        return out
