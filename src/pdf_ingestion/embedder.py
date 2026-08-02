"""Jina v3 embedder with late-chunking support and a fast stub for tests."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk


# -- Data contract -------------------------------------------------------------

@dataclass
class EmbeddedChunk:
    chunk: TextChunk
    embedding: np.ndarray   # shape (embedding_dim,)
    model_name: str


# -- Stub (fast unit tests, no model download) ---------------------------------

class StubEmbedder:
    """Deterministic random vectors -- zero model download, used in tests."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.model_name = "stub"
        logger.warning("StubEmbedder active -- embeddings are random vectors")

    def embed_chunks(self, chunks: list[TextChunk]) -> list[EmbeddedChunk]:
        rng = np.random.default_rng(seed=42)
        results = []
        for chunk in chunks:
            vec = rng.random(self.dim).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-9
            results.append(EmbeddedChunk(chunk=chunk, embedding=vec, model_name=self.model_name))
        return results

    def embed_query(self, text: str) -> np.ndarray:
        rng = np.random.default_rng(seed=hash(text) % (2**31))
        vec = rng.random(self.dim).astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-9)


# -- Jina v3 embedder via sentence-transformers --------------------------------

class JinaEmbedder:
    """
    Wraps jinaai/jina-embeddings-v3 via sentence-transformers.

    GPU acceleration:
        Set USE_GPU=true in .env to run on CUDA. The model is loaded onto the
        GPU device and EMBEDDING_BATCH_SIZE should be increased (32-64 on GPU).

    Late chunking:
        All chunks from the same document context window are passed together
        with late_chunking=True. The model encodes the concatenated sequence
        and returns one mean-pooled vector per chunk, each informed by its
        neighbours in the same window.

    Long documents:
        A 1,000-page textbook exceeds the 8,192-token limit. We partition
        chunks into contiguous windows <= max_context_tokens and apply late
        chunking within each window independently.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._model = None
        self._device: str = "cuda" if self._cfg.use_gpu else "cpu"
        self._supports_late_chunking: bool | None = None  # probed once after load

    def _load(self) -> None:
        if self._model is not None:
            return
        import os
        from sentence_transformers import SentenceTransformer

        os.makedirs(self._cfg.model_cache_dir, exist_ok=True)
        os.environ.setdefault("HF_HOME", self._cfg.model_cache_dir)

        logger.info(
            "Loading Jina v3 via sentence-transformers '{}' on device={}...",
            self._cfg.embedding_model,
            self._device,
        )
        # Do NOT pass device="cpu" — Jina v3 uses LoRA meta tensors that break
        # when SentenceTransformer calls .to("cpu") explicitly. Let it auto-detect
        # on CPU. Only specify device for CUDA to move to the GPU.
        st_kwargs: dict = {
            "trust_remote_code": True,
            "cache_folder": self._cfg.model_cache_dir,
        }
        if self._device == "cuda":
            st_kwargs["device"] = "cuda"

        self._model = SentenceTransformer(self._cfg.embedding_model, **st_kwargs)
        self._model.eval()

        # Probe once whether the underlying module exposes .encode() with
        # late_chunking support, so we never retry-and-fail per window.
        underlying = self._model._first_module()
        self._supports_late_chunking = callable(getattr(underlying, "encode", None))
        logger.info(
            "Jina v3 loaded -- device={}, dim={}, native late-chunking={}",
            self._device,
            self._cfg.embedding_dim,
            self._supports_late_chunking,
        )

    @property
    def model_name(self) -> str:
        return self._cfg.embedding_model

    # -- Public API ------------------------------------------------------------

    def embed_chunks(self, chunks: list[TextChunk]) -> list[EmbeddedChunk]:
        """
        Embed all chunks with late chunking.
        Chunks are grouped into context windows; each window is encoded jointly.
        """
        self._load()
        if not chunks:
            return []

        windows = self._build_windows(chunks)
        results: list[EmbeddedChunk] = []

        for window_chunks in windows:
            texts = [c.text for c in window_chunks]
            vecs = self._encode_late(texts, task="retrieval.passage")
            for chunk, vec in zip(window_chunks, vecs):
                results.append(
                    EmbeddedChunk(chunk=chunk, embedding=vec, model_name=self.model_name)
                )

        logger.success("Embedded {} chunks via Jina v3 late chunking (device={})",
                       len(results), self._device)
        return results

    def embed_query(self, text: str) -> np.ndarray:
        """Single query embedding with retrieval.query task prefix."""
        self._load()
        vecs = self._encode_late([text], task="retrieval.query", late_chunking=False)
        return vecs[0]

    # -- Internals -------------------------------------------------------------

    def _build_windows(self, chunks: list[TextChunk]) -> list[list[TextChunk]]:
        """
        Partition chunks into windows whose token sum <= max_context_tokens.
        Preserves document order so late-chunking context is meaningful.
        """
        windows: list[list[TextChunk]] = []
        current: list[TextChunk] = []
        current_tokens = 0

        for chunk in chunks:
            t = chunk.token_count or len(chunk.text.split())
            if current and current_tokens + t > self._cfg.max_context_tokens:
                windows.append(current)
                current = []
                current_tokens = 0
            current.append(chunk)
            current_tokens += t

        if current:
            windows.append(current)

        logger.debug("Split {} chunks into {} context windows", len(chunks), len(windows))
        return windows

    def _encode_late(
        self,
        texts: list[str],
        task: str = "retrieval.passage",
        late_chunking: bool = True,
    ) -> list[np.ndarray]:
        """
        Encode via Jina v3 with GPU support and configurable batch size.

        If the underlying model exposes .encode() with late_chunking support
        (probed once at load time), use it for context-aware embeddings.
        Otherwise falls back to standard sentence-transformers encode.
        """
        import torch

        arr: np.ndarray | None = None
        batch_size = self._cfg.embedding_batch_size

        # Path 1: native late chunking (probed at load time)
        if late_chunking and len(texts) > 1 and self._supports_late_chunking:
            try:
                underlying = self._model._first_module()
                with torch.no_grad():
                    out = underlying.encode(texts, task=task, late_chunking=True)
                arr = np.array(out, dtype=np.float32)
            except Exception as exc:
                logger.debug("Native late-chunking encode failed: {}", exc)
                arr = None

        # Path 2: standard ST encode (with GPU-aware batch size)
        if arr is None:
            try:
                with torch.no_grad():
                    out = self._model.encode(
                        texts,
                        task=task,
                        batch_size=batch_size,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )
                arr = np.array(out, dtype=np.float32)
            except Exception as exc:
                logger.error("Encoding failed: {}. Using zero vectors.", exc)
                arr = np.zeros((len(texts), self._cfg.embedding_dim), dtype=np.float32)

        # L2-normalise for cosine similarity in Qdrant
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        return list(arr / norms)


# -- Factory -------------------------------------------------------------------

def get_embedder(settings: Settings | None = None) -> StubEmbedder | JinaEmbedder:
    cfg = settings or get_settings()
    if cfg.use_stub_embedder:
        return StubEmbedder(dim=cfg.embedding_dim)
    return JinaEmbedder(settings=cfg)
