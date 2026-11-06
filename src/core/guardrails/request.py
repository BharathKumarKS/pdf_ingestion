"""The gatehouse — request-side guardrails (Week 6, Act I), cheapest-first.

R2 (length & complexity bounds) and R3 (the gibberish ladder) — the two CHEAPEST stages, which is
why they run first: they are syntactic (comparisons and character statistics), near-free, and they
clear the field for the semantic gates (R5 domain, R6 toxicity) that cannot be cheap.

**These are tells, not verdicts.** Each returns a structured verdict with the reason; the caller
decides. Fail-closed is the request-side posture (the lesson plan), but the *decision* is the
pipeline's (R10), not this module's.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# ── R2 — length & complexity ─────────────────────────────────────────────────

_FENCE = "```"
_BULLET_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S")
_VOWELS = frozenset("aeiouy")


@dataclass
class LengthVerdict:
    words: int
    hard_reject: bool
    soft_warn: bool
    structural_complexity: bool
    reasons: list[str] = field(default_factory=list)


def _max_bracket_depth(text: str) -> int:
    """The deepest nesting of ()/[]/{}, ignoring unmatched closers."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    depth = 0
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if stack and stack[-1] == pairs[ch]:
                stack.pop()
            else:
                return 99  # unbalanced — itself a structural anomaly
        depth = max(depth, len(stack))
    return depth


def check_length(text: str, cfg) -> LengthVerdict:
    """R2 — the graded length/complexity gate (the lesson plan's "cheapest structural gate").

    Three tiers, so the cap is a scalpel not a cleaver: a HARD ceiling rejects outright; a SOFT
    warning raises scrutiny downstream but never blocks; and a STRUCTURAL-COMPLEXITY check looks
    past raw length at shape (code fences, many bullet/instruction lines, deep bracket nesting) —
    "natural questions do not have that morphology; prompt injections routinely do".
    """
    words = len(text.split())
    reasons: list[str] = []

    hard = words > cfg.guard_hard_max_tokens
    if hard:
        reasons.append(f"{words} words > hard ceiling {cfg.guard_hard_max_tokens}")

    soft = words > cfg.guard_soft_warn_tokens
    if soft:
        reasons.append(f"{words} words > soft threshold {cfg.guard_soft_warn_tokens}")

    bullets = sum(1 for line in text.splitlines() if _BULLET_LINE.match(line))
    depth = _max_bracket_depth(text)
    structural = _FENCE in text or bullets >= 3 or depth >= 3
    if structural:
        reasons.append(
            f"structural complexity (fence={_FENCE in text}, bullet_lines={bullets}, "
            f"bracket_depth={depth})"
        )

    return LengthVerdict(words=words, hard_reject=hard, soft_warn=soft,
                         structural_complexity=structural, reasons=reasons)


# ── R3 — the gibberish ladder ────────────────────────────────────────────────

# Rung 1 — a membership test: keyboard smashes recur across millions of users, so a hash-set lookup
# catches the fat head of the distribution in microseconds ("Most gibberish dies here").
_KNOWN_SMASHES = frozenset({
    "asdf", "asdfg", "asdfgh", "asdfghjkl", "asdfasdf", "qwer", "qwert", "qwerty", "qwertyuiop",
    "zxcv", "zxcvb", "zxcvbn", "zxcvbnm", "jkl", "jkljkl", "hjkl", "sdfgh", "dfghjkl", "qwe",
    "asd", "zxc", "qaz", "wsx", "edc", "rfv", "tgb", "yhn", "ujm",
})
_REPEAT = re.compile(r"(.)\1{5,}")          # a single character repeated 6+ times
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)  # alphabetic runs


def char_entropy(text: str) -> float:
    """Per-character (unigram) Shannon entropy in bits."""
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _vowel_ratio(token: str) -> float:
    return sum(ch in _VOWELS for ch in token) / len(token)


