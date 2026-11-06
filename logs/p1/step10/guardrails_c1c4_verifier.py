#!/usr/bin/env python3
"""C1/C4 independent stdlib verifier — re-derives every cell from the raw numbers.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/guardrails_c1c4_verifier.py

Two halves, both independent of the port's own control flow:

PART 1 (V1–V8) re-reads ``logs/p1/step10/c1_live_probe.json`` and re-derives every asserted flag
and every reported derived cell from the RAW probabilities — never trusting a stored ``*_ok``.

PART 2 (V9–V13) re-derives the C4 ALCE metrics with an INDEPENDENT implementation of the
definitions (its own statement splitter, its own citation regex, its own recall/precision
arithmetic) over fixtures with a hand-set entailment oracle keyed on (statement_index, page), and
compares against the port driven by the same oracle.

Stdlib only. Exits 0 only if every check passes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

PROBE = ROOT / "logs" / "p1" / "step10" / "c1_live_probe.json"
TAU = 0.55  # the config default for guard_nli_threshold, pinned so the verifier is hermetic

checks: list[tuple[str, bool, str]] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok), detail))


# ── PART 1 — the live probe's derived cells ─────────────────────────────────

def verify_probe() -> None:
    if not PROBE.exists():
        ck("V0 probe artifact exists", False, f"missing {PROBE}")
        return
    p = json.loads(PROBE.read_text())
    a, r = p["asserted"], p["reported"]

    id2label = r["head_id2label"]
    true_idx = next((int(k) for k, v in id2label.items() if v.lower() == "entailment"), None)
    ck("V1 A1 index equals the model's own entailment head", a["A1_entailment_index"] == true_idx,
       f"{a['A1_entailment_index']} vs {true_idx}")
    ck("V2 A1_ok re-derives from V1", a["A1_ok"] == (a["A1_entailment_index"] == true_idx))
    ck("V3 A2_ok re-derives from the support prob", a["A2_ok"] == (a["A2_support_prob"] >= TAU),
       f"p={a['A2_support_prob']}")
    ck("V4 A4_ok re-derives from the contradict prob",
       a["A4_ok"] == (a["A4_contradict_prob"] < TAU), f"p={a['A4_contradict_prob']}")
    ck("V5 R1 flag re-derives from the unrelated prob",
       r["R1_unrelated_below_bar"] == (r["R1_unrelated_prob"] < TAU),
       f"p={r['R1_unrelated_prob']}")
    ck("V6 R3 gap equals support minus unrelated",
       r["R3_separation_gap"] == round(a["A2_support_prob"] - r["R1_unrelated_prob"], 6),
       f"{r['R3_separation_gap']}")
    heads = r["R2_head_reads"]
    ck("V7a the head read is 3 pairs × 3 classes",
       all(len(v) == 3 for v in heads.values()) and len(heads) == 3,
       str({k: len(v) for k, v in heads.items()}))
    support_entail = heads["support"][a["A1_entailment_index"]]
    ck("V7b the support row's entailment column equals A2",
       abs(support_entail - round(a["A2_support_prob"], 6)) < 1e-9, f"{support_entail}")
    ck("V8 all_asserted_pass equals the conjunction of the A*_ok flags",
       p["all_asserted_pass"] == all(v for k, v in a.items() if k.endswith("_ok")))


# ── PART 2 — the C4 metric, re-derived independently ────────────────────────

_CIT = re.compile(r"[\[【(]\s*[Pp]age\s*(\d+)\s*[\]】)]")
_SENT = re.compile(r"(?<=[.!?])\s+")


def _reference_alce(answer: str, evidence: dict[int, str],
                    oracle: set[tuple[int, int]]) -> tuple[float | None, float | None, int]:
    """An independent implementation of ALCE citation recall/precision, from the definitions.

    ``oracle`` is the set of (statement_index, page) pairs that entail — the fixture's hand-set
    ground truth, so the comparison tests the METRIC, not a model.
    """
    stmts = [s.strip() for s in _SENT.split(answer.strip()) if s.strip()]
    cites: list[tuple[int, int]] = []
    for i, s in enumerate(stmts):
        for m in _CIT.finditer(s):
            cites.append((i, int(m.group(1))))
    if not cites:
        return None, None, 0
    entailing = {(i, pg) for i, pg in cites if pg in evidence and (i, pg) in oracle}
    covered = {i for i, _ in entailing}
    recall = len(covered) / len(stmts) if stmts else None
    precision = len(entailing) / len(cites)
    return (round(recall, 4) if recall is not None else None), round(precision, 4), len(cites)


class _OracleChecker:
    """An NLI checker whose verdicts are the fixture's hand-set oracle (keyed on (claim_index, page))."""

    def __init__(self, oracle: set[tuple[int, int]]) -> None:
        self._oracle = oracle

    def score_edges(self, edges):
        return [{**e, "is_entailing": (e["claim_index"], e["document_index"]) in self._oracle}
                for e in edges]


def verify_c4() -> None:
    from src.core.config import Settings
    from src.core.guardrails.response import compute_citation_faithfulness, get_nli_checker

    fixtures = [
        # (answer, evidence, oracle: (statement_index, page) that entail)
        ("Energy is conserved [Page 1]. Momentum is conserved.",
         {1: "energy is conserved"}, {(0, 1)}),
        ("Energy is conserved [Page 1] and [Page 2].",
         {1: "energy is conserved", 2: "the cat sat on the mat"}, {(0, 1)}),
        ("The proton mass is 1.67 [Page 1].", {1: "energy is conserved"}, set()),
        ("No citation at all here.", {1: "x"}, set()),
    ]
    for idx, (answer, evidence, oracle) in enumerate(fixtures):
        exp = _reference_alce(answer, evidence, oracle)
        got = compute_citation_faithfulness(answer, evidence, _OracleChecker(oracle))
        ok = (got.citation_recall == exp[0] and got.citation_precision == exp[1]
              and got.n_citations == exp[2])
        ck(f"V{9 + idx} fixture {idx} matches the independent ALCE re-derivation", ok,
           f"port=({got.citation_recall},{got.citation_precision},{got.n_citations}) "
           f"ref=({exp[0]},{exp[1]},{exp[2]})")

    # V13 — the stub checker resolves the entailment column to the real DeBERTa head order.
    checker = get_nli_checker(Settings(use_stub_nli=True, guard_nli_threshold=TAU))
    ck("V13 the stub checker's entailment column matches the model head order",
       checker._entailment_idx == 1, f"idx={checker._entailment_idx}")


def main() -> int:
    verify_probe()
    verify_c4()
    n_pass = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    print(f"\n{n_pass}/{len(checks)} checks PASS")
    return 0 if n_pass == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
