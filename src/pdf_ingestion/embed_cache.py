"""Side-car resume cache for the late-chunk embedding phase (IMPROVEMENTS.md §I19).

**The problem this solves.** The ingest computes every parent's embeddings in memory and writes
**once**, at the end, in `DocumentStore.save_document`. There is no resume. Step 8's three runs
each discarded a nearly-complete document — 86, 53.6 and **63.8 minutes**, the last after
**339 of 341** parents had finished — because one request to a flaky endpoint exhausted its
retries. Retry and the per-request deadline (`cluster_embedder`) reduce the *probability* of an
abort; only a checkpoint reduces its *cost*.

**Why a side-car and not incremental writes.** Writing to Qdrant/SQLite per parent batch would
make a partially-written collection look complete to the funnel, the eval and the UI — a worse
failure than a clean abort. So `save_document` stays the single atomic write point and the
checkpoint lives beside it: for each parent, the pooled child vectors it produced.

**Key.** A cache entry is valid only for the exact (document, chunking config, model) triple that
produced it, so the directory is named by a fingerprint over the PDF's bytes and the knobs that
change chunk boundaries or vectors. Change `parent_max_tokens` and the old entries are simply not
found — they are never silently reused. (The stale directory is left on disk; `prune()` removes
fingerprints other than the current one.)

**Crash safety.** One `.npz` per parent, written to a temp file and `os.replace`d into place, so a
crash mid-write can only lose the parent being written, never corrupt an existing entry. A parent
that fails to load is treated as a miss, not an error — the worst case is re-embedding it.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module import-light
    from src.pdf_ingestion.chunker import TextChunk
    from src.pdf_ingestion.late_chunk_embedder import EnrichedChunk

# The config fields that change chunk boundaries or the vectors themselves. Anything here
# invalidates the cache; anything not here must not, or a stale entry could be reused silently.
_FINGERPRINT_FIELDS = (
    "dense_model",
    "dense_dim",
    "dense_dim_low",
    "parent_max_tokens",
    "semantic_threshold",
    "min_chunk_tokens",
    "late_chunk_enabled",
)


def fingerprint(pdf_path: str | Path, cfg) -> str:
    """Identity of the (document, chunking config, model) triple a cache entry is valid for.

    The PDF is hashed by content, not by name — re-exporting the same file under a new name must
    not be able to reuse entries from a different document.
    """
    h = hashlib.sha256()
    h.update(Path(pdf_path).read_bytes())
    for field in _FINGERPRINT_FIELDS:
        h.update(f"\x00{field}={getattr(cfg, field, None)}".encode())
    return h.hexdigest()[:16]


@dataclass
class CachedParent:
    """One parent's pooled child vectors, as written by a previous run."""

    child_ids: list[str]
    dense_1024: np.ndarray      # (n_children, dense_dim)
    dense_64: np.ndarray        # (n_children, dense_dim_low)
    token_spans: np.ndarray     # (n_children, 2) int32
    late_chunked: np.ndarray    # (n_children,) bool
    model_name: str

    def rebuild(self, children: list[TextChunk]) -> list[EnrichedChunk] | None:
        """Re-attach the cached vectors to ``children``, or ``None`` if they do not line up.

        Returning ``None`` on any mismatch is deliberate: a cache that re-attaches vectors to the
        wrong children would corrupt the index silently, whereas a miss only costs one request.
        The child ids are checked, not just the count, so a re-chunk that happens to produce the
        same number of children is still rejected.
        """
        from src.pdf_ingestion.late_chunk_embedder import EnrichedChunk

        if len(children) != len(self.child_ids):
            return None
        if [c.chunk_id for c in children] != self.child_ids:
            return None
        return [
            EnrichedChunk(
                chunk=child,
                dense_1024=self.dense_1024[i],
                dense_64=self.dense_64[i],
                model_name=self.model_name,
                token_span=(int(self.token_spans[i][0]), int(self.token_spans[i][1])),
                late_chunked=bool(self.late_chunked[i]),
            )
            for i, child in enumerate(children)
        ]


