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

Alignment (probed per model — ``logs/p1/step4/probe_qwen3_alignment.py`` for Qwen3 and
``logs/p1/step10/probe_nomic_alignment.py`` for nomic): the local tokenizer tokenizes with
``add_special_tokens=False`` and its ``offset_mapping`` tiles the text, while the endpoint wraps the
input in its own special tokens. **How many, and WHERE they sit, is a property of one tokenizer +
one server** — so it is declared per model in ``_DECLARED_SPECIALS`` and re-probed, never inherited.
Qwen3 adds one TRAILING ``<|endoftext|>`` (``matrix[:-1]``); nomic adds **two TRAILING and no leading
token** (``matrix[:-2]``), so ``matrix[:-1]`` would keep one special vector and shift every child's
pooling window (§I77, plan trap 3). ⚠️ The BERT-style guess — ``[CLS] … [SEP]``, one LEADING and one
trailing — was **wrong**, and the probe is what caught it. A layout that does not match the
declaration raises rather than shifting.

⚠️ **The document-side prefix is part of this contract.** The endpoint is handed
``document_prefix + parent.text``, so the character offsets must be computed on the **same prefixed
string** and each child's span translated by ``len(prefix)``. Applying the prefix to one side only
shifts every span with no warning at all (plan trap 2) — the failure this module is most exposed to.

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

# -- Endpoint special-token layout ---------------------------------------------
#
# The per-token endpoint wraps its input in its own special tokens, so the response carries
# `n_local + leading + trailing` vectors — and `_content_tokens` needs BOTH numbers, not their sum.
# For a BERT-style tokenizer the layout is `[CLS] content… [SEP]`, so the content matrix is
# `matrix[1:-1]`; dropping only the last vector would shift every child's pooling window by one
# token, silently. §I77's addendum established nomic's DELTA (+2) but explicitly NOT which two
# tokens they are, so this map is filled by **measurement**
# (`logs/p1/step10/probe_nomic_alignment.py`).
#
# ⚠️ The probe MEASURES; this map DECLARES — deliberately separate, because a probe that both
# discovers and authorises the rule is a guard that can never fail. `probe_alignment` asserts the
# live endpoint still matches the declaration.
_DECLARED_SPECIALS: dict[str, tuple[int, int]] = {
    # (leading, trailing) special-token vectors the endpoint adds.
    # 0 leading + 2 TRAILING (``matrix[:-2]``) — MEASURED 2026-10-25, not assumed:
    # ``probe_nomic_alignment.json`` puts the best offset at 0 with a 7.87x margin over the
    # runner-up. The BERT-style ``[CLS] … [SEP]`` guess (1, 1) was wrong; it would have pooled
    # every child one token off, silently.
    "nomic-ai/nomic-embed-text-v1.5": (0, 2),
    "Qwen/Qwen3-Embedding-0.6B": (0, 1),        # probed 2026-10-17 (one trailing <|endoftext|>)
}


