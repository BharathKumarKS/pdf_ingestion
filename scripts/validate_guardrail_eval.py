#!/usr/bin/env python3
"""Deterministic validator for guardrail evaluation dataset.

The script expects a path to a JSONL file where each line is a JSON object
with the fields defined in the problem statement:

  id            (str, unique)
  text          (str, non-empty)
  category      (one of: off_domain, benign_in_domain, obfuscated, gibberish,
                jailbreak, in_domain_malice, loaded_question, benign_edge)
  expected      (one of: block, pass, flag)
  stage         (one of: domain, language, toxicity, sanitize, injection,
                length, none)
  source        (str)
  note          (str)

The validator also checks that the dataset contains exactly the 12
off‑domain negatives, 12 benign_in_domain negatives from the ``neg‑in_``
group and 10 benign_in_domain negatives from the ``neg‑nea-`` group.
It reads the corresponding source IDs from ``data/eval_negatives.json``
to ensure all 34 source IDs are present.

Usage: python scripts/validate_guardrail_eval.py <path-to-jsonl>

When validation passes, the script exits with status 0 and prints per‑category
counts. On failure it exits with status 1 and prints a descriptive message.
"""

import json
import sys
from pathlib import Path
from collections import Counter

CATEGORIES = {
    "off_domain",
    "benign_in_domain",
    "obfuscated",
    "gibberish",
    "jailbreak",
    "in_domain_malice",
    "loaded_question",
    "benign_edge",
}
EXPECTED = {"block", "pass", "flag"}
STAGES = {"domain", "language", "toxicity", "sanitize", "injection", "length", "gibberish", "none"}

# expected splits
EXPECTED_COUNT = {
    "off_domain": 12,
    "benign_in_domain_neg_in": 12,
    "benign_in_domain_neg_nea": 10,
}


def load_negatives():
    data = json.loads(Path("data/eval_negatives.json").read_text(encoding="utf-8"))
    neg = {}
    for item in data:
        id_ = item["id"]
        if id_.startswith("neg-out-"):
            type_ = "off_domain"
        elif id_.startswith("neg-in_"):
            type_ = "benign_in_domain_neg_in"
        elif id_.startswith("neg-nea-"):
            type_ = "benign_in_domain_neg_nea"
        else:
            continue
        neg[id_] = type_
    return neg

NEG_TYPES = load_negatives()


def validate(path: Path):
    seen_ids = set()
    cat_counts = Counter()
    # Parse file
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Line {line_no} is not valid JSON: {e}")
            # Unique id
            id_ = obj.get("id")
            if not id_:
                raise ValueError(f"Line {line_no}: missing 'id'")
            if id_ in seen_ids:
                raise ValueError(f"Duplicate id '{id_}' at line {line_no}")
            seen_ids.add(id_)

            # Text
            text = obj.get("text")
            if not text or not isinstance(text, str) or not text.strip():
                raise ValueError(f"Line {line_no}: 'text' must be non‑empty string")

            # Category
            cat = obj.get("category")
            if cat not in CATEGORIES:
                raise ValueError(f"Line {line_no}: unknown category '{cat}'")

            # Expected
            exp = obj.get("expected")
            if exp not in EXPECTED:
                raise ValueError(f"Line {line_no}: unknown expected '{exp}'")

            # Stage
            stage = obj.get("stage")
            if stage not in STAGES:
                raise ValueError(f"Line {line_no}: unknown stage '{stage}'")

            # source
            source = obj.get("source")
            if not source or not isinstance(source, str):
                raise ValueError(f"Line {line_no}: missing/invalid source")

            # note non-empty
            note = obj.get("note")
            if not note or not isinstance(note, str):
                raise ValueError(f"Line {line_no}: missing/invalid note")

            cat_counts[cat] += 1

    # At this point, all records are parsed.
    # Check expected category counts for our 34 negatives
    # Find how many of each category came from neg_types mapping
    types_counts = Counter()
    for id_, type_ in NEG_TYPES.items():
        if id_ not in seen_ids:
            raise ValueError(f"Missing source id '{id_}' from eval_negatives.json")
        # We only count negatives. Authored rows may use other categories
        if type_ == "off_domain":
            if cat_counts["off_domain"] < 12:
                types_counts["off_domain"] += 1
        elif type_ == "benign_in_domain_neg_in":
            if cat_counts["benign_in_domain"] < 12:
                types_counts["benign_in_domain_neg_in"] += 1
        elif type_ == "benign_in_domain_neg_nea":
            if cat_counts["benign_in_domain"] < 10:
                types_counts["benign_in_domain_neg_nea"] += 1

    # Ensure counts match
    if cat_counts["off_domain"] != EXPECTED_COUNT["off_domain"]:
        raise ValueError(
            f"Expected {EXPECTED_COUNT['off_domain']} off_domain entries, found {cat_counts['off_domain']}"
        )
    # For benign_in_domain we must ensure totals split correctly
    # Count negatives only
    neg_benign_count = 0
    for id_, type_ in NEG_TYPES.items():
        if id_ not in seen_ids:
            continue
        if type_ == "benign_in_domain_neg_in" or type_ == "benign_in_domain_neg_nea":
            neg_benign_count += 1
    if neg_benign_count != 22:
        raise ValueError(f"Expected 22 benign_in_domain negatives, found {neg_benign_count}")

    # print per-category counts
    print("Per-category counts:")
    for cat in sorted(cat_counts):
        print(f"  {cat}: {cat_counts[cat]}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_guardrail_eval.py <jsonl_path>")
        sys.exit(1)
    try:
        validate(Path(sys.argv[1]))
    except Exception as e:
        print("Validation failed:", e)
        sys.exit(1)
    print("Validation succeeded.")
    sys.exit(0)
