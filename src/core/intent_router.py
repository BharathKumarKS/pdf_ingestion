"""
Intent router — Phase 4.

Classifies a user query into one of five retrieval intents using cosine
similarity against pre-embedded prototype queries. Uses the query vector
already computed for vector search — zero extra embedding calls.

Intents and the retrieval routes they activate:
  factual  → vector only           (specific fact, definition, formula)
  overview → vector + RAPTOR       (broad topic, chapter summary)
  multihop → vector + GraphRAG     (prerequisite, relationship, "why")
  visual   → ColPali only          (diagram, figure, table, graph)
  mixed    → vector + RAPTOR + GraphRAG  (complex / ambiguous query)

The router is a singleton — prototype embeddings are computed once on first
use and cached in memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# ── Intent definitions ────────────────────────────────────────────────────────

class Intent(str, Enum):
    FACTUAL  = "factual"
    OVERVIEW = "overview"
    MULTIHOP = "multihop"
    VISUAL   = "visual"
    MIXED    = "mixed"
    # R5 (§I114) — the domain gate's reject class. NOT a retrieval route: an off-scope query's
    # correct action is a clean refusal, not a search. It is in the enum so the classifier can be
    # TRAINED to predict it; until the retrain adds the class, it is never predicted, so adding it
    # is behaviour-neutral on the current model.
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class RouteConfig:
    """Which retrieval routes to activate for a given intent."""
    use_vector:  bool = True
    use_raptor:  bool = False
    use_graph:   bool = False
    use_colpali: bool = False


ROUTE_MAP: dict[Intent, RouteConfig] = {
    Intent.FACTUAL:  RouteConfig(use_vector=True,  use_raptor=False, use_graph=False, use_colpali=False),
    Intent.OVERVIEW: RouteConfig(use_vector=True,  use_raptor=True,  use_graph=False, use_colpali=False),
    Intent.MULTIHOP: RouteConfig(use_vector=True,  use_raptor=False, use_graph=True,  use_colpali=False),
    Intent.VISUAL:   RouteConfig(use_vector=False, use_raptor=False, use_graph=False, use_colpali=True),
    Intent.MIXED:    RouteConfig(use_vector=True,  use_raptor=True,  use_graph=True,  use_colpali=False),
    # The refusal route: no lane fires. A caller sees all-False and returns a refusal (the
    # grounding/security door, Act III) rather than running an empty search.
    Intent.OUT_OF_SCOPE: RouteConfig(use_vector=False, use_raptor=False, use_graph=False, use_colpali=False),
}


def is_refusal(route: RouteConfig) -> bool:
    """True when a route activates NO lane — the out-of-scope refusal (Act III's security door)."""
    return not (route.use_vector or route.use_raptor or route.use_graph or route.use_colpali)


@dataclass
class GateDecision:
    """The three-band domain-gate decision (the lesson plan's "cheap first gate").

    ``band`` is ``"in"`` (confidently in domain — admit), ``"out"`` (confidently off domain —
    reject) or ``"ambiguous"`` (the uncertainty band — escalate to the next stage). ``confidence``
    is ``P(out_of_scope)`` from the classifier (NaN in prototype mode, which has no probabilities).
    """
    intent: Intent
    band: str
    confidence: float
    refuse: bool


# ── Prototype queries per intent ──────────────────────────────────────────────
# These are embedded once at startup and used for cosine similarity scoring.
# Physics-domain prototypes — extend for other subjects as needed.

_PROTOTYPES: dict[Intent, list[str]] = {
    Intent.FACTUAL: [
        "What is Newton's second law?",
        "Define kinetic energy",
        "What is the formula for momentum?",
        "What is the value of Planck's constant?",
        "State Ohm's law",
        "What does F equals ma mean?",
        "Define electric field",
        "What is the speed of light?",
        "What is Coulomb's law?",
        "Define work done by a force",
    ],
    Intent.OVERVIEW: [
        "Give me an overview of classical mechanics",
        "Summarize the chapter on conservation laws",
        "Explain the main themes in electromagnetism",
        "What are the key ideas in thermodynamics?",
        "Describe the big picture of quantum mechanics",
        "How does Feynman introduce energy?",
        "What are the main concepts covered in this section?",
        "Give a broad summary of wave mechanics",
    ],
    Intent.MULTIHOP: [
        "Why does a satellite stay in orbit?",
        "What should I understand before learning Maxwell's equations?",
        "How is simple harmonic motion related to wave propagation?",
        "How do conservation laws connect different areas of physics?",
        "What are the prerequisites for understanding quantum tunneling?",
        "How does Newton's law lead to orbital mechanics?",
        "Why does a pendulum swing the way it does?",
        "How does the concept of energy appear across mechanics and thermodynamics?",
        "What connects electricity and magnetism?",
    ],
    Intent.VISUAL: [
        "Show me the diagram of the double-slit experiment",
        "Find the page with the force diagram for an inclined plane",
        "Which page shows the sinusoidal wave illustration?",
        "Find the table comparing wavelengths of electromagnetic radiation",
        "Show me the graph of pressure versus volume in an ideal gas",
        "Find the figure explaining the photoelectric effect",
        "Which page has the circuit diagram?",
        "Show me the picture of the pendulum setup",
    ],
    # R5 (§I114) — the off-domain class. The corpus is physics (Feynman Vol 1); these are the
    # queries the book cannot address. ⚠️ The classifier is only as good as its NEGATIVE class, so
    # these are curated deliberately (the lesson plan: "curate out-of-domain examples with the same
    # care you brought to the retrieval corpus"). ⚠️ §I114 measured the CEILING: an off-domain
    # signal targets the 12 `neg-out` queries only; the 22 in-domain negatives need the response-side
    # grounding floor, not this gate.
    Intent.OUT_OF_SCOPE: [
        "What is the capital of France?",
        "Who won the last World Cup?",
        "Give me a recipe for chocolate cake",
        "What is the best stock to buy this year?",
        "Tell me a joke about programmers",
        "How do I write a cover letter?",
        "What is the weather in London tomorrow?",
        "Summarize the plot of Hamlet",
        "What is the latest smartphone model?",
        "How do I fix a leaking tap?",
        "What are the symptoms of the flu?",
        "Who is the current prime minister?",
    ],
}


# ── Router ────────────────────────────────────────────────────────────────────

class IntentRouter:
    """
    Query intent classifier.

    Two modes depending on whether a trained model is available:

    1. Trained classifier (preferred): loads a joblib-serialised sklearn model
       from cfg.intent_classifier_path. predict() returns the intent label.

    2. Prototype similarity (fallback): cosine similarity against pre-embedded
       hand-crafted prototype queries. Zero training data required but accuracy
       is unmeasured.
    """

    CONFIDENCE_THRESHOLD = 0.30  # used only in prototype mode

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._clf = None           # trained sklearn classifier (mode 1)
        self._proto_matrices: dict[Intent, np.ndarray] | None = None  # mode 2
        self._try_load_classifier()

    def _try_load_classifier(self) -> None:
        """Load trained sklearn classifier if the model file exists."""
        from pathlib import Path
        model_path = Path(self._cfg.intent_classifier_path)
        if not model_path.exists():
            logger.warning(
                "IntentRouter: classifier model not found at {} — using prototype "
                "similarity mode (lower accuracy). Train once with: "
                "uv run python scripts/train_intent_classifier.py",
                model_path,
            )
            return
        try:
            import joblib
            from sklearn.linear_model import LogisticRegression
            clf = joblib.load(model_path)
            # Schema check before trusting the artifact: a wrong-type or wrong-dim
            # model would otherwise predict garbage while logging a clean load.
            if not isinstance(clf, LogisticRegression):
                raise TypeError(
                    f"expected sklearn LogisticRegression, got {type(clf).__name__}"
                )
            n_feat = getattr(clf, "n_features_in_", None)
            if n_feat != self._cfg.dense_dim:
                raise ValueError(
                    f"classifier expects {n_feat} features but the dense lane produces "
                    f"{self._cfg.dense_dim}; re-train with the current embedder "
                    f"(uv run python scripts/train_intent_classifier.py --train-only)"
                )
            self._clf = clf
            logger.info("IntentRouter: loaded trained classifier from {}", model_path)
        except Exception as exc:
            logger.warning(
                "IntentRouter: classifier at {} failed validation ({}) — using "
                "prototype similarity (lower accuracy)",
                model_path, exc,
            )

    def _ensure_prototypes(self) -> None:
        if self._proto_matrices is not None:
            return
        # The prototypes must live in the same space as the incoming query vector, so they
        # come from the dense lane (cluster Qwen3 + the query instruction) — NOT the retired
        # local 768d Nomic embedder. A mismatch here is a shape error on the first query.
        from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
        embedder = get_cluster_embedder(self._cfg)
        logger.info("IntentRouter: embedding {} prototype sets…", len(_PROTOTYPES))
        matrices: dict[Intent, np.ndarray] = {}
        for intent, phrases in _PROTOTYPES.items():
            vecs = np.array([embedder.embed_query(p) for p in phrases], dtype=np.float32)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
            matrices[intent] = vecs / norms
        self._proto_matrices = matrices
        logger.info("IntentRouter: prototypes ready")

    def classify(self, query_vector: np.ndarray) -> Intent:
        from src.core import telemetry

        if self._cfg.use_stub_embedder:
            return Intent.MIXED

        q = np.array(query_vector, dtype=np.float32)

        # Mode 1: trained classifier
        if self._clf is not None:
            try:
                label = self._clf.predict([q])[0]
                logger.debug("IntentRouter (trained): '{}'", label)
                intent = Intent(label)
                with telemetry.span("intent_route", {"intent": intent.value, "mode": "classifier"}):
                    pass
                return intent
            except Exception as exc:
                logger.warning(
                    "IntentRouter: trained classifier failed ({}), falling back to prototypes. "
                    "Re-train against the dense lane: "
                    "uv run python scripts/train_intent_classifier.py --train-only",
                    exc,
                )
                self._clf = None  # don't retry every query

        # Mode 2: prototype similarity
        self._ensure_prototypes()
        q = q / (np.linalg.norm(q) + 1e-9)
        best_intent = Intent.MIXED
        best_score  = self.CONFIDENCE_THRESHOLD
        for intent, matrix in self._proto_matrices.items():
            score = float((matrix @ q).max())
            if score > best_score:
                best_score  = score
                best_intent = intent
        logger.debug("IntentRouter (prototype): '{}' (score={:.3f})", best_intent, best_score)
        with telemetry.span("intent_route", {
            "intent": best_intent.value,
            "score": round(best_score, 4),
            "mode": "prototype",
        }):
            pass
        return best_intent

    def route(self, query_vector: np.ndarray) -> RouteConfig:
        intent = self.classify(query_vector)
        return ROUTE_MAP[intent]

    def gate(self, query_vector: np.ndarray) -> GateDecision:
        """R5 — the three-band domain gate. Reads the classifier's PROBABILITY, not just its label.

        "Let the cheap model's own uncertainty route the escalation": confidently in domain →
        admit; confidently off domain → reject; between the two thresholds → escalate (band
        ``"ambiguous"``). Cost then scales with the width of the confusion band, not with traffic.

        ⚠️ Behaviour-neutral until the classifier is RE-TRAINED with ``out_of_scope``: a model with
        no such class yields ``P(out)=0`` → band ``"in"``, never a refusal. The retrain is a run.
        """
        intent = self.classify(query_vector)

        # Prototype mode (or a model with no probabilities): only an explicit out_of_scope label
        # refuses. There is no probability to band on.
        if self._clf is None or not hasattr(self._clf, "predict_proba"):
            refuse = intent is Intent.OUT_OF_SCOPE
            return GateDecision(intent, "out" if refuse else "in", float("nan"), refuse)

        classes = list(getattr(self._clf, "classes_", []))
        if Intent.OUT_OF_SCOPE.value not in classes:
            return GateDecision(intent, "in", 0.0, False)

        q = np.array(query_vector, dtype=np.float32)
        try:
            probs = self._clf.predict_proba([q])[0]
        except Exception as exc:  # noqa: BLE001 — a gate must not crash the request path
            logger.warning("IntentRouter.gate: predict_proba failed ({}); admitting", exc)
            return GateDecision(intent, "in", float("nan"), False)

        p_out = float(probs[classes.index(Intent.OUT_OF_SCOPE.value)])
        if p_out >= self._cfg.guard_domain_out_conf:
            return GateDecision(intent, "out", p_out, True)
        if p_out <= self._cfg.guard_domain_in_conf:
            return GateDecision(intent, "in", p_out, False)
        return GateDecision(intent, "ambiguous", p_out, False)


# ── Singleton ─────────────────────────────────────────────────────────────────

_router_instance: IntentRouter | None = None


def get_intent_router(settings: Settings | None = None) -> IntentRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter(settings=settings or get_settings())
    return _router_instance


def reset_intent_router() -> None:
    global _router_instance
    _router_instance = None