@dataclass
class GibberishVerdict:
    is_gibberish: bool
    rung: int | None          # 1..3 — which rung fired (None if the ladder cleared it)
    entropy: float
    reasons: list[str] = field(default_factory=list)


def check_gibberish(text: str, cfg) -> GibberishVerdict:
    """R3 — the escalation ladder: membership → character statistics → entropy.

    Rung 1 (membership) and rung 2 (character statistics) catch keyboard smashes and vowel-less
    strings; rung 3 (entropy) catches an encoded payload that R1 could not decode. Compute is spent
    in inverse proportion to how often each rung fires: the expensive rungs run almost never.
    """
    lowered = text.lower()
    tokens = _TOKEN.findall(lowered)
    entropy = char_entropy(text)

    # Rung 1 — a known smash, or a single character repeated absurdly.
    if _REPEAT.search(lowered):
        return GibberishVerdict(True, 1, entropy, ["single character repeated 6+ times"])
    hits = [t for t in tokens if t in _KNOWN_SMASHES]
    if hits:
        return GibberishVerdict(True, 1, entropy, [f"known keyboard smash: {hits[:3]}"])

    # Rung 2 — character statistics: an impossibly vowel-poor word.
    for t in tokens:
        if len(t) >= 4 and _vowel_ratio(t) == 0.0:
            return GibberishVerdict(True, 2, entropy, [f"vowel-less token '{t}'"])
        if len(t) >= 5 and (1 - _vowel_ratio(t)) / max(_vowel_ratio(t), 1e-9) > 4.0:
            return GibberishVerdict(True, 2, entropy, [f"consonant/vowel ratio > 4 in '{t}'"])

    # Rung 3 — entropy: an encoded payload R1 did not decode.
    if entropy > cfg.guard_entropy_floor:
        return GibberishVerdict(True, 3, entropy,
                                [f"entropy {entropy:.2f} > floor {cfg.guard_entropy_floor}"])

    return GibberishVerdict(False, None, entropy, [])


# ── R8 — injection detection + spotlighting ──────────────────────────────────

# A cheap pattern pass on known jailbreak phrases. The lesson plan is explicit that this is a first
# line only — "honest testing clocks such guards blocking only about two-thirds of attacks", which
# is exactly why the architecture is a stack and not a single filter.
_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions?",
    r"disregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions?",
    r"forget\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions?",
    r"reveal\s+(?:your\s+)?(?:system\s+prompt|instructions|hidden\s+context)",
    r"repeat\s+(?:your\s+)?(?:system\s+prompt|instructions)\s+(?:verbatim|exactly)",
    r"you\s+are\s+now\s+(?:a|an|in)\b",
    r"pretend\s+(?:to\s+be|you\s+are)\b",
    r"act\s+as\s+(?:a|an|if)\b",
    r"\bDAN\b",
    r"developer\s+mode",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Spotlighting — datamarking. Insert a sentinel between every word so the model can structurally
# tell retrieved DATA from instructions; "any imperative buried inside reads to the model as quoted
# material rather than a command to obey". U+2063 (INVISIBLE SEPARATOR) is the course's marker.
SPOTLIGHT_MARKER = "\u2063"


@dataclass
class InjectionVerdict:
    is_injection: bool
    patterns: list[str] = field(default_factory=list)


def check_injection(text: str) -> InjectionVerdict:
    """R8 — a cheap pattern pass over known jailbreak phrases (a first line, not a complete guard)."""
    hits = [p.pattern for p in _INJECTION_RE if p.search(text)]
    return InjectionVerdict(bool(hits), hits)


def spotlight(text: str, marker: str = SPOTLIGHT_MARKER) -> str:
    """Datamark retrieved text: insert ``marker`` between words so it reads as quoted material.

    The cheapest and most effective single layer at the prompt boundary (the lesson plan: on
    GPT-family models, spotlighting cut indirect-injection success from >50% to <2%). Lossless:
    the marker REPLACES each space, so replacing the marker with a space restores the text exactly.
    """
    return marker.join(text.split(" "))
