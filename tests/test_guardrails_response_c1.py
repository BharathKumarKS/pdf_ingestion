"""C1 — the assertion–evidence bipartite graph (claim extraction → matrix → τ filter → NLI).

Discriminating tests:
  * ``test_matrix_is_the_cartesian_product`` — the graph's edge set and indices;
  * ``test_similarity_filter_is_strictly_above_the_threshold`` — the τ boundary;
  * ``test_isolated_claim_is_an_ungrounded_left_node`` — the hallucination signature;
  * ``test_groundedness_is_the_fraction_of_grounded_claims`` — the score;
  * ``test_groundedness_caps_claims_and_evidence`` — the O(claims × evidence) budget knob;
  * ``test_claim_extractor_falls_back_to_sentence_split`` — the stub-LLM offline path.

All model stages run on the offline stand-ins (``USE_STUB_NLI``) so the suite never downloads
``all-MiniLM-L6-v2`` or ``cross-encoder/nli-deberta-v3-base``.
"""
from __future__ import annotations

import pytest

from src.core.config import Settings
from src.core.guardrails.response import (
    ClaimDocumentMatrixBuilder,
    ClaimExtractor,
    GroundednessEvaluator,
    _parse_claim_json,
    _resolve_entailment_class_index,
    _StubCrossEncoder,
    evaluate_groundedness,
    get_groundedness_evaluator,
    get_nli_checker,
    get_semantic_filter,
)


@pytest.fixture
def cfg():
    return Settings(use_stub_nli=True, guard_similarity_threshold=0.5, guard_nli_threshold=0.55,
                    guard_max_claims=12, guard_max_evidence=8)


# ── The matrix builder ───────────────────────────────────────────────────────

def test_matrix_is_the_cartesian_product():
    m = ClaimDocumentMatrixBuilder().build(["a", "b"], ["x", "y", "z"])
    assert len(m) == 6
    assert [(e["claim_index"], e["document_index"]) for e in m] == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)
    ]
    assert m[0]["claim"] == "a" and m[0]["document"] == "x"


def test_empty_inputs_give_no_edges():
    b = ClaimDocumentMatrixBuilder()
    assert b.build([], ["x"]) == [] and b.build(["a"], []) == []


# ── The similarity pre-filter ────────────────────────────────────────────────

def test_similarity_filter_is_strictly_above_the_threshold(cfg):
    # 'energy conserved' vs itself → cosine 1.0 (kept); vs an unrelated doc → dropped.
    f = get_semantic_filter(cfg)
    matrix = ClaimDocumentMatrixBuilder().build(
        ["energy is conserved", "energy is conserved"],
        ["energy is conserved in closed systems", "the cat sat on the mat"],
    )
    kept = f.filter_pairs(matrix)
    kept_docs = {e["document_index"] for e in kept}
    assert 0 in kept_docs, "a high-overlap pair must survive the τ filter"
    assert 1 not in kept_docs, "an unrelated pair must be dropped"
    assert all(e["semantic_similarity"] > cfg.guard_similarity_threshold for e in kept)


def test_similarity_filter_empty_matrix_is_empty(cfg):
    assert get_semantic_filter(cfg).filter_pairs([]) == []


# ── The NLI entailment checker ───────────────────────────────────────────────

def test_entailment_index_resolves_to_the_entailment_head():
    # The real DeBERTa head order is {0: contradiction, 1: entailment, 2: neutral}.
    assert _resolve_entailment_class_index(_StubCrossEncoder()) == 1


def test_nli_marks_entailing_at_the_threshold(cfg):
    checker = get_nli_checker(cfg)
    edges = [{"claim_index": 0, "document_index": 0,
              "claim": "energy is conserved", "document": "energy is conserved here"}]
    scored = checker.score_edges(edges)
    assert scored[0]["entailment_probability"] == pytest.approx(1.0)
    assert scored[0]["is_entailing"] is True


def test_nli_leaves_an_unsupported_pair_not_entailing(cfg):
    checker = get_nli_checker(cfg)
    edges = [{"claim_index": 0, "document_index": 0,
              "claim": "the proton mass is 1.67", "document": "energy is conserved"}]
    scored = checker.score_edges(edges)
    assert scored[0]["is_entailing"] is False


def test_nli_empty_is_empty(cfg):
    assert get_nli_checker(cfg).score_edges([]) == []


# ── The groundedness evaluator ───────────────────────────────────────────────