class EmbeddingCache:
    """Per-parent checkpoint of the late-chunk embedding phase."""

    def __init__(self, root: str | Path, key: str) -> None:
        self._dir = Path(root) / key
        self._key = key
        self.hits = 0
        self.misses = 0
        self.writes = 0

    @property
    def directory(self) -> Path:
        return self._dir

    def _path(self, parent_id: int) -> Path:
        return self._dir / f"p{parent_id}.npz"

    def get(self, parent_id: int) -> CachedParent | None:
        """Return the cached entry, or ``None`` on a miss OR an unreadable entry."""
        path = self._path(parent_id)
        if not path.exists():
            self.misses += 1
            return None
        try:
            with np.load(path, allow_pickle=False) as z:
                entry = CachedParent(
                    child_ids=[str(c) for c in z["child_ids"]],
                    dense_1024=z["dense_1024"],
                    dense_64=z["dense_64"],
                    token_spans=z["token_spans"],
                    late_chunked=z["late_chunked"],
                    model_name=str(z["model_name"]),
                )
        except Exception as exc:  # noqa: BLE001 - a bad entry is a miss, never a crash
            logger.warning("Embedding cache: entry {} unreadable ({}) — re-embedding",
                           path.name, type(exc).__name__)
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def put(self, parent_id: int, chunks: list[EnrichedChunk]) -> None:
        """Persist one parent's vectors atomically. Never raises — a cache must not fail a run."""
        if not chunks:
            return
        final = self._path(parent_id)
        tmp = final.with_suffix(".npz.tmp")
        try:
            # mkdir is INSIDE the try on purpose: it is the step most likely to fail (an
            # unwritable root, a file where the directory should be), and `put` promises never to
            # raise — a cache that can abort an ingest is worse than no cache.
            self._dir.mkdir(parents=True, exist_ok=True)
            # Write through an open handle, NOT a path: `np.savez(path)` silently appends ".npz"
            # when the name does not already end in it, so a path ending ".npz.tmp" becomes
            # ".npz.tmp.npz" and the os.replace below fails on a file that was never created.
            # A handle makes numpy write exactly where it is told.
            with open(tmp, "wb") as fh:
                np.savez(
                    fh,
                    child_ids=np.asarray([c.chunk.chunk_id for c in chunks], dtype="U"),
                    dense_1024=np.asarray([c.dense_1024 for c in chunks], dtype=np.float32),
                    dense_64=np.asarray([c.dense_64 for c in chunks], dtype=np.float32),
                    token_spans=np.asarray([c.token_span for c in chunks], dtype=np.int32),
                    late_chunked=np.asarray([c.late_chunked for c in chunks], dtype=bool),
                    model_name=np.asarray(chunks[0].model_name, dtype="U"),
                )
            os.replace(tmp, final)
            self.writes += 1
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.warning("Embedding cache: could not write {} ({}) — continuing uncached",
                           final.name, type(exc).__name__)
            # The cleanup must not be able to raise either — the failure that brought us here is
            # often precisely that the path is not usable, so unlink fails the same way the write
            # did. Suppressing is the point: this handler exists to keep `put` from raising.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def summary(self) -> str:
        return (f"{self.hits} hits / {self.misses} misses / {self.writes} written "
                f"(key {self._key})")

    def prune(self, keep_current: bool = True) -> list[str]:
        """Delete cache directories for other fingerprints. Returns what was removed.

        Not called automatically: a stale directory is harmless (it is simply not looked up) and
        deleting someone else's in-flight run's cache would be worse than leaving a few MB behind.
        """
        removed: list[str] = []
        root = self._dir.parent
        if not root.exists():
            return removed
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if keep_current and child.name == self._key:
                continue
            for f in child.glob("*.npz"):
                f.unlink(missing_ok=True)
            try:
                child.rmdir()
            except OSError:  # pragma: no cover - non-empty for a reason we do not control
                continue
            removed.append(child.name)
        return removed
