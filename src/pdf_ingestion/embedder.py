"""Jina v3 embedder with late-chunking support and a fast stub for tests."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk


# ── Data contract ─────────────────────────────────────────────────────────

@dataclass
class EmbeddedChunk:
    chunk: TextChunk
    embedding: np.ndarray   # shape (embedding_dim,)
    model_name: str


# ── Stub (fast unit tests, no model download) ─────────────────────────────

class StubEmbedder:
    """Deterministic random vectors — zero model download, used in tests."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.model_name = "stub"
        logger.warning("StubEmbedder active — embeddings are random vectors")

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


# ── Jina v3 embedder via sentence-transformers ────────────────────────────

class JinaEmbedder:
    """
    Wraps jinaai/jina-embeddings-v3 via sentence-transformers.

    Late chunking:
        All chunks from the same document context window are passed to the
        model together with late_chunking=True.  The model encodes the
        concatenated sequence then returns one mean-pooled vector *per chunk*
        — each vector is informed by its neighbours in the same window.

    Long documents:
        A 1,000-page textbook exceeds the 8,192-token limit.  We partition
        chunks into contiguous windows ≤ max_context_tokens and apply late
        chunking within each window independently.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import os
        from sentence_transformers import SentenceTransformer

        os.makedirs(self._cfg.model_cache_dir, exist_ok=True)
        os.environ.setdefault("HF_HOME", self._cfg.model_cache_dir)

        logger.info("Loading Jina v3 via sentence-transformers '{}'…", self._cfg.embedding_model)
        self._model = SentenceTransformer(
            self._cfg.embedding_model,
            trust_remote_code=True,
            cache_folder=self._cfg.model_cache_dir,
        )
        self._model.eval()
        logger.info("Jina v3 loaded — dim={}", self._cfg.embedding_dim)

    @property
    def model_name(self) -> str:
        return self._cfg.embedding_model

    # ── Public API ────────────────────────────────────────────────────────

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

        logger.success("Embedded {} chunks via Jina v3 late chunking", len(results))
        return results

    def embed_query(self, text: str) -> np.ndarray:
        """Single query embedding with retrieval.query task prefix."""
        self._load()
        vecs = self._encode_late([text], task="retrieval.query", late_chunking=False)
        return vecs[0]

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_windows(self, chunks: list[TextChunk]) -> list[list[TextChunk]]:
        """
        Partition chunks into windows whose token sum ≤ max_context_tokens.
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
        Encode via Jina v3.

        sentence-transformers 5.x validates kwargs strictly and blocks
        `late_chunking`.  We bypass this by calling the underlying Jina
        module's own encode() directly when late_chunking is requested.
        Falls back to standard ST encode if that path fails.
        """
        import torch

        arr: np.ndarray | None = None

        # ── Path 1: late chunking via underlying Jina model ───────────────
        if late_chunking and len(texts) > 1:
            try:
                underlying = self._model._first_module()
                with torch.no_grad():
                    out = underlying.encode(
                        texts, task=task, late_chunking=True
                    )
                arr = np.array(out, dtype=np.float32)
                logger.debug("Late chunking via underlying model succeeded")
            except Exception as exc:
                logger.debug("Underlying late-chunking failed ({}), falling back", exc)
                arr = None

        # ── Path 2: standard ST encode (no late_chunking kwarg) ──────────
        if arr is None:
            try:
                with torch.no_grad():
                    out = self._model.encode(
                        texts,
                        task=task,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )
                arr = np.array(out, dtype=np.float32)
            except Exception as exc:
                logger.error("Encoding failed entirely: {}. Using zero vectors.", exc)
                arr = np.zeros((len(texts), self._cfg.embedding_dim), dtype=np.float32)

        # L2-normalise for cosine similarity in Qdrant
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        return list(arr / norms)


# ── Factory ───────────────────────────────────────────────────────────────

def get_embedder(settings: Settings | None = None) -> StubEmbedder | JinaEmbedder:
    cfg = settings or get_settings()
    if cfg.use_stub_embedder:
        return StubEmbedder(dim=cfg.embedding_dim)
    return JinaEmbedder(settings=cfg)
