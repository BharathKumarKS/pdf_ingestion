"""Dense text embedder served by the SupportVectors cluster.

The model lives on the cluster; nothing is downloaded locally. Mirrors the class repo's
pattern — `Labs/Week_6/sv_rag_pipeline/src/svrag/late_chunk_embedder.py` and the
`02-contextual_and_late_chunking.ipynb` "API-based late chunking" cell — where only the
*tokenizer* is local (for character offsets) and the vectors come over HTTP.

Endpoint: ``POST {sv_embed_url}`` with ``{"model": ..., "input": [...]}``.

Two views of one model:

* ``embed_documents(texts)``      -> pooled ``(N, dense_dim)``, L2-normalised
* ``embed_query(text)``           -> pooled ``(dense_dim,)``, with the query instruction
* ``embed_documents_tokens(texts)`` -> per-token ``(n_tokens, dense_dim)``, for late chunking

The last one sets ``return_token_embeddings: true``. That flag is what makes late chunking
possible against the cluster at all: the default response is a single pooled vector per
input, and no endpoint exposes a dense model's per-token hidden states otherwise.

**The endpoint returns UNNORMALISED vectors** (measured 2026-10-17, Qwen3-Embedding-0.6B:
pooled query norm ≈ 70.1, pooled passage ≈ 83.9, per-token ≈ 90–131). So the L2
normalisation the docstrings promise is done **client-side** here, for the pooled paths
only — per-token vectors must stay raw, because the mean is taken before normalising
(``late_chunk_embedder._finish``). Leaving the pooled paths raw is invisible under Qdrant's
COSINE distance (which normalises internally) and is a landmine for any consumer that does a
dot product: the index side normalises, the query side did not, so a bare
``query @ doc`` was off by a factor of ~6,000.

MRL: the cluster **ignores** a ``dimensions`` parameter (verified 2026-10-16: asking
Qwen3-Embedding-0.6B for 64/256/512 returns 1024 every time), so the low-dimensional view
is sliced client-side and re-normalised — the same shape as ``NomicEmbedder._truncate``.
"""
from __future__ import annotations

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


def mrl_slice(vec: np.ndarray, dim: int) -> np.ndarray:
    """Matryoshka truncation: take the first ``dim`` coordinates and re-normalise.

    Cosine similarity assumes unit norm, and a truncated prefix of a unit vector is not
    unit-length, so the re-normalisation is required, not cosmetic.
    """
    low = np.asarray(vec, dtype=np.float32)[:dim].copy()
    norm = float(np.linalg.norm(low)) + 1e-9
    return low / norm


def l2_normalise(vec: np.ndarray) -> np.ndarray:
    """Unit-length view of ``vec`` — the endpoint's pooled vectors are not normalised."""
    arr = np.asarray(vec, dtype=np.float32)
    return arr / (float(np.linalg.norm(arr)) + 1e-9)


# -- Stub (fast unit tests, no network) ----------------------------------------

