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
}


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
            return
        try:
            import joblib
            self._clf = joblib.load(model_path)
            logger.info("IntentRouter: loaded trained classifier from {}", model_path)
        except Exception as exc:
            logger.warning("IntentRouter: could not load classifier ({}), using prototypes", exc)

    def _ensure_prototypes(self) -> None:
        if self._proto_matrices is not None:
            return
        from src.pdf_ingestion.embedder import get_embedder
        embedder = get_embedder(self._cfg)
        logger.info("IntentRouter: embedding {} prototype sets…", len(_PROTOTYPES))
        matrices: dict[Intent, np.ndarray] = {}
        for intent, phrases in _PROTOTYPES.items():
            vecs = np.array([embedder.embed_query(p) for p in phrases], dtype=np.float32)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
            matrices[intent] = vecs / norms
        self._proto_matrices = matrices
        logger.info("IntentRouter: prototypes ready")

    def classify(self, query_vector: np.ndarray) -> Intent:
        if self._cfg.use_stub_embedder:
            return Intent.MIXED

        q = np.array(query_vector, dtype=np.float32)

        # Mode 1: trained classifier
        if self._clf is not None:
            label = self._clf.predict([q])[0]
            logger.debug("IntentRouter (trained): '{}'", label)
            return Intent(label)

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
        return best_intent

    def route(self, query_vector: np.ndarray) -> RouteConfig:
        intent = self.classify(query_vector)
        return ROUTE_MAP[intent]


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
