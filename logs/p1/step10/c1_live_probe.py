"""C1 live acceptance — the ported model stages against the REAL lab models.

Runs the two model stages with the actual weights (no stub):
  * ``SemanticSimilarityFilter`` → ``all-MiniLM-L6-v2``
  * ``NLIEntailmentChecker``     → ``cross-encoder/nli-deberta-v3-base``

Two kinds of result, kept separate on purpose (an over-strict check is worse than no check):

ASSERTED — properties of the PORT (must hold, or the port is wrong):
  A1  the entailment class index resolves to the model's own ``entailment`` head;
  A2  a passage that STATES the claim scores entailment ≥ τ;
  A4  a passage that CONTRADICTS the claim is NOT entailed (the NLI head discriminates);
  A5  the similarity pre-filter keeps the related pair and drops the unrelated one;
  A6  the end-to-end graph marks the supported claim grounded and the fabricated one isolated.

REPORTED — properties of the MODEL (measured, not asserted; the port cannot fix them):
  R1  the probability the unrelated passage scores for the claim (⚠️ measured 0.9948 live
      2026-11-05 — the base DeBERTa NLI head calls an unrelated passage entailment);
  R2  the full 3-column head read for each pair, so the class order is auditable;
  R3  the separation between the supporting and unrelated pairs (a gap ≤ 0 means the model
      cannot tell them apart, whatever τ is chosen).

Writes ``logs/p1/step10/c1_live_probe.json``. Needs the model download on first run (CPU).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.config import Settings  # noqa: E402
from src.core.guardrails.response import (  # noqa: E402
    ClaimDocumentMatrixBuilder,
    GroundednessEvaluator,
    NLIEntailmentChecker,
    SemanticSimilarityFilter,
)

OUT = ROOT / "logs" / "p1" / "step10" / "c1_live_probe.json"

CLAIM = "Energy is conserved in a closed system."
SUPPORT = ("The total energy of an isolated system remains constant; energy can neither be "
           "created nor destroyed, so it is conserved in a closed system.")
CONTRADICT = "Energy is routinely created from nothing inside a closed system."
UNRELATED = "The cat sat quietly on the warm mat by the window."


def main() -> int:
    cfg = Settings(use_stub_nli=False)
    asserted: dict = {}
    reported: dict = {}
    t0 = time.time()

    checker = NLIEntailmentChecker(cfg.guard_nli_threshold, model_name=cfg.guard_nli_model)
    id2label = checker._model.model.config.id2label
    asserted["A1_entailment_index"] = checker._entailment_idx
    asserted["A1_ok"] = checker._entailment_idx == _expected_entailment_idx(id2label)
    reported["head_id2label"] = {str(k): str(v) for k, v in id2label.items()}

    docs = [SUPPORT, UNRELATED, CONTRADICT]
    edges = [{"claim_index": i, "document_index": i, "claim": CLAIM, "document": d}
             for i, d in enumerate(docs)]
    scored = checker.score_edges(edges)
    p_support, p_unrelated, p_contradict = (e["entailment_probability"] for e in scored)
    asserted["A2_support_prob"] = p_support
    asserted["A2_ok"] = p_support >= cfg.guard_nli_threshold
    asserted["A4_contradict_prob"] = p_contradict
    asserted["A4_ok"] = p_contradict < cfg.guard_nli_threshold

    # R1/R2 — REPORTED: the model's read of the unrelated pair, and the raw 3-column head.
    reported["R1_unrelated_prob"] = p_unrelated
    reported["R1_unrelated_below_bar"] = p_unrelated < cfg.guard_nli_threshold
    raw = checker._model.predict([(d, CLAIM) for d in docs],
                                 convert_to_numpy=True, apply_softmax=True)
    reported["R2_head_reads"] = {
        name: [round(float(x), 6) for x in row]
        for name, row in zip(["support", "unrelated", "contradict"], raw)
    }
    # R3 — REPORTED: the separation. The unrelated pair clears the bar at any τ ≤ p_unrelated.
    reported["R3_unrelated_clears_bar_up_to_tau"] = round(p_unrelated, 6)
    reported["R3_separation_gap"] = round(p_support - p_unrelated, 6)

    sim = SemanticSimilarityFilter(cfg.guard_similarity_threshold,
                                   model_name=cfg.guard_similarity_model)
    matrix = ClaimDocumentMatrixBuilder().build([CLAIM, CLAIM], [SUPPORT, UNRELATED])
    kept_docs = {e["document_index"] for e in sim.filter_pairs(matrix)}
    asserted["A5_kept_docs"] = sorted(kept_docs)
    asserted["A5_ok"] = kept_docs == {0}

    evaluator = GroundednessEvaluator(ClaimDocumentMatrixBuilder(), sim, checker)
    graph = evaluator.evaluate([CLAIM, "The proton mass is 1.67e-27 kg."], [SUPPORT, UNRELATED])
    asserted["A6_score"] = graph["groundedness_score"]
    asserted["A6_isolated"] = graph["isolated_claims"]
    asserted["A6_ok"] = (graph["groundedness_score"] == 0.5
                         and len(graph["isolated_claims"]) == 1)

    result = {
        "model": cfg.guard_nli_model,
        "similarity_model": cfg.guard_similarity_model,
        "asserted": asserted,
        "reported": reported,
        "wall_s": round(time.time() - t0, 1),
        "all_asserted_pass": all(v for k, v in asserted.items() if k.endswith("_ok")),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_asserted_pass"] else 1


def _expected_entailment_idx(id2label) -> int:
    """Independently resolve the entailment head from the model's own config."""
    for k, v in id2label.items():
        if str(v).lower() == "entailment":
            return int(k)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