class StubClusterEmbedder:
    """Deterministic pseudo-random vectors — no cluster, no download."""

    def __init__(self, dim: int = 1024, dim_low: int = 64) -> None:
        self.dim = dim
        self.dim_low = dim_low
        self.model_name = "stub"
        logger.warning("StubClusterEmbedder active — embeddings are random vectors")

    @staticmethod
    def _unit(rng: np.random.Generator, shape: tuple[int, ...]) -> np.ndarray:
        arr = rng.random(shape).astype(np.float32)
        return arr / (np.linalg.norm(arr, axis=-1, keepdims=True) + 1e-9)

    def _seed(self, text: str) -> np.random.Generator:
        return np.random.default_rng(seed=hash(text) % (2**31))

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        return [self._unit(self._seed(t), (self.dim,)) for t in texts]

    def embed_query(self, text: str) -> np.ndarray:
        return self._unit(self._seed(text), (self.dim,))

    def embed_documents_tokens(self, texts: list[str]) -> list[np.ndarray]:
        # ~1 token per 4 characters, floor 1 — deterministic, so tests can assert shapes.
        return [self._unit(self._seed(t), (max(1, len(t) // 4), self.dim)) for t in texts]


class StubTokenizer:
    """Token offsets consistent with :class:`StubClusterEmbedder`'s token count.

    The stub embedder returns ``max(1, len(text) // 4)`` vectors per text, so the stub
    tokenizer must yield **exactly that many** offsets or ``LateChunkEmbedder._content_tokens``
    raises on an alignment mismatch. They live in one file so the invariant is visible: the
    real endpoint's count and the local tokenizer's count are the pair that must agree.

    Mirrors the HF-fast call signature the late-chunk embedder uses. Offsets tile the text.
    """

    TOKENS_PER_CHAR = 4

    def __call__(self, text, add_special_tokens=True, return_offsets_mapping=False):
        n = max(1, len(text) // self.TOKENS_PER_CHAR)
        step = max(1, len(text) // n)
        offsets: list[tuple[int, int]] = []
        start = 0
        for i in range(n):
            end = len(text) if i == n - 1 else min(start + step, len(text))
            offsets.append((start, end))
            start = end
        out: dict = {"input_ids": list(range(n))}
        if return_offsets_mapping:
            out["offset_mapping"] = offsets
        return out


# -- SV cluster (GPU inference, no local model) --------------------------------

class ClusterDenseEmbedder:
    """Dense embeddings from the SV cluster's ``/embed-text/v1/embeddings`` endpoint."""

    def __init__(self, settings: Settings | None = None, client=None) -> None:
        cfg = settings or get_settings()
        if not cfg.sv_embed_url:
            raise ValueError(
                "ClusterDenseEmbedder requires sv_embed_url (set SV_EMBED_URL), e.g. "
                "http://10.0.10.70:8123/embed-text/v1/embeddings"
            )
        self._url = cfg.sv_embed_url
        self._model = cfg.dense_model
        self._dim = cfg.dense_dim
        self._dim_low = cfg.dense_dim_low
        self._instruction = cfg.query_instruction
        self._batch_size = max(1, cfg.embedding_batch_size)
        self._client = client  # injected in tests (httpx.MockTransport)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def dim_low(self) -> int:
        return self._dim_low

    # -- HTTP ------------------------------------------------------------------

    def _post(self, texts: list[str], token_embeddings: bool) -> list[np.ndarray]:
        import httpx

        client = self._client or httpx.Client(timeout=120)
        results: list[np.ndarray] = []
        try:
            for i in range(0, len(texts), self._batch_size):
                batch = texts[i : i + self._batch_size]
                payload: dict = {"model": self._model, "input": batch}
                if token_embeddings:
                    payload["return_token_embeddings"] = True
                resp = client.post(self._url, json=payload)
                resp.raise_for_status()
                items = resp.json()["data"]
                # The server returns `index`; honour it rather than trusting array order
                # (same contract as ClusterColBERTEmbedder — a reordered batch would
                # otherwise attach embeddings to the wrong texts, silently).
                for item in sorted(items, key=lambda it: it.get("index", 0)):
                    arr = np.asarray(item["embedding"], dtype=np.float32)
                    if token_embeddings and arr.ndim == 3:
                        arr = arr[0]  # (1, n_tokens, dim) -> (n_tokens, dim)
                    elif not token_embeddings and arr.ndim == 2:
                        arr = arr[0]
                    results.append(arr)
        finally:
            if self._client is None:
                client.close()
        return results

    # -- Public API ------------------------------------------------------------

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        """Pooled passage embeddings, L2-normalised. Documents carry no instruction."""
        if not texts:
            return []
        return [l2_normalise(v) for v in self._post(texts, token_embeddings=False)]

    def embed_query(self, text: str) -> np.ndarray:
        """Pooled query embedding, L2-normalised, with the configured instruction."""
        return l2_normalise(self._post([self._instruction + text], token_embeddings=False)[0])

    def embed_documents_tokens(self, texts: list[str]) -> list[np.ndarray]:
        """Per-token passage embeddings ``(n_tokens, dim)`` — the late-chunking input."""
        if not texts:
            return []
        return self._post(texts, token_embeddings=True)


# -- Singleton factory ---------------------------------------------------------

_cluster_embedder: StubClusterEmbedder | ClusterDenseEmbedder | None = None


def get_cluster_embedder(
    settings: Settings | None = None,
) -> StubClusterEmbedder | ClusterDenseEmbedder:
    global _cluster_embedder
    if _cluster_embedder is None:
        cfg = settings or get_settings()
        if cfg.use_stub_embedder:
            _cluster_embedder = StubClusterEmbedder(dim=cfg.dense_dim, dim_low=cfg.dense_dim_low)
        else:
            _cluster_embedder = ClusterDenseEmbedder(settings=cfg)
            logger.info(
                "Dense embedder: SV cluster '{}' at {}", cfg.dense_model, cfg.sv_embed_url
            )
    return _cluster_embedder


def reset_cluster_embedder() -> None:
    global _cluster_embedder
    _cluster_embedder = None


def get_query_vector(text: str, settings: Settings | None = None) -> np.ndarray:
    """The query vector for the dense lane — the model that built the index.

    A query must be embedded by the same model as the documents, or the two live in
    different spaces: Nomic's 768d and Qwen3's 1024d are not comparable, and Qdrant rejects
    a 768d query against a ``dense_1024`` slot outright. This is the single accessor for
    that model, so the index side (``chunking_pipeline`` → ``LateChunkEmbedder``) and the
    query side cannot drift apart. The instruction is prepended by ``embed_query``.
    """
    return get_cluster_embedder(settings).embed_query(text)
