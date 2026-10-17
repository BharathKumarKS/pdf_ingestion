"""
ColPali visual embedder — Phase 3.

ColPali (vidore/colpali-v1.2) produces a matrix of patch embeddings per page
image (late-interaction multi-vector). Qdrant stores these with MaxSim scoring
so visual search retrieves the most relevant page without collapsing to a
single representative vector.

Patch shape: (N_patches, patch_dim) per page  — typically (1030, 128) in prod.
Stub shape:  (32, 128) per page               — deterministic, no model download.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


@dataclass
class EmbeddedPage:
    page_image_id: str
    document_id: str
    page_number: int
    patch_embeddings: np.ndarray   # shape (N_patches, patch_dim)
    qdrant_point_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# -- Stub (no model download needed for tests) ---------------------------------

class StubColPaliEmbedder:
    """Returns seeded random patch matrices — identical API to ColPaliEmbedder."""

    STUB_PATCHES = 32
    STUB_DIM = 128

    def embed_pages(self, images: list) -> list[np.ndarray]:
        results = []
        for img in images:
            seed = abs(hash(str(id(img)))) % (2**31)
            rng = np.random.default_rng(seed)
            patches = rng.random((self.STUB_PATCHES, self.STUB_DIM)).astype(np.float32)
            norms = np.linalg.norm(patches, axis=1, keepdims=True) + 1e-9
            results.append(patches / norms)
        return results

    def embed_query_image(self, image) -> np.ndarray:
        seed = abs(hash(str(id(image)))) % (2**31)
        rng = np.random.default_rng(seed)
        patches = rng.random((self.STUB_PATCHES, self.STUB_DIM)).astype(np.float32)
        norms = np.linalg.norm(patches, axis=1, keepdims=True) + 1e-9
        return patches / norms

    def embed_query_text(self, text: str) -> np.ndarray:
        """Deterministic stub of the text-query path (same shape as a page)."""
        seed = abs(hash(str(text))) % (2**31)
        rng = np.random.default_rng(seed)
        patches = rng.random((self.STUB_PATCHES, self.STUB_DIM)).astype(np.float32)
        norms = np.linalg.norm(patches, axis=1, keepdims=True) + 1e-9
        return patches / norms

    @property
    def patch_dim(self) -> int:
        return self.STUB_DIM


# -- ColPali -------------------------------------------------------------------

class ColPaliEmbedder:
    """Wraps vidore/colpali-v1.2 for page-level multi-vector embeddings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._model = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from colpali_engine.models import ColPali, ColPaliProcessor

        device = "cuda" if (self._cfg.use_gpu and torch.cuda.is_available()) else "cpu"
        logger.info("Loading ColPali model '{}' on {}", self._cfg.colpali_model, device)
        self._model = ColPali.from_pretrained(
            self._cfg.colpali_model,
            cache_dir=self._cfg.model_cache_dir,
        ).to(device).eval()
        self._processor = ColPaliProcessor.from_pretrained(
            self._cfg.colpali_model,
            cache_dir=self._cfg.model_cache_dir,
        )
        self._device = device

    def embed_pages(self, images: list) -> list[np.ndarray]:
        """
        Embed a list of PIL images.
        Returns one (N_patches, patch_dim) float32 array per image.
        """
        import torch
        self._load()
        results: list[np.ndarray] = []
        batch_size = max(1, self._cfg.embedding_batch_size // 4)  # ColPali is heavier

        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            try:
                inputs = self._processor.process_images(batch).to(self._device)
                with torch.no_grad():
                    embeddings = self._model(**inputs)  # (B, N_patches, D)
                for j in range(len(batch)):
                    patches = embeddings[j].cpu().numpy().astype(np.float32)
                    norms = np.linalg.norm(patches, axis=1, keepdims=True) + 1e-9
                    results.append(patches / norms)
            except Exception as exc:
                logger.warning("ColPali batch {} failed ({}), using zeros", i, exc)
                for _ in batch:
                    results.append(np.zeros((1, self._cfg.colpali_patch_dim), dtype=np.float32))

        return results

    def embed_query_image(self, image) -> np.ndarray:
        """Embed a single query PIL image into patch vectors."""
        return self.embed_pages([image])[0]

    def embed_query_text(self, text: str) -> np.ndarray:
        """Embed a text query into the SAME patch space as the stored page images.

        ColPali is a late-interaction model: ``process_queries`` runs the text
        through the same encoder that produced the page vectors, so the resulting
        (N_patches, patch_dim) matrix is comparable to the stored pages under
        MaxSim. No re-ingest — the text path shares the page embedding space.

        The patch count is not fixed (a short query yields far fewer patches than
        a 1031-patch page), which is why ``visual_search`` normalises by the
        query's own patch count rather than a constant.
        """
        import torch
        self._load()
        with torch.no_grad():
            inputs = self._processor.process_queries([text]).to(self._device)
            embeddings = self._model(**inputs)  # (1, N_patches, D)
        patches = embeddings[0].cpu().numpy().astype(np.float32)
        norms = np.linalg.norm(patches, axis=1, keepdims=True) + 1e-9
        return patches / norms

    @property
    def patch_dim(self) -> int:
        return self._cfg.colpali_patch_dim


# -- Singleton factory --------------------------------------------------------

# ColPali loads ~5.5 GB of weights. Constructing one per call (as this factory
# used to) reloaded the model for EVERY query, which thrashed memory and
# OOM-killed a 33-query visual run at query 15. Cached exactly like
# get_colbert_embedder / get_reranker; reset in tests.
_colpali_instance: StubColPaliEmbedder | ColPaliEmbedder | None = None


def get_colpali_embedder(
    settings: Settings | None = None,
) -> StubColPaliEmbedder | ColPaliEmbedder:
    global _colpali_instance
    if _colpali_instance is None:
        cfg = settings or get_settings()
        if cfg.use_stub_colpali:
            _colpali_instance = StubColPaliEmbedder()
        else:
            _colpali_instance = ColPaliEmbedder(settings=cfg)
    return _colpali_instance


def reset_colpali_embedder() -> None:
    global _colpali_instance
    _colpali_instance = None
