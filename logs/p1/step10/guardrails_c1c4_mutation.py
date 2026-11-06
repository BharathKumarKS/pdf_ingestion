#!/usr/bin/env python3
"""C1/C4 mutation proof — every ported stage is guarded by a test that reddens when broken.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_c1c4_mutation.py

Each mutation edits the LIVE source, runs exactly its intended test, and is restored byte-identical
afterwards. PASS requires every mutation to redden its intended check and no mutation to be inert.
⚠️ Coverage is per-MUTATION, not per-TEST (the repo's C2 precedent): 13 mutations guard the 32
assertions' load-bearing behaviours; the wiring/empty-input/parse-variant tests are not each
individually mutated.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/core/guardrails/response.py"
PY = str(ROOT / ".venv/bin/python")
C1 = "tests/test_guardrails_response_c1.py"
C4 = "tests/test_guardrails_citation_c4.py"

MUTATIONS = [
    ("M1 matrix builder swaps the claim/document index",
     '                    "claim_index": claim_index,\n                    "document_index": document_index,',
     '                    "claim_index": document_index,\n                    "document_index": document_index,',
     f"{C1}::test_matrix_is_the_cartesian_product"),
    ("M2 similarity filter keeps everything (threshold ignored)",
     "            if score > self.similarity_threshold:",
     "            if score >= 0.0:",
     f"{C1}::test_similarity_filter_is_strictly_above_the_threshold"),
    ("M3 entailment head resolution is hard-coded to the wrong column",
     '        if str(label).lower() == "entailment":\n            return idx',
     '        if str(label).lower() == "entailment":\n            return 2',
     f"{C1}::test_entailment_index_resolves_to_the_entailment_head"),
    ("M4 NLI reads column 0 instead of the entailment column",
     "            probabilities = probs[:, self._entailment_idx].astype(float)",
     "            probabilities = probs[:, 0].astype(float)",
     f"{C1}::test_nli_marks_entailing_at_the_threshold"),
    ("M5 groundedness score is always 1.0",
     "            \"groundedness_score\": grounded_count / len(claims),",
     "            \"groundedness_score\": 1.0,",
     f"{C1}::test_groundedness_is_the_fraction_of_grounded_claims"),
    ("M6 nothing is ever flagged isolated",
     "            is_isolated = not is_grounded",
     "            is_isolated = False",
     f"{C1}::test_isolated_claim_is_an_ungrounded_left_node"),
    ("M7 the claim cap is removed",
     "    claims = [c for c in claims if c.strip()][: cfg.guard_max_claims]",
     "    claims = [c for c in claims if c.strip()][: 999]",
     f"{C1}::test_groundedness_caps_claims_and_evidence"),
    ("M8 the sentence-split fallback loses its punctuation split",
     r'        raw_claims = re.split(r"[.!?]\s+|\n+", response_text.strip())',
     r'        raw_claims = re.split(r"\n+", response_text.strip())',
     f"{C1}::test_claim_extractor_falls_back_to_sentence_split"),
    ("M9 the extractor does not unwrap the {'claims': [...]} object",
     '            parsed = parsed.get("claims")',
     "            parsed = parsed",
     f"{C1}::test_parse_claim_json_unwraps_the_object_when_the_array_slice_is_invalid"),
    ("M10 citation recall uses the covered count as its own denominator",
     "    recall = len(covered) / len(statements) if statements else None",
     "    recall = len(covered) / max(len(covered), 1) if statements else None",
     f"{C4}::test_uncited_statement_drags_recall_down"),
    ("M11 citation precision uses the entailing count as its own denominator",
     "    precision = len(entailing) / len(pairs)",
     "    precision = len(entailing) / max(len(entailing), 1)",
     f"{C4}::test_citation_outside_the_evidence_is_unfaithful"),
    ("M12 the page map overwrites instead of merging same-page chunks",
     '        pages.setdefault(int(page), []).append(str(text))',
     "        pages[int(page)] = [str(text)]",
     f"{C4}::test_evidence_by_page_merges_chunks_on_the_same_page"),
    ("M13 an uncited answer returns a vacuous 1.0 instead of None",
     "        return CitationFaithfulness(None, None, len(statements), 0)",
     "        return CitationFaithfulness(1.0, 1.0, len(statements), 0)",
     f"{C4}::test_no_citations_returns_none_not_one"),
]


def _run(test: str) -> int:
    return subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True).returncode


def main() -> int:
    original = SRC.read_text()
    reddened, inert = [], []
    try:
        for name, old, new, test in MUTATIONS:
            assert original.count(old) == 1, f"{name}: anchor not unique ({original.count(old)})"
            SRC.write_text(original.replace(old, new))
            rc = _run(test)
            (reddened if rc != 0 else inert).append(name)
            print(f"  {'REDDENED' if rc != 0 else 'INERT   '}  {name}  → {test.split('::')[-1]}")
    finally:
        SRC.write_text(original)

    assert SRC.read_text() == original, "source not restored byte-identical"
    print(f"\n{len(reddened)}/{len(MUTATIONS)} mutations reddened their intended check; "
          f"inert: {inert or 'none'}")
    if inert:
        print("RESULT: FAIL — an inert check guards nothing")
        return 1
    print("RESULT: PASS — every mutation reddens its intended check, no inert mutation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
