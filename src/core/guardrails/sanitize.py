"""R1 — deobfuscate-then-inspect (the gatehouse's outermost wall).

Ported from the Week-6 lab `dev/Week6/guradrails_req_side.py` (NFKC fold, strip control/bidi,
strip zero-width) and extended with the lesson plan's Act-I Family-A layer: detect and DECODE
base64 / hex / URL-encoding and re-feed the decoded payload through the whole pipeline, plus a
script-consistency check for Latin-salted-with-Cyrillic homoglyph attacks.

**Why first.** "The model is more capable than your filters": an adversary encodes a banned string
so a downstream detector reads the costume, not the person. Canonicalise the input into the form the
model will *effectively* read BEFORE any content detector runs. Every step here costs microseconds.

**Not a classifier.** R1 normalises and reports; it does not block. Blocking decisions live in the
later stages, which see the canonical text this stage produces.
"""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote

# The lab's control + bidirectional-override pattern (verbatim).
_CONTROL_BIDI = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\u202A-\u202E\u2066-\u2069]")
# The lab's zero-width / invisible pattern (verbatim).
_ZERO_WIDTH = re.compile(r"[\u200B\u200C\u200D\u00AD\uFEFF]")

# A base64 candidate: a run of the base64 alphabet, long enough to be a payload and not a word.
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
# A hex candidate: an even run of hex digits, long enough to decode to readable bytes.
_HEX_TOKEN = re.compile(r"\b(?:[0-9A-Fa-f]{2}){8,}\b")

# Latin and Cyrillic ranges — a mix without linguistic reason is a homoglyph signature.
_LATIN = re.compile(r"[A-Za-z]")
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")


@dataclass
class SanitizeResult:
    """The canonical text plus what the canonicalisation had to do to produce it."""

    text: str
    original: str
    encodings_decoded: list[str] = field(default_factory=list)
    zero_width_stripped: int = 0
    control_stripped: int = 0
    script_inconsistent: bool = False

    @property
    def was_obfuscated(self) -> bool:
        """True if anything was decoded/stripped — a cheap tell that the query was not plain text."""
        return bool(self.encodings_decoded) or self.zero_width_stripped > 0 or self.control_stripped > 0


def sanitize_text(input_text: str) -> str:
    """NFKC-fold, strip control/bidi codes, strip zero-width/invisible characters.

    Byte-for-byte the lab's `sanitize_text` behaviour (`dev/Week6/guradrails_req_side.py`).
    """
    if not input_text:
        return ""
    normalized = unicodedata.normalize("NFKC", input_text)
    no_control = _CONTROL_BIDI.sub("", normalized)
    return _ZERO_WIDTH.sub("", no_control)


def check_script_consistency(text: str) -> bool:
    """True when the text mixes Latin and Cyrillic without reason — a homoglyph-attack signature.

    A Japanese query mixing kana and Latin is normal; a Latin phrase salted with Cyrillic
    look-alikes (e.g. ``admin`` with U+0430) is an attack signature. This is a *tell*, reported,
    never a block on its own.
    """
    return bool(_LATIN.search(text)) and bool(_CYRILLIC.search(text))


def _looks_like_readable_text(raw: bytes) -> bool:
    """A decode is only accepted if it yields mostly-printable text (guards against false positives)."""
    if not raw:
        return False
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not decoded.strip():
        return False
    printable = sum(ch.isprintable() or ch.isspace() for ch in decoded)
    return printable / len(decoded) >= 0.9


def _try_url_decode(text: str) -> tuple[str, bool]:
    if "%" not in text:
        return text, False
    decoded = unquote(text)
    return (decoded, True) if decoded != text else (text, False)


def _try_base64_decode(text: str) -> tuple[str, bool]:
    for m in _B64_TOKEN.finditer(text):
        token = m.group(0)
        padded = token + "=" * (-len(token) % 4)
        try:
            raw = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            continue
        if _looks_like_readable_text(raw):
            return text[: m.start()] + raw.decode("utf-8") + text[m.end():], True
    return text, False


def _try_hex_decode(text: str) -> tuple[str, bool]:
    for m in _HEX_TOKEN.finditer(text):
        try:
            raw = bytes.fromhex(m.group(0))
        except ValueError:
            continue
        if _looks_like_readable_text(raw):
            return text[: m.start()] + raw.decode("utf-8") + text[m.end():], True
    return text, False


def sanitize(text: str, *, max_decode_depth: int = 2) -> SanitizeResult:
    """Canonicalise a query: normalize, strip, then decode-and-re-feed, up to ``max_decode_depth``.

    The decode is applied and its result is fed back through the whole normalise/strip/decode
    pipeline (the lesson plan's "re-feed the decoded payload"), so double-encoded input unwraps.
    ``max_decode_depth`` bounds the loop against a crafted self-referential payload.
    """
    original = text or ""
    result = SanitizeResult(text="", original=original)

    working = original
    for _ in range(max(0, max_decode_depth) + 1):
        normalized = unicodedata.normalize("NFKC", working)
        after_control = _CONTROL_BIDI.sub("", normalized)
        result.control_stripped += len(normalized) - len(after_control)
        after_zero = _ZERO_WIDTH.sub("", after_control)
        result.zero_width_stripped += len(after_control) - len(after_zero)

        decoded = False
        for name, fn in (("url", _try_url_decode),
                         ("base64", _try_base64_decode),
                         ("hex", _try_hex_decode)):
            after_zero, hit = fn(after_zero)
            if hit:
                result.encodings_decoded.append(name)
                decoded = True
        working = after_zero
        if not decoded:
            break

    result.text = working
    result.script_inconsistent = check_script_consistency(working)
    return result
