"""ColBERT v2.0 late-interaction multi-vector embedder.

Each text is encoded as a matrix of (n_tokens, 128) L2-normalised token vectors.
Qdrant uses MaxSim scoring: the query token matrix is compared against the document
token matrix and the maximum cosine similarity per query token is summed.

Three implementations — same interface, pick via factory:
  StubColBERTEmbedder      — deterministic random matrices for unit tests
  ClusterColBERTEmbedder   — SV cluster API (GPU inference, no local download)
  FastembedColBERTEmbedder — fastembed ONNX (CPU-friendly, default for local)
"""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# -- Stub (fast unit tests, no model download) ---------------------------------

class StubColBERTEmbedder:
    """Random token matrices — no model download, deterministic per text."""

    STUB_DIM = 128
    STUB_TOKENS = 32
    STUB_Q_TOKENS = 16

    @property
    def patch_dim(self) -> int:
        return self.STUB_DIM

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        results = []
        for text in texts:
            rng = np.random.default_rng(seed=hash(text) % (2**31))
            mat = rng.random((self.STUB_TOKENS, self.STUB_DIM)).astype(np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
            results.append(mat / norms)
        return results

    def embed_query(self, text: str) -> np.ndarray:
        rng = np.random.default_rng(seed=hash(text) % (2**31))
        mat = rng.random((self.STUB_Q_TOKENS, self.STUB_DIM)).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        return mat / norms


# -- SV Cluster API (GPU inference, no local model) ---------------------------

class ClusterColBERTEmbedder:
    """
    Calls the SV cluster ColBERT endpoint.
    URL: http://10.0.10.51:8000/embed-text/v1/multivector-embeddings

    Request:  {"model": "colbert-ir/colbertv2.0", "input": [...], "encoding_type": "document"|"query"}
    Response: {"data": [{"embedding": [[...token vecs...]], "index": 0}, ...]}
    """

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        self._url   = cfg.sv_colbert_url
        self._model = cfg.colbert_model

    def _post(self, texts: list[str], encoding_type: str, batch_size: int = 4) -> list[np.ndarray]:
        import httpx
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = httpx.post(
                self._url,
                json={"model": self._model, "input": batch, "encoding_type": encoding_type},
                timeout=120,
            )
            resp.raise_for_status()
            for item in resp.json()["data"]:
                mat = np.array(item["embedding"], dtype=np.float32)
                if mat.ndim == 1:
                    mat = mat[np.newaxis, :]  # cluster returns (dim,) for query
                norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
                results.append(mat / norms)
        return results

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        return self._post(texts, "document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._post([text], "query")[0]


# -- fastembed ONNX (local, CPU-friendly) -------------------------------------

class FastembedColBERTEmbedder:
    """
    ColBERT via fastembed ONNX — no cluster required, runs on CPU.
    Downloads the model once to cfg.model_cache_dir (~436 MB).
    Uses query_embed() for queries and embed() for passages — fastembed
    applies the correct token prefixes automatically.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg   = settings or get_settings()
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from fastembed import LateInteractionTextEmbedding
        logger.info("Loading ColBERT '{}' via fastembed (ONNX)…", self._cfg.colbert_model)
        self._model = LateInteractionTextEmbedding(
            model_name=self._cfg.colbert_model,
            cache_dir=self._cfg.model_cache_dir,
        )
        logger.info("ColBERT (fastembed) ready")

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        self._load()
        results = []
        for mat in self._model.embed(texts):
            m = np.array(mat, dtype=np.float32)
            norms = np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
            results.append(m / norms)
        return results

    def embed_query(self, text: str) -> np.ndarray:
        self._load()
        mat = np.array(list(self._model.query_embed(text))[0], dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        return mat / norms


# -- Singleton factory --------------------------------------------------------

_colbert_instance: StubColBERTEmbedder | ClusterColBERTEmbedder | FastembedColBERTEmbedder | None = None


def get_colbert_embedder(
    settings: Settings | None = None,
) -> StubColBERTEmbedder | ClusterColBERTEmbedder | FastembedColBERTEmbedder:
    global _colbert_instance
    if _colbert_instance is None:
        cfg = settings or get_settings()
        if cfg.use_stub_colbert or not cfg.colbert_enabled:
            _colbert_instance = StubColBERTEmbedder()
        elif cfg.sv_colbert_url:
            _colbert_instance = ClusterColBERTEmbedder(settings=cfg)
            logger.info("ColBERT: using SV cluster at {}", cfg.sv_colbert_url)
        else:
            _colbert_instance = FastembedColBERTEmbedder(settings=cfg)
            logger.info("ColBERT: using fastembed (local ONNX)")
    return _colbert_instance


def reset_colbert_embedder() -> None:
    global _colbert_instance
    _colbert_instance = None
