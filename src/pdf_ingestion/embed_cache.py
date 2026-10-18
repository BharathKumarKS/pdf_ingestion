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
import threading
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
#
# `chunk_size` / `chunk_overlap` are included although they measured INERT: varying chunk_size
# across 128/256/512/1024 on an 8,600-character parent produced byte-identical children (the
# semantic segmentation, driven by `semantic_threshold`, decides the boundaries; 0.8 -> 2 children
# and 0.3 -> 39). They are here as cheap insurance against that changing, and that is recorded so
# the inclusion is honest rather than cargo-cult.
_FINGERPRINT_FIELDS = (
    "dense_model",
    "dense_dim",
    "dense_dim_low",
    "parent_max_tokens",
    "semantic_threshold",
    "min_chunk_tokens",
    "chunk_size",
    "chunk_overlap",
    "late_chunk_enabled",
)

# Bump this whenever the CHUNKING or EMBEDDING CODE changes in a way that alters the children or
# the vectors, even if no config value does. Config fields cannot capture a code change, and a
# stale entry reused after one would be silently wrong — the exact class of bug this module exists
# to avoid. Not automatic: hashing the module source would make every cache entry invalid on every
# refactor, which is worse than the discipline of bumping this.
_CACHE_SCHEMA_VERSION = 1


def fingerprint(pdf_path: str | Path, cfg) -> str:
    """Identity of the (document, chunking config, model) triple a cache entry is valid for.

    The PDF is hashed by content, not by name — re-exporting the same file under a new name must
    not be able to reuse entries from a different document.
    """
    h = hashlib.sha256()
    h.update(Path(pdf_path).read_bytes())
    h.update(f"\x00schema={_CACHE_SCHEMA_VERSION}".encode())
    for field in _FINGERPRINT_FIELDS:
        h.update(f"\x00{field}={getattr(cfg, field, None)}".encode())
    return h.hexdigest()[:16]


def _text_sha(text: str) -> str:
    """Content digest of a child's text — the cache's real identity check.

    128 bits, not the 64 a 16-character prefix would give. The cost is zero and the alternative is
    a birthday-bound collision argument nobody should have to make about their cache.
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:32]


@dataclass
class CachedParent:
    """One parent's pooled child vectors, as written by a previous run."""

    text_sha: np.ndarray        # (n_children,) content digest of each child's TEXT
    char_spans: np.ndarray      # (n_children, 2) int32 char_start/char_end
    dense_1024: np.ndarray      # (n_children, dense_dim)
    dense_64: np.ndarray        # (n_children, dense_dim_low)
    token_spans: np.ndarray     # (n_children, 2) int32
    late_chunked: np.ndarray    # (n_children,) bool
    model_name: str

    def rebuild(self, children: list[TextChunk]) -> list[EnrichedChunk] | None:
        """Re-attach the cached vectors to ``children``, or ``None`` if they do not line up.

        **Validated on CONTENT, not identity.** The first version of this keyed on
        ``chunk_id`` — which is ``str(uuid.uuid4())``, minted fresh on every run, so the ids could
        never match across runs and the cache would have silently never hit in production. (It
        passed its tests because they reused the same child objects, so the uuids happened to
        agree.) What IS stable across runs with the same chunking config is the child's **text and
        character span**, and those are what a hit is checked against.

        Returning ``None`` on any mismatch is deliberate: a cache that re-attached vectors to the
        wrong children would corrupt the index silently, whereas a miss only costs one request.
        """
        from src.pdf_ingestion.late_chunk_embedder import EnrichedChunk

        if len(children) != len(self.text_sha):
            return None
        for i, child in enumerate(children):
            if _text_sha(child.text) != str(self.text_sha[i]):
                return None
            if (int(self.char_spans[i][0]), int(self.char_spans[i][1])) != (
                child.char_start, child.char_end
            ):
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
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.writes = 0

    def _bump(self, field: str) -> None:
        """Increment a counter under a lock.

        `get`/`put` are called from up to `late_chunk_workers` threads on one shared instance, and
        `self.hits += 1` is a read-modify-write. The lock is cheap insurance, and it is stated as
        insurance rather than as a fix for an observed bug: measured directly, an UNLOCKED `+= 1`
        on an int attribute lost zero increments at 8x25, 16x150 and 32x300 threads x iterations
        with `sys.setswitchinterval(1e-6)` — CPython's GIL plus the specializing interpreter make
        the sequence complete inside a time slice for this pattern. It becomes genuinely racy on a
        free-threaded build, which is reason enough to keep it. See the matching test.
        """
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    @property
    def directory(self) -> Path:
        return self._dir

    def _path(self, parent_id: int) -> Path:
        return self._dir / f"p{parent_id}.npz"

    def get(self, parent_id: int) -> CachedParent | None:
        """Return the cached entry, or ``None`` on a miss OR an unreadable entry."""
        path = self._path(parent_id)
        if not path.exists():
            self._bump("misses")
            return None
        try:
            with np.load(path, allow_pickle=False) as z:
                entry = CachedParent(
                    text_sha=z["text_sha"],
                    char_spans=z["char_spans"],
                    dense_1024=z["dense_1024"],
                    dense_64=z["dense_64"],
                    token_spans=z["token_spans"],
                    late_chunked=z["late_chunked"],
                    model_name=str(z["model_name"]),
                )
        except Exception as exc:  # noqa: BLE001 - a bad entry is a miss, never a crash
            logger.warning("Embedding cache: entry {} unreadable ({}) — re-embedding",
                           path.name, type(exc).__name__)
            self._bump("misses")
            return None
        self._bump("hits")
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
                    text_sha=np.asarray([_text_sha(c.chunk.text) for c in chunks], dtype="U"),
                    char_spans=np.asarray(
                        [(c.chunk.char_start, c.chunk.char_end) for c in chunks], dtype=np.int32
                    ),
                    dense_1024=np.asarray([c.dense_1024 for c in chunks], dtype=np.float32),
                    dense_64=np.asarray([c.dense_64 for c in chunks], dtype=np.float32),
                    token_spans=np.asarray([c.token_span for c in chunks], dtype=np.int32),
                    late_chunked=np.asarray([c.late_chunked for c in chunks], dtype=bool),
                    model_name=np.asarray(chunks[0].model_name, dtype="U"),
                )
            os.replace(tmp, final)
            self._bump("writes")
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
