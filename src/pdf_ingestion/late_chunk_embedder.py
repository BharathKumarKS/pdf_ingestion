"""E3 — late chunking: each child embedded from its **parent's** token vectors.

The defect this removes: ``embedder.py`` encodes every child in isolation, so a child that
opens *"This is proportional to the square of the distance…"* is embedded with no antecedent —
the vector cannot know what "This" refers to. Late chunking (Günther et al., *Late Chunking*)
embeds the **parent** once and mean-pools the token vectors that fall inside each child's
character span, so the child's vector is built from hidden states that saw the whole section.

The cluster makes this possible without a local model: ``return_token_embeddings: true`` on
``/embed-text/v1/embeddings`` returns per-token, native-dimension vectors
(``cluster_embedder.ClusterDenseEmbedder.embed_documents_tokens``). Only the **tokenizer** is
local, for character offsets.

Alignment (probed live 2026-10-17 — ``logs/p1/step4/probe_qwen3_alignment.py``,
``alignment.json``): the local ``Qwen/Qwen3-Embedding-0.6B`` tokenizer tokenizes with
``add_special_tokens=False`` and its ``offset_mapping`` tiles the text; the endpoint returns
**exactly one extra trailing** ``<|endoftext|>`` vector. So the content matrix is
``matrix[:-1]`` when ``n_api == n_local + 1``. Both other shapes are handled explicitly and a
third raises — a silent off-by-one here would mis-attribute every child vector.

MRL: the mean is linear, so ``mean(tok)[:64] == mean(tok[:64])`` (pinned by
``test_cluster_embedder.test_mrl_slice_of_a_mean_equals_mean_of_slices``). The 64d view is
therefore taken **after** pooling and re-normalised — late chunking and the two-dim design
compose (plan §2.1).

Cost (measured on ``test_book.pdf``, 19 pages → 968-page extrapolation,
``logs/p1/step4/probe_late_chunk_cost.py``): per-token output is ~160x the pooled payload and
~55x the wall time — ~48 min and ~13.6 GB of JSON for the whole book, one call per parent.
That is why the pipeline embeds **parents**, never children, and why it is a background job.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk
from src.pdf_ingestion.cluster_embedder import (
    ClusterDenseEmbedder,
    StubClusterEmbedder,
    StubTokenizer,
    get_cluster_embedder,
    mrl_slice,
)
from src.pdf_ingestion.models import ParentChunk

# -- Data contract -------------------------------------------------------------

@dataclass
class EnrichedChunk:
    """A child plus the two dense vectors the new index stores.

    Mirrors ``embedder.EmbeddedChunk`` (``chunk`` + vectors) rather than re-declaring the
    child's fields, so ``store.py``'s payload code keeps one shape to handle.
    """

    chunk: TextChunk
    dense_1024: np.ndarray                 # native dim, L2-normalised
    dense_64: np.ndarray                   # MRL prefix, re-normalised
    model_name: str = ""
    # Token index range (half-open) in the parent's tokenization the vector was pooled from;
    # (0, 0) when the span overlapped no token and the parent mean was used instead.
    token_span: tuple[int, int] = (0, 0)
    late_chunked: bool = True


# -- Late-chunk embedder -------------------------------------------------------

class LateChunkEmbedder:
    """Pool per-token cluster vectors over each child's span inside its parent."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: ClusterDenseEmbedder | StubClusterEmbedder | None = None,
        tokenizer=None,
    ) -> None:
        self._cfg = settings or get_settings()
        self._embedder = embedder or get_cluster_embedder(self._cfg)
        self._tokenizer = tokenizer
        self._dim = self._cfg.dense_dim
        self._dim_low = self._cfg.dense_dim_low

    @property
    def model_name(self) -> str:
        return getattr(self._embedder, "model_name", "")

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.late_chunk_enabled)

    def _get_tokenizer(self):
        if self._tokenizer is None:
            if self._cfg.use_stub_embedder:
                # Tests: no download, and offsets that match StubClusterEmbedder's token
                # count, so the real pooling path runs offline.
                self._tokenizer = StubTokenizer()
                logger.warning("StubTokenizer active — token offsets are synthetic")
            else:
                from transformers import AutoTokenizer

                self._tokenizer = AutoTokenizer.from_pretrained(
                    self._cfg.dense_model, cache_dir=self._cfg.model_cache_dir
                )
                logger.info("Late-chunk tokenizer ready: {}", self._cfg.dense_model)
        return self._tokenizer

    # -- Offsets ---------------------------------------------------------------

    def _offsets(self, text: str) -> list[tuple[int, int]]:
        """Character spans of the parent's tokens, plain tokenization (no special tokens)."""
        enc = self._get_tokenizer()(text, add_special_tokens=False, return_offsets_mapping=True)
        return [(int(s), int(e)) for s, e in enc["offset_mapping"]]

    @staticmethod
    def _content_tokens(matrix: np.ndarray, n_local: int, parent_id: int, dim: int) -> np.ndarray:
        """Drop the endpoint's trailing special-token vector; refuse anything else.

        Measured contract (probe, 2026-10-17): ``n_api == n_local + 1`` with the extra vector
        last. ``n_api == n_local`` means a server that does not append it. Any other count
        would silently shift every span by one token, so it raises.
        """
        if matrix.ndim != 2 or matrix.shape[1] != dim:
            raise ValueError(
                f"Per-token matrix for parent {parent_id} has shape {matrix.shape}, "
                f"expected (n_tokens, {dim})"
            )
        n_api = matrix.shape[0]
        if n_api == n_local + 1:
            return matrix[:-1]
        if n_api == n_local:
            logger.debug(
                "Parent {}: endpoint returned no trailing special vector ({} tokens)",
                parent_id, n_local,
            )
            return matrix
        raise ValueError(
            f"Token alignment broken for parent {parent_id}: local tokenizer produced "
            f"{n_local} tokens, the endpoint returned {n_api} vectors. Late chunking needs "
            f"them equal (or the endpoint's single trailing special vector)."
        )

    # -- Pooling ---------------------------------------------------------------

    @staticmethod
    def _pool(
        tokens: np.ndarray,
        offsets: list[tuple[int, int]],
        span: tuple[int, int],
        parent_id: int,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        """Mean of the token vectors overlapping ``[char_start, char_end)``."""
        start, end = span
        indices = [i for i, (ts, te) in enumerate(offsets) if te > start and ts < end]
        if not indices:
            # The class repo's guard: fall back to the parent mean rather than drop the child
            # or emit a zero vector (P0's "silent fallbacks killed" — hence the warning).
            logger.warning(
                "Child span {}:{} of parent {} overlaps no token — using the parent mean",
                start, end, parent_id,
            )
            return tokens.mean(axis=0), (0, 0)
        return tokens[indices].mean(axis=0), (indices[0], indices[-1] + 1)

    def _finish(self, pooled: np.ndarray, chunk: TextChunk, span, late: bool) -> EnrichedChunk:
        dense = np.asarray(pooled, dtype=np.float32)
        dense = dense / (float(np.linalg.norm(dense)) + 1e-9)
        return EnrichedChunk(
            chunk=chunk,
            dense_1024=dense,
            dense_64=mrl_slice(dense, self._dim_low),
            model_name=self.model_name,
            token_span=span,
            late_chunked=late,
        )

    # -- Public API ------------------------------------------------------------

    def embed_parent(
        self, parent: ParentChunk, children: list[TextChunk]
    ) -> list[EnrichedChunk]:
        """Enrich every child of one parent from a single per-token cluster call."""
        if not children:
            return []
        if not parent.text.strip():
            logger.warning("Empty parent text (parent_id={}) — children skipped", parent.parent_id)
            return []

        if not self.enabled:
            logger.info("late_chunk_enabled=False — embedding children in isolation")
            return [self.embed_isolated(c) for c in children]

        offsets = self._offsets(parent.text)
        if not offsets:
            logger.warning(
                "Parent {} tokenized to zero tokens — falling back to isolation embeddings",
                parent.parent_id,
            )
            return [self.embed_isolated(c) for c in children]

        matrix = np.asarray(
            self._embedder.embed_documents_tokens([parent.text])[0], dtype=np.float32
        )
        tokens = self._content_tokens(matrix, len(offsets), parent.parent_id, self._dim)

        out: list[EnrichedChunk] = []
        for child in children:
            pooled, span = self._pool(
                tokens, offsets, (child.char_start, child.char_end), parent.parent_id
            )
            out.append(self._finish(pooled, child, span, late=True))
        logger.debug(
            "Late-chunked parent {} → {} children ({} tokens, {} vectors)",
            parent.parent_id, len(out), len(offsets), matrix.shape[0],
        )
        return out

    def embed_children(
        self, parents: list[ParentChunk], children: list[TextChunk]
    ) -> list[EnrichedChunk]:
        """Enrich a whole document's children, grouped by parent, in document order."""
        by_parent: dict[int, list[TextChunk]] = {}
        for child in children:
            by_parent.setdefault(child.parent_id, []).append(child)

        known = {p.parent_id for p in parents}
        orphans = sorted(pid for pid in by_parent if pid not in known)
        if orphans:
            raise ValueError(f"Children reference parents that do not exist: {orphans}")

        out: list[EnrichedChunk] = []
        for parent in parents:
            out.extend(self.embed_parent(parent, by_parent.get(parent.parent_id, [])))
        logger.success("Enriched {} children from {} parents", len(out), len(parents))
        return out

    def embed_query(self, text: str) -> np.ndarray:
        """Query vector from the same model.

        No instruction is added here: ``ClusterDenseEmbedder.embed_query`` already prepends
        ``query_instruction`` (and the index side must match the query side, not duplicate it).
        """
        return self._embedder.embed_query(text)

    # -- Isolation twin (late_chunk_enabled=False, and the no-token fallback) ----

    def embed_isolated(self, chunk: TextChunk) -> EnrichedChunk:
        """The twin: the same child embedded alone, with no parent context (the E3 control)."""
        vec = self._embedder.embed_documents([chunk.text])[0]
        return self._finish(np.asarray(vec, dtype=np.float32), chunk, (0, 0), late=False)
