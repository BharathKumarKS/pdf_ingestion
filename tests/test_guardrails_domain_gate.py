"""R5 — the domain gate (`out_of_scope`) and the three-band decision.

Discriminating tests (each fails without its implementation):
  * ``test_out_of_scope_route_refuses`` — the refusal route activates no lane;
  * ``test_gate_bands_on_probability`` — confident-out rejects, confident-in admits, the middle
    escalates (the lesson plan's "read the probability, not just the label");
  * ``test_gate_is_neutral_without_the_class`` — a model with no `out_of_scope` class NEVER refuses
    (behaviour-neutral until the retrain);
  * ``test_training_script_covers_out_of_scope`` — the retrain can actually produce the class.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from src.core.config import Settings
from src.core.intent_router import (
    ROUTE_MAP,
    GateDecision,
    Intent,
    IntentRouter,
    is_refusal,
)


@pytest.fixture
def cfg():
    return Settings(use_stub_embedder=True, qdrant_in_memory=True)


class _FakeClf:
    """A stand-in classifier exposing exactly the surface the gate reads."""

    def __init__(self, classes: list[str], label: str, p_out: float):
        self.classes_ = np.array(classes)
        self._label = label
        self._p_out = p_out

    def predict(self, X):
        return [self._label]

    def predict_proba(self, X):
        n = len(self.classes_)
        probs = np.full(n, (1.0 - self._p_out) / max(n - 1, 1))
        if "out_of_scope" in list(self.classes_):
            probs[list(self.classes_).index("out_of_scope")] = self._p_out
        return np.array([probs])


# ── The route ────────────────────────────────────────────────────────────────

def test_out_of_scope_route_refuses():
    r = ROUTE_MAP[Intent.OUT_OF_SCOPE]
    assert is_refusal(r) is True, "the out-of-scope route must activate no lane"
    assert not (r.use_vector or r.use_raptor or r.use_graph or r.use_colpali)


def test_normal_routes_are_not_refusals():
    for intent in (Intent.FACTUAL, Intent.OVERVIEW, Intent.MULTIHOP, Intent.VISUAL, Intent.MIXED):
        assert is_refusal(ROUTE_MAP[intent]) is False


def test_out_of_scope_is_a_real_intent_member():
    assert Intent.OUT_OF_SCOPE.value == "out_of_scope"


# ── The three-band gate ──────────────────────────────────────────────────────

def _router(cfg, clf) -> IntentRouter:
    r = IntentRouter(settings=cfg)
    r._clf = clf  # bypass the on-disk artifact; the gate reads _clf directly
    return r


def test_gate_rejects_when_confidently_off_domain(cfg):
    r = _router(cfg, _FakeClf(["factual", "out_of_scope"], "out_of_scope", 0.90))
    d = r.gate(np.zeros(cfg.dense_dim, dtype=np.float32))
    assert isinstance(d, GateDecision) and d.band == "out" and d.refuse is True
    assert d.confidence == pytest.approx(0.90)


def test_gate_admits_when_confidently_in_domain(cfg):
    r = _router(cfg, _FakeClf(["factual", "out_of_scope"], "factual", 0.05))
    d = r.gate(np.zeros(cfg.dense_dim, dtype=np.float32))
    assert d.band == "in" and d.refuse is False


def test_gate_escalates_in_the_uncertainty_band(cfg):
    r = _router(cfg, _FakeClf(["factual", "out_of_scope"], "factual", 0.35))
    d = r.gate(np.zeros(cfg.dense_dim, dtype=np.float32))
    assert d.band == "ambiguous" and d.refuse is False, "the middle band must not reject"


def test_gate_is_neutral_without_the_class(cfg):
    """A model trained before out_of_scope existed must NEVER refuse — behaviour-neutral."""
    r = _router(cfg, _FakeClf(["factual", "overview"], "factual", 0.0))
    d = r.gate(np.zeros(cfg.dense_dim, dtype=np.float32))
    assert d.band == "in" and d.refuse is False and d.confidence == 0.0


def test_gate_refuses_in_prototype_mode_on_an_explicit_label(cfg, monkeypatch):
    r = IntentRouter(settings=cfg)
    r._clf = None
    monkeypatch.setattr(r, "classify", lambda q: Intent.OUT_OF_SCOPE)
    d = r.gate(np.zeros(cfg.dense_dim, dtype=np.float32))
    assert d.band == "out" and d.refuse is True


# ── The retrain can produce the class ────────────────────────────────────────

def test_training_script_covers_out_of_scope():
    script = Path(__file__).resolve().parents[1] / "scripts" / "train_intent_classifier.py"
    spec = importlib.util.spec_from_file_location("tic_under_test", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "out_of_scope" in mod.INTENTS
    assert "out_of_scope" in mod.GENERATION_PROMPTS
