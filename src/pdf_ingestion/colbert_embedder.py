"""ColBERT v2.0 late-interaction multi-vector embedder.

Each text is encoded as a matrix of (n_tokens, 128) L2-normalised token vectors.
Qdrant uses MaxSim scoring: the query token matrix is compared against the document
token matrix and the maximum cosine similarity per query token is summed.

Model: colbert-ai/colbertv2.0 (BERT base + Linear(768→128) projection head)

For unit tests, StubColBERTEmbedder returns fixed-shape random matrices without
any model download.
"""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# -- Stub (fast unit tests, no model download) ---------------------------------

class StubColBERTEmbedder:
    """Random token matrices — no model download, deterministic per text."""

    STUB_DIM = 128
    STUB_TOKENS = 32    # simulated document token count
    STUB_Q_TOKENS = 16  # simulated query token count

    @property
    def patch_dim(self) -> int:  # compat alias for old code
        return self.STUB_DIM

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        """Returns list of (STUB_TOKENS, 128) float32 matrices."""
        results = []
        for text in texts:
            rng = np.random.default_rng(seed=hash(text) % (2**31))
            mat = rng.random((self.STUB_TOKENS, self.STUB_DIM)).astype(np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
            results.append(mat / norms)
        return results

    def embed_query(self, text: str) -> np.ndarray:
        """Returns (STUB_Q_TOKENS, 128) float32 matrix."""
        rng = np.random.default_rng(seed=hash(text) % (2**31))
        mat = rng.random((self.STUB_Q_TOKENS, self.STUB_DIM)).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        return mat / norms


# -- ColBERT v2.0 (real model) -------------------------------------------------

class ColBERTEmbedder:
    """
    Late-interaction multi-vector encoder using colbert-ai/colbertv2.0.

    Architecture:
        BERT base (bert-base-uncased) → last_hidden_state (B, L, 768)
        Linear(768, 128) → token projections (B, L, 128)
        L2-normalise each token → MaxSim-ready matrices

    Query:   truncated to 32 tokens (ColBERT convention)
    Passage: truncated to 300 tokens
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._tokenizer = None
        self._bert = None
        self._linear = None
        self._device: str = "cuda" if self._cfg.use_gpu else "cpu"

    def _load(self) -> None:
        if self._bert is not None:
            return
        import os
        import torch
        import torch.nn as nn
        from transformers import AutoTokenizer, AutoModel

        os.makedirs(self._cfg.model_cache_dir, exist_ok=True)
        os.environ.setdefault("HF_HOME", self._cfg.model_cache_dir)

        model_name = self._cfg.colbert_model
        logger.info("Loading ColBERT '{}' on {}...", model_name, self._device)

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=self._cfg.model_cache_dir,
        )

        # Load as generic model; colbert-ai/colbertv2.0 is BERT-compatible
        self._bert = AutoModel.from_pretrained(
            model_name,
            cache_dir=self._cfg.model_cache_dir,
            ignore_mismatched_sizes=True,
        )

        # Extract or build the linear projection (768 → colbert_dim)
        hidden_size = getattr(self._bert.config, "hidden_size", 768)
        out_dim = self._cfg.colbert_dim

        if hasattr(self._bert, "linear"):
            self._linear = self._bert.linear
        else:
            self._linear = nn.Linear(hidden_size, out_dim, bias=False)
            # Try to populate weights from state dict
            sd = self._bert.state_dict()
            weight_key = next((k for k in sd if "linear.weight" in k), None)
            if weight_key and sd[weight_key].shape == (out_dim, hidden_size):
                self._linear.weight = nn.Parameter(sd[weight_key])
                logger.info("ColBERT: loaded projection from '{}'", weight_key)
            else:
                logger.warning(
                    "ColBERT: linear projection weights not found in checkpoint — "
                    "using random init. Re-ingest will produce suboptimal results."
                )

        self._bert.eval()
        if self._device == "cuda":
            self._bert = self._bert.cuda()
            self._linear = self._linear.cuda()

        logger.info("ColBERT loaded — dim={}, device={}", out_dim, self._device)

    # -- Public API ------------------------------------------------------------

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        """Encode passage texts → list of (n_tokens, colbert_dim) float32 matrices."""
        self._load()
        return self._encode(texts, max_length=300)

    def embed_query(self, text: str) -> np.ndarray:
        """Encode query → (n_tokens, colbert_dim) float32 matrix."""
        self._load()
        return self._encode([text], max_length=32)[0]

    # -- Internals -------------------------------------------------------------

    def _encode(self, texts: list[str], max_length: int = 300) -> list[np.ndarray]:
        import torch

        inputs = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        if self._device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            out = self._bert(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
            hidden = out.last_hidden_state              # (B, L, 768)
            projected = self._linear(hidden)            # (B, L, 128)
            norms = projected.norm(dim=-1, keepdim=True).clamp(min=1e-9)
            normalised = (projected / norms).float()   # (B, L, 128)

        results = []
        for i, mask in enumerate(inputs["attention_mask"]):
            seq_len = int(mask.sum().item())
            results.append(normalised[i, :seq_len].cpu().numpy())
        return results


# -- Singleton + factory -------------------------------------------------------

_colbert_instance: StubColBERTEmbedder | ColBERTEmbedder | None = None


def get_colbert_embedder(
    settings: Settings | None = None,
) -> StubColBERTEmbedder | ColBERTEmbedder:
    global _colbert_instance
    if _colbert_instance is None:
        cfg = settings or get_settings()
        if cfg.use_stub_colbert or not cfg.colbert_enabled:
            _colbert_instance = StubColBERTEmbedder()
        else:
            _colbert_instance = ColBERTEmbedder(settings=cfg)
    return _colbert_instance


def reset_colbert_embedder() -> None:
    global _colbert_instance
    _colbert_instance = None
