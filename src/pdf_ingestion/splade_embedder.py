"""SPLADE sparse embedder — Phase 4.

SPLADE produces sparse vectors over the full vocabulary. Unlike BM25, it also
expands queries with semantically related terms learned during training.

Three implementations — same interface, pick via factory:
  StubSpladeEmbedder      — deterministic sparse vectors for unit tests
  ClusterSpladeEmbedder   — SV cluster API (GPU inference, no local download)
  FastembedSpladeEmbedder — fastembed ONNX (CPU-friendly, default for local)
"""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# -- Sparse vector type -------------------------------------------------------

class SparseVector:
    """Lightweight sparse vector — matches Qdrant's SparseVector schema."""

    def __init__(self, indices: list[int], values: list[float]) -> None:
        self.indices = indices
        self.values  = values

    def to_qdrant(self):
        from qdrant_client.models import SparseVector as QSparseVector
        return QSparseVector(indices=self.indices, values=self.values)


# -- Stub (fast unit tests, no model download) --------------------------------

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


# -- SV Cluster API (GPU inference, no local model) ---------------------------

class ClusterSpladeEmbedder:
    """
    Calls the SV cluster sparse embedding endpoint.
    URL: http://10.0.10.51:8000/embed-text/v1/sparse-embeddings

    Request:  {"model": "prithivida/Splade_PP_en_v1", "input": [...]}
    Response: {"data": [{"embedding": {"indices": [...], "values": [...]}, "index": 0}]}
    """

    def __init__(self, settings: Settings | None = None) -> None:
        cfg        = settings or get_settings()
        self._url   = cfg.sv_sparse_url
        self._model = cfg.splade_model

    def _post(self, texts: list[str], batch_size: int = 32) -> list[SparseVector]:
        import httpx
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = httpx.post(
                self._url,
                json={"model": self._model, "input": batch},
                timeout=120,
            )
            resp.raise_for_status()
            for item in resp.json()["data"]:
                emb = item["embedding"]
                results.append(SparseVector(indices=emb["indices"], values=emb["values"]))
        return results

    def encode_sparse(self, text: str) -> SparseVector:
        return self._post([text])[0]

    def encode_batch(self, texts: list[str]) -> list[SparseVector]:
        return self._post(texts)


# -- fastembed ONNX (local, CPU-friendly) -------------------------------------

class FastembedSpladeEmbedder:
    """
    SPLADE via fastembed ONNX — no cluster required, runs on CPU.
    Downloads the model once to cfg.model_cache_dir (~532 MB).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg   = settings or get_settings()
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from fastembed import SparseTextEmbedding
        logger.info("Loading SPLADE '{}' via fastembed (ONNX)…", self._cfg.splade_model)
        self._model = SparseTextEmbedding(
            model_name=self._cfg.splade_model,
            cache_dir=self._cfg.model_cache_dir,
        )
        logger.info("SPLADE (fastembed) ready")

    def encode_sparse(self, text: str) -> SparseVector:
        return self.encode_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[SparseVector]:
        self._load()
        results = []
        for e in self._model.embed(texts):
            d = e.as_object()
            results.append(SparseVector(
                indices=list(d["indices"]),
                values=list(d["values"]),
            ))
        return results


# -- Singleton factory --------------------------------------------------------

_splade_instance: StubSpladeEmbedder | ClusterSpladeEmbedder | FastembedSpladeEmbedder | None = None


def get_splade_embedder(
    settings: Settings | None = None,
) -> StubSpladeEmbedder | ClusterSpladeEmbedder | FastembedSpladeEmbedder:
    global _splade_instance
    if _splade_instance is None:
        cfg = settings or get_settings()
        if cfg.use_stub_splade or not cfg.splade_enabled:
            _splade_instance = StubSpladeEmbedder()
        elif cfg.sv_sparse_url:
            _splade_instance = ClusterSpladeEmbedder(settings=cfg)
            logger.info("SPLADE: using SV cluster at {}", cfg.sv_sparse_url)
        else:
            _splade_instance = FastembedSpladeEmbedder(settings=cfg)
            logger.info("SPLADE: using fastembed (local ONNX)")
    return _splade_instance


def reset_splade_embedder() -> None:
    global _splade_instance
    _splade_instance = None
