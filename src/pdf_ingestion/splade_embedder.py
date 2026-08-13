"""
SPLADE sparse embedder — Phase 4.

SPLADE (SParse Lexical AnD Expansion) produces sparse vectors over the full
vocabulary (~30k BERT token dimensions). Unlike BM25, SPLADE also expands
queries and documents with semantically related terms learned during training.
For example, "velocity" activates "speed", "motion", "kinematics" — catching
matches that dense-only search misses.

Used alongside Jina v3 dense vectors in Qdrant hybrid search with RRF fusion:
  dense (Jina)  → semantic similarity
  sparse (SPLADE) → keyword + synonym matching
  RRF fusion     → combines both signals

Model: naver/splade-cocondenser-selfdistil (~500MB, CPU-friendly)
"""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# ── Sparse vector type ────────────────────────────────────────────────────────

class SparseVector:
    """Lightweight sparse vector — matches Qdrant's SparseVector schema."""
    def __init__(self, indices: list[int], values: list[float]) -> None:
        self.indices = indices
        self.values  = values

    def to_qdrant(self):
        from qdrant_client.models import SparseVector as QSparseVector
        return QSparseVector(indices=self.indices, values=self.values)


# ── Stub (no model download for tests) ───────────────────────────────────────

class StubSpladeEmbedder:
    """Returns deterministic sparse vectors — no model needed for tests."""

    def encode_sparse(self, text: str) -> SparseVector:
        rng     = np.random.default_rng(seed=abs(hash(text)) % (2 ** 31))
        n       = 20
        indices = sorted(rng.choice(30522, size=n, replace=False).tolist())
        values  = rng.random(n).tolist()
        return SparseVector(indices=indices, values=values)

    def encode_batch(self, texts: list[str]) -> list[SparseVector]:
        return [self.encode_sparse(t) for t in texts]


# ── Real SPLADE embedder ──────────────────────────────────────────────────────

class SpladeEmbedder:
    """
    Encodes text as SPLADE sparse vectors using naver/splade-cocondenser-selfdistil.

    Encoding formula (SPLADE):
        sparse_vec[token] = max_over_positions( log(1 + ReLU(logit[token])) )

    Result: dict-like sparse vector with non-zero weights on relevant token IDs.
    Semantically related tokens get non-zero weights even if absent from the text.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg   = settings or get_settings()
        self._model = None
        self._tok   = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        model_name = self._cfg.splade_model
        cache_dir  = self._cfg.model_cache_dir

        logger.info("Loading SPLADE model '{}' on device=cpu…", model_name)
        self._tok   = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)
        self._model = AutoModelForMaskedLM.from_pretrained(model_name, cache_dir=cache_dir)
        self._model.eval()
        logger.info("SPLADE loaded — vocab size {}", self._tok.vocab_size)

    def encode_sparse(self, text: str) -> SparseVector:
        """Encode a single text to a sparse vector."""
        return self.encode_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[SparseVector]:
        """Encode a batch of texts to sparse vectors."""
        import torch
        self._load()

        inputs = self._tok(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        with torch.no_grad():
            logits = self._model(**inputs).logits   # (batch, seq_len, vocab)

        # SPLADE pooling: log(1 + ReLU(logit)).max(dim=seq_len)
        scores = torch.log(1 + torch.relu(logits)).max(dim=1).values  # (batch, vocab)

        results = []
        for row in scores:
            nz_mask = row > 0
            indices = nz_mask.nonzero(as_tuple=False).squeeze(1).tolist()
            values  = row[nz_mask].tolist()
            results.append(SparseVector(indices=indices, values=values))

        return results


# ── Singleton factory ─────────────────────────────────────────────────────────

_splade_instance: StubSpladeEmbedder | SpladeEmbedder | None = None


def get_splade_embedder(
    settings: Settings | None = None,
) -> StubSpladeEmbedder | SpladeEmbedder:
    global _splade_instance
    if _splade_instance is None:
        cfg = settings or get_settings()
        if cfg.use_stub_splade or not cfg.splade_enabled:
            _splade_instance = StubSpladeEmbedder()
        else:
            _splade_instance = SpladeEmbedder(settings=cfg)
    return _splade_instance


def reset_splade_embedder() -> None:
    global _splade_instance
    _splade_instance = None
