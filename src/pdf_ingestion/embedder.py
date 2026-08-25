"""Nomic MRL embedder (replaces Jina v3) with a fast stub for tests.

Key changes vs Jina v3:
- Model: nomic-ai/nomic-embed-text-v1.5 (Apache 2.0, Matryoshka-capable)
- Task prefixes: "search_query: " / "search_document: " (no late-chunking)
- MRL truncation: full 768d vector is sliced to 64d then re-normalised
  → EmbeddedChunk carries both embedding (768d) and embedding_low (64d)
- embed_query() still returns a single 768d array; store.search() computes
  the 64d slice internally when building the nested Qdrant prefetch.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk


# -- Data contract -------------------------------------------------------------

@dataclass
class EmbeddedChunk:
    chunk: TextChunk
    embedding: np.ndarray       # shape (embedding_dim,)  — full 768d dense
    model_name: str
    embedding_low: np.ndarray = field(default_factory=lambda: np.array([]))
    # shape (embedding_dim_low,) — 64d MRL truncation; populated by NomicEmbedder


# -- Stub (fast unit tests, no model download) ---------------------------------

class StubEmbedder:
    """Deterministic random vectors — zero model download, used in tests."""

    def __init__(self, dim: int = 768, dim_low: int = 64) -> None:
        self.dim = dim
        self.dim_low = dim_low
        self.model_name = "stub"
        logger.warning("StubEmbedder active — embeddings are random vectors")

    def embed_chunks(self, chunks: list[TextChunk]) -> list[EmbeddedChunk]:
        rng = np.random.default_rng(seed=42)
        results = []
        for chunk in chunks:
            vec = rng.random(self.dim).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-9
            vec_low = vec[: self.dim_low].copy()
            vec_low /= np.linalg.norm(vec_low) + 1e-9
            results.append(EmbeddedChunk(
                chunk=chunk,
                embedding=vec,
                embedding_low=vec_low,
                model_name=self.model_name,
            ))
        return results

    def embed_query(self, text: str) -> np.ndarray:
        rng = np.random.default_rng(seed=hash(text) % (2**31))
        vec = rng.random(self.dim).astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-9)

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        rng = np.random.default_rng(seed=42)
        results = []
        for _ in texts:
            vec = rng.random(self.dim).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-9
            results.append(vec)
        return results


# -- Nomic MRL embedder --------------------------------------------------------

class NomicEmbedder:
    """
    Wraps nomic-ai/nomic-embed-text-v1.5 via sentence-transformers.

    Task prefixes (Nomic convention):
        Queries  → "search_query: " prefix
        Passages → "search_document: " prefix

    Matryoshka (MRL):
        Full 768d embedding is sliced to 64d and re-normalised.
        Both dimensions are stored in Qdrant (dense_768 and dense_64).
        The 64d vector is used for a fast first-stage ANN; 768d rescores.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._model = None
        self._device: str = "cuda" if self._cfg.use_gpu else "cpu"

    def _load(self) -> None:
        if self._model is not None:
            return
        import os
        from sentence_transformers import SentenceTransformer

        os.makedirs(self._cfg.model_cache_dir, exist_ok=True)
        os.environ.setdefault("HF_HOME", self._cfg.model_cache_dir)

        logger.info(
            "Loading Nomic embed v1.5 '{}' on device={}...",
            self._cfg.embedding_model,
            self._device,
        )
        st_kwargs: dict = {
            "trust_remote_code": True,
            "cache_folder": self._cfg.model_cache_dir,
        }
        if self._device == "cuda":
            st_kwargs["device"] = "cuda"

        self._model = SentenceTransformer(self._cfg.embedding_model, **st_kwargs)
        self._model.eval()
        logger.info(
            "Nomic embed loaded — device={}, full_dim={}, low_dim={}",
            self._device, self._cfg.embedding_dim, self._cfg.embedding_dim_low,
        )

    @property
    def model_name(self) -> str:
        return self._cfg.embedding_model

    # -- Public API ------------------------------------------------------------

    def embed_chunks(self, chunks: list[TextChunk]) -> list[EmbeddedChunk]:
        """Embed passage chunks with the 'search_document:' task prefix."""
        self._load()
        if not chunks:
            return []

        texts = ["search_document: " + c.text for c in chunks]
        vecs = self._encode(texts)

        results = []
        for chunk, vec in zip(chunks, vecs):
            vec_low = self._truncate(vec, self._cfg.embedding_dim_low)
            results.append(EmbeddedChunk(
                chunk=chunk,
                embedding=vec,
                embedding_low=vec_low,
                model_name=self.model_name,
            ))

        logger.success("Embedded {} chunks via Nomic MRL (device={})", len(results), self._device)
        return results

    def embed_query(self, text: str) -> np.ndarray:
        """Single query embedding with 'search_query:' task prefix. Returns 768d."""
        self._load()
        vecs = self._encode(["search_query: " + text])
        return vecs[0]

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        """Batch embed raw strings as passages (for re-indexing). Returns 768d each."""
        self._load()
        prefixed = ["search_document: " + t for t in texts]
        return self._encode(prefixed)

    # -- Internals -------------------------------------------------------------

    @staticmethod
    def _truncate(vec: np.ndarray, dim: int) -> np.ndarray:
        """MRL truncation: slice to first `dim` dims and re-normalise."""
        low = vec[:dim].copy()
        norm = np.linalg.norm(low) + 1e-9
        return low / norm

    def _encode(self, texts: list[str]) -> list[np.ndarray]:
        """Encode texts via sentence-transformers, L2-normalise, return list."""
        import torch

        batch_size = self._cfg.embedding_batch_size
        arr: np.ndarray | None = None

        try:
            with torch.no_grad():
                out = self._model.encode(
                    texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
            arr = np.array(out, dtype=np.float32)
        except Exception as exc:
            logger.error("Nomic encoding failed: {}. Using zero vectors.", exc)
            arr = np.zeros((len(texts), self._cfg.embedding_dim), dtype=np.float32)

        # Ensure L2-normalised (normalize_embeddings=True should handle it)
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        return list(arr / norms)


# -- Factory -------------------------------------------------------------------

def get_embedder(settings: Settings | None = None) -> StubEmbedder | NomicEmbedder:
    cfg = settings or get_settings()
    if cfg.use_stub_embedder:
        return StubEmbedder(dim=cfg.embedding_dim, dim_low=cfg.embedding_dim_low)
    return NomicEmbedder(settings=cfg)