def test_groundedness_is_the_fraction_of_grounded_claims(cfg):
    ev = get_groundedness_evaluator(cfg)
    res = ev.evaluate(
        ["energy is conserved", "the proton mass is 1.67"],
        ["energy is conserved in closed systems"],
    )
    assert res["groundedness_score"] == pytest.approx(0.5)
    assert res["claim_results"][0]["is_grounded"] is True
    assert res["claim_results"][1]["is_grounded"] is False


def test_isolated_claim_is_an_ungrounded_left_node(cfg):
    ev = get_groundedness_evaluator(cfg)
    res = ev.evaluate(["the proton mass is 1.67"], ["energy is conserved"])
    cr = res["claim_results"][0]
    assert cr["is_isolated"] is True and cr["is_grounded"] is False
    assert cr["best_edge"] is None and cr["best_entailment_probability"] == 0.0
    assert res["isolated_claims"] == ["the proton mass is 1.67"]


def test_no_claims_is_vacuously_grounded(cfg):
    res = get_groundedness_evaluator(cfg).evaluate([], ["energy is conserved"])
    assert res["groundedness_score"] == 1.0 and res["isolated_claims"] == []


def test_best_edge_is_the_highest_entailment_probability(cfg):
    ev = get_groundedness_evaluator(cfg)
    res = ev.evaluate(["energy is conserved"],
                      ["energy is conserved", "energy is conserved and conserved forever"])
    best = res["claim_results"][0]["best_edge"]
    assert best is not None and best["is_entailing"] is True


# ── The entry point + budget caps ────────────────────────────────────────────

def test_groundedness_caps_claims_and_evidence(cfg):
    cfg.guard_max_claims = 2
    cfg.guard_max_evidence = 1

    class _Extractor:
        def extract(self, _text):
            return ["c1", "c2", "c3", "c4"]

    res = evaluate_groundedness("ignored", ["d1", "d2", "d3"], cfg, extractor=_Extractor())
    # 4 claims capped to 2, 3 documents capped to 1 ⇒ 2 edges (2 claims × 1 document).
    assert len(res["scored_edges"]) <= 2
    assert len(res["claim_results"]) == 2


def test_evaluate_groundedness_uses_the_extractor(cfg):
    class _Extractor:
        def extract(self, _text):
            return ["energy is conserved"]

    res = evaluate_groundedness("whatever", ["energy is conserved"], cfg, extractor=_Extractor())
    assert res["groundedness_score"] == pytest.approx(1.0)


# ── The claim extractor (offline) ────────────────────────────────────────────

def test_claim_extractor_falls_back_to_sentence_split(cfg):
    # The stub LLM returns "{}" → no claims parsed → the lab's sentence-split fallback fires.
    # The lab splits on `[.!?]\s+`, so a final sentence keeps its trailing period (verbatim port).
    claims = ClaimExtractor(cfg).extract("Energy is conserved. Momentum is also conserved.")
    assert claims == ["Energy is conserved", "Momentum is also conserved."]


def test_claim_extractor_empty_text_is_empty(cfg):
    assert ClaimExtractor(cfg).extract("   ") == []


def test_parse_claim_json_accepts_the_object_form():
    assert _parse_claim_json('{"claims": ["a", "b"]}') == ["a", "b"]


def test_parse_claim_json_unwraps_the_object_when_the_array_slice_is_invalid():
    # A second array in the object makes the bracket-slice fallback invalid JSON, so only the
    # explicit `{"claims": ...}` unwrap can recover the claims — this is the object-form guard.
    assert _parse_claim_json('{"claims": ["a", "b"], "extra": [1, 2]}') == ["a", "b"]


def test_parse_claim_json_accepts_a_bare_array():
    assert _parse_claim_json('["a", "b"]') == ["a", "b"]


def test_parse_claim_json_strips_a_fence():
    assert _parse_claim_json('```json\n{"claims": ["a"]}\n```') == ["a"]


def test_parse_claim_json_returns_none_on_garbage():
    assert _parse_claim_json("not json at all") is None
    assert _parse_claim_json("") is None


# ── The factory picks the stand-in ───────────────────────────────────────────

def test_factories_use_the_offline_stand_in_under_stub(cfg):
    from src.core.guardrails.response import _StubEncoder
    assert isinstance(get_semantic_filter(cfg)._model, _StubEncoder)
    assert isinstance(get_nli_checker(cfg)._model, _StubCrossEncoder)


def test_groundedness_evaluator_wires_all_three_stages(cfg):
    ev = get_groundedness_evaluator(cfg)
    assert isinstance(ev, GroundednessEvaluator)
    assert isinstance(ev.matrix_builder, ClaimDocumentMatrixBuilder)