def declared_specials(model: str) -> tuple[int, int]:
    """``(leading, trailing)`` special-token vectors the endpoint adds for ``model``.

    Raises for an undeclared model rather than assuming the Qwen3 contract: guessing the layout is
    not an off-by-one on a count, it is a silent shift of every child's pooling window (§I77).
    """
    try:
        return _DECLARED_SPECIALS[model]
    except KeyError:
        raise ValueError(
            f"No declared special-token layout for {model!r}. The per-token endpoint wraps its "
            f"input, and late chunking must know WHERE the specials sit (leading vs trailing) — "
            f"assuming the Qwen3 contract would shift every child's pooling window. Probe it "
            f"(logs/p1/step10/probe_nomic_alignment.py) and declare the result in "
            f"late_chunk_embedder._DECLARED_SPECIALS."
        ) from None


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
        specials: tuple[int, int] | None = None,
    ) -> None:
        self._cfg = settings or get_settings()
        self._embedder = embedder or get_cluster_embedder(self._cfg)
        self._tokenizer = tokenizer
        self._dim = self._cfg.dense_dim
        self._dim_low = self._cfg.dense_dim_low
        self._doc_prefix = self._cfg.document_prefix
        # `(leading, trailing)` special-token vectors the endpoint adds. Resolved from the model
        # declaration, EXCEPT for the stub, whose documented contract is `n_api == n_local` (the
        # stub embedder emits no special vector — see `cluster_embedder.StubTokenizer`).
        # ⚠️ Keyed on the EMBEDDER ACTUALLY IN USE, not `cfg.use_stub_embedder`: the flag is a
        # global that a unit test holds True while passing a real (mock-transport) embedder, and
        # the layout is a property of the embedder, not of the process — keying off the flag made
        # 14 tests raise on the count mismatch (§I78).
        if specials is not None:
            self._specials = specials
        elif isinstance(self._embedder, StubClusterEmbedder):
            self._specials = (0, 0)
        else:
            self._specials = declared_specials(self._cfg.dense_model)

    @property
    def specials(self) -> tuple[int, int]:
        """``(leading, trailing)`` — the layout every pooled child vector depends on."""
        return self._specials

    @property
    def document_prefix(self) -> str:
        return self._doc_prefix

    def _prefixed(self, text: str) -> str:
        """The exact string the endpoint is handed — the prefix must be in BOTH places.

        ⚠️ The embedder applies ``cfg.document_prefix`` on its passage paths, so the tokenizer here
        must see the same prefixed string or every child's span is short by the prefix's token
        count (plan §1 trap 2 — the silent one).
        """
        return self._doc_prefix + text

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
        """Character spans of the **prefixed** parent's tokens, plain tokenization.

        ⚠️ ``self._prefixed(text)``, not ``text``. The endpoint is handed the prefixed string, so
        tokenizing the raw text here would make every child's span short by the prefix's token
        count — a mis-pooled vector with no warning (plan §1 trap 2). The caller translates each
        child's span by ``len(self._doc_prefix)`` into these coordinates.
        """
        enc = self._get_tokenizer()(
            self._prefixed(text), add_special_tokens=False, return_offsets_mapping=True
        )
        return [(int(s), int(e)) for s, e in enc["offset_mapping"]]

    @staticmethod
    def _content_tokens(
        matrix: np.ndarray,
        n_local: int,
        parent_id: int,
        dim: int,
        specials: tuple[int, int] = (0, 1),
    ) -> np.ndarray:
        """Drop the endpoint's special-token vectors; refuse any layout it cannot explain.

        ``specials`` is ``(leading, trailing)`` — **where** the wrapper sits, not just how many.
        The old signature hard-coded the Qwen3 contract (``n_local + 1``, trailing); nomic adds two,
        both TRAILING, so ``matrix[:-1]`` would keep a special vector and shift every span by one
        token while the counts still looked plausible (§I77; plan trap 3).
        """
        if matrix.ndim != 2 or matrix.shape[1] != dim:
            raise ValueError(
                f"Per-token matrix for parent {parent_id} has shape {matrix.shape}, "
                f"expected (n_tokens, {dim})"
            )
        leading, trailing = specials
        n_api = matrix.shape[0]
        if n_api == n_local + leading + trailing:
            end = n_api - trailing if trailing else n_api
            return matrix[leading:end]
        raise ValueError(
            f"Token alignment broken for parent {parent_id}: the local tokenizer produced "
            f"{n_local} tokens and the endpoint returned {n_api} vectors, but this model's "
            f"declared layout is {leading} leading + {trailing} trailing specials (so "
            f"{n_local + leading + trailing} were expected). A count this module cannot explain "
            f"would shift every child's pooling window, so nothing was pooled — re-probe the "
            f"layout (logs/p1/step10/probe_nomic_alignment.py) and update _DECLARED_SPECIALS."
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
        tokens = self._content_tokens(
            matrix, len(offsets), parent.parent_id, self._dim, self._specials
        )

        # ⚠️ `offsets` are in the PREFIXED string's coordinates (the endpoint was handed
        # `prefix + parent.text`), while a child's `char_start`/`char_end` index the RAW parent
        # text. Translating by `len(prefix)` puts the two in one coordinate system; skipping it
        # pools every child from the wrong tokens, and **nothing raises** (plan §1 trap 2).
        shift = len(self._doc_prefix)

        out: list[EnrichedChunk] = []
        for child in children:
            pooled, span = self._pool(
                tokens, offsets, (child.char_start + shift, child.char_end + shift),
                parent.parent_id,
            )
            out.append(self._finish(pooled, child, span, late=True))
        logger.debug(
            "Late-chunked parent {} → {} children ({} tokens, {} vectors)",
            parent.parent_id, len(out), len(offsets), matrix.shape[0],
        )
        return out

    def probe_alignment(self, text: str, sentinel: str = " sentinel") -> dict:
        """Measure the live endpoint's special-token layout and CHECK it against the declaration.

        Two calls — the text, and the same text plus a sentinel word. Left-to-right tokenization
        makes the first text's content tokens a **prefix** of the second's, so the responses align
        at the number of LEADING special vectors:

            leading  = argmin_o max|M1[o:o+n1] - M2[o:o+n1]|
            trailing = len(M1) - n1 - leading

        ⚠️ This is the **guard**, not the source of truth. ``_DECLARED_SPECIALS`` declares and this
        asserts: a server-side layout change is loud here instead of silently shifting every
        child's pooling window.

        The match is tolerant because the right offset is an **exact** zero only for a CAUSAL model.
        Measured 2026-10-25 (``probe_nomic_alignment.json``): both models' per-token path IS
        bit-reproducible (repeated identical calls differ by 0.0), but Qwen3 — causal, so appending
        a sentinel cannot change an earlier token's hidden state — matches at 0.0, while nomic is
        bidirectional and the sentinel does move its earlier vectors (1.18 at the correct offset,
        against 9.3 for the runner-up: a 7.9x margin). So the argmin is what decides, and the
        runner-up margin is returned so an alignment that is only marginally better than its
        neighbours is visible rather than assumed.
        """
        tok = self._get_tokenizer()
        t1, t2 = text, text + sentinel
        n1 = len(tok(self._prefixed(t1), add_special_tokens=False)["input_ids"])
        m1 = np.asarray(self._embedder.embed_documents_tokens([t1])[0], dtype=np.float64)
        m2 = np.asarray(self._embedder.embed_documents_tokens([t2])[0], dtype=np.float64)

        # ⚠️ Compare each candidate block against ``m1[:n1]`` — the CONTENT vectors — not against
        # ``m1``, which carries the specials too. Comparing to ``m1`` can never match (the shapes
        # differ by exactly the specials), so the guard would raise for every model, including the
        # ones it is meant to confirm.
        profile: list[dict] = []
        for offset in range(0, m2.shape[0] - n1 + 1):
            block = m2[offset:offset + n1]
            if block.shape != m1[:n1].shape:
                continue
            profile.append({"leading": offset,
                            "max_abs_diff": float(np.max(np.abs(m1[:n1] - block)))})
        if not profile:
            raise RuntimeError(
                f"could not align the endpoint's two responses for {self.model_name!r}: "
                f"{m1.shape[0]} vectors for {n1} local tokens, and no offset matched. The "
                f"special-token layout is NOT established, so late chunking cannot be trusted."
            )
        best = min(profile, key=lambda r: r["max_abs_diff"])
        leading = int(best["leading"])
        trailing = int(m1.shape[0]) - n1 - leading
        # The margin, not the residual, is the signal: a bidirectional model's correct offset is
        # small but NOT zero (the sentinel moves earlier tokens' hidden states), so an alignment
        # only marginally better than its neighbours is not established.
        others = sorted(r["max_abs_diff"] for r in profile if r["leading"] != leading)
        margin = (round(others[0] / best["max_abs_diff"], 3)
                  if others and best["max_abs_diff"] > 0 else None)
        measured = (leading, trailing)
        if measured != self._specials:
            raise RuntimeError(
                f"the endpoint's special-token layout for {self.model_name!r} is measured as "
                f"{measured} (leading, trailing) but _DECLARED_SPECIALS says {self._specials}. "
                f"Every child's pooling window would shift by the difference. Re-probe and update "
                f"the declaration before embedding anything."
            )
        return {"leading": leading, "trailing": trailing, "n_local": n1,
                "n_api": int(m1.shape[0]), "match_max_abs_diff": best["max_abs_diff"],
                "runner_up_margin_x": margin, "profile": profile}

    def embed_children(
        self,
        parents: list[ParentChunk],
        children: list[TextChunk],
        cache=None,
    ) -> list[EnrichedChunk]:
        """Enrich a whole document's children, grouped by parent, in document order.

        Parents are embedded **concurrently** (``late_chunk_workers``). This is the ingest's
        dominant cost — one per-token POST per parent, each carrying ~5 s of fixed overhead
        on top of the transfer — so it is ~100% time spent waiting on the cluster. That makes
        **threads** the right tool: the GIL is released for the duration of each request, so
        the workers overlap the waiting rather than the arithmetic. Processes would only add
        pickling of large float matrices for no gain.

        Results are reassembled in **parent order**, so the document order the store and the
        tests rely on is identical to the serial path — concurrency changes the wall clock,
        not the output.

        ``cache`` is an optional :class:`~src.pdf_ingestion.embed_cache.EmbeddingCache`. When
        given, a parent whose vectors are already checkpointed is rebuilt from disk instead of
        re-embedded, and each freshly embedded parent is written back. That is what makes an
        aborted run resumable: Step 8 attempt 3 finished 339 of 341 parents and lost all of it
        (IMPROVEMENTS.md §I19).
        """
        by_parent: dict[int, list[TextChunk]] = {}
        for child in children:
            by_parent.setdefault(child.parent_id, []).append(child)

        known = {p.parent_id for p in parents}
        orphans = sorted(pid for pid in by_parent if pid not in known)
        if orphans:
            raise ValueError(f"Children reference parents that do not exist: {orphans}")

        workers = max(1, int(getattr(self._cfg, "late_chunk_workers", 1) or 1))
        if workers == 1 or len(parents) <= 1:
            out: list[EnrichedChunk] = []
            for parent in parents:
                out.extend(self._enrich_one(parent, by_parent.get(parent.parent_id, []), cache))
        else:
            out = self._embed_parents_concurrently(parents, by_parent, workers, cache)

        if cache is not None:
            logger.info("Late-chunk cache: {}", cache.summary())
        logger.success("Enriched {} children from {} parents", len(out), len(parents))
        return out

    def _enrich_one(self, parent: ParentChunk, kids: list[TextChunk], cache) -> list[EnrichedChunk]:
        """One parent's children: from the checkpoint if possible, else embedded and cached."""
        if cache is not None:
            hit = cache.get(parent.parent_id)
            if hit is not None:
                rebuilt = hit.rebuild(kids)
                if rebuilt is not None:
                    # Counted HERE, not in `get`: only the caller knows the entry validated. The
                    # old order let attempt 5 report `341 hits` while rejecting all 341 (§I19a).
                    cache.record_hit()
                    return rebuilt
                # Loaded under the current digest scheme but the children no longer line up — a real
                # content change, and never a silent mis-join. A *scheme* change cannot reach this
                # branch: `get` reports it as a miss, which is precisely what attempt 5 was.
                cache.record_rejected()
                logger.warning(
                    "Late-chunk cache: entry for parent {} does not match the current children "
                    "— re-embedding", parent.parent_id,
                )
        out = self.embed_parent(parent, kids)
        if cache is not None and out:
            cache.put(parent.parent_id, out)
        return out

    def _embed_parents_concurrently(
        self,
        parents: list[ParentChunk],
        by_parent: dict[int, list[TextChunk]],
        workers: int,
        cache=None,
    ) -> list[EnrichedChunk]:
        """``embed_parent`` over a thread pool, flattened back into parent order.

        Keyed by position, not by ``parent_id``, so a repeated id cannot collapse two parents
        into one slot. ``future.result()`` re-raises, so a parent that fails after its retries
        abort the ingest loudly instead of silently shrinking the document.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Resolve the tokenizer BEFORE the pool starts. `_get_tokenizer` lazy-loads with a bare
        # `if self._tokenizer is None`, which is not atomic: without this, the first N workers
        # can all pass the check and each build the model concurrently — wasteful, and it
        # contends on the HuggingFace cache lock. (Encoding is safe from several threads; the
        # unsynchronised *load* is the hazard, so warming it here is the whole fix.) It is also
        # the slowest part of the first parent, so doing it once up front is strictly better.
        self._get_tokenizer()

        logger.info("Late-chunking {} parents with {} workers", len(parents), workers)
        results: dict[int, list[EnrichedChunk]] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    self._enrich_one, parent, by_parent.get(parent.parent_id, []), cache
                ): idx
                for idx, parent in enumerate(parents)
            }
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()

        return [ec for idx in range(len(parents)) for ec in results[idx]]

    def embed_query(self, text: str) -> np.ndarray:
        """Query vector from the same model.

        No instruction is added here: ``ClusterDenseEmbedder.embed_query`` already prepends
        ``query_instruction`` (and the index side must match the query side, not duplicate it).
        """
        return self._embedder.embed_query(text)

    # -- Isolation twin (late_chunk_enabled=False, and the no-token fallback) ----

    def embed_isolated(self, chunk: TextChunk) -> EnrichedChunk:
        """The twin: the same child embedded alone, with no parent context (the E3 control)."""
        return self.embed_isolated_batch([chunk])[0]

    def embed_isolated_batch(self, chunks: list[TextChunk]) -> list[EnrichedChunk]:
        """The isolation twin, **batched**: pooled over each chunk's own ``text``, no parent context.

        ⚠️ This IS the *pooled* construction — ``ClusterDenseEmbedder.embed_documents`` applies the
        document-side prefix (``search_document: `` for nomic) and L2-normalises, so the vector this
        returns is the same object §I63/§I87 measured as ``nomic_pooled``: whole-chunk text,
        prefixed, pooled. It is the drop-late-chunking treatment (§I88) — the re-embed script's
        ``--pooled`` mode calls this instead of :meth:`embed_parent`.

        ⚠️ Batching changes only the request count, never a vector: the endpoint returns one pooled
        vector per input, independent of how the inputs are grouped. The write's acceptance check
        (stored vs a fresh pooled call at cos 1.0) is what holds that claim, not this docstring.
        """
        if not chunks:
            return []
        vecs = self._embedder.embed_documents([c.text for c in chunks])
        return [self._finish(np.asarray(v, dtype=np.float32), c, (0, 0), late=False)
                for c, v in zip(chunks, vecs)]
