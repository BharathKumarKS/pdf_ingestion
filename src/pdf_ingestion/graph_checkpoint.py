"""Interval checkpoint + resume for Phase 3 concept extraction (IMPROVEMENTS.md §I23).

**The problem this solves.** `GraphBuilder.build_graph` extracts concepts for **every** chunk
in memory before writing anything, so an abort at any point discards every completed extraction.
The 2026-10-19 build of doc `7ba61432` measured **16 h 25 m** against a 2 h estimate, holding up
to 2,000 chunks of work in RAM with no way to persist it (§I23 defect 1). Retry and the
per-request deadline (`src/core/llm.py`, §I24) reduce the *probability* of an abort; only a
checkpoint reduces its *cost* — the same reasoning as the card phase's checkpoint (§I27).

**Why a side-car and not incremental graph writes.** Memgraph is the single write point and it
stays that way. A partially-written concept graph is indistinguishable from a complete one to
`graph_search`, to the §I21 density check and to any node count taken in Memgraph — exactly the
"an artifact existing is not the item done" failure (§I25's class). So the checkpoint holds the
*extraction output* beside the graph, as `embed_cache` does for the late-chunk phase (§I19).

**Key, and why it carries the prompt digest.** The file is named by
``(document_id, model, prompt digest)`` — the identity of the *run*, not of its inputs. The
prompt digest matters because `_CONCEPT_PROMPT` is a code constant: changing it changes what the
extraction means, and a checkpoint written under the old prompt must not be silently reused. An
entry is used only if its ``chunk_id`` is present in the chunk list being built **now**, so a
corpus change (a re-ingest, the §I21 content filter, a changed chunk budget) needs no detection
to be safe — chunk ids are ``uuid4()`` per ingest, so entries for a changed corpus match nothing
and are dropped.

**A chunk whose extraction FAILED is not treated as done** — it is re-attempted on resume. This
is the whole point: the 2026-10-19 build had **44 failures reported as "0 failed"** (§I23), and a
checkpoint that recorded those as complete would bake the loss in permanently. `ok=False` covers
the LLM call erroring, returning empty, or returning unusable JSON; a chunk that genuinely has no
concepts returns valid JSON with an empty list and ``ok=True``, and IS checkpointed.

**Crash safety.** Append-only JSONL, `flush()` + `fsync()` on every write. A crash can tear at
most the final line; the loader stops at the last line that parses and truncates the file back to
it, so a torn record costs one chunk, never the file.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from loguru import logger

# Bump when the checkpoint FORMAT or the extraction serialisation changes. Config cannot capture
# a code change, and a stale entry read back after one would be silently wrong.
_SCHEMA_VERSION = 1

# The digest scheme for the run key, stored in the header and checked on read (§I19a).
_DIGEST_SCHEME = "sha256:16"


def prompt_digest(prompt_template: str) -> str:
    """Digest of the extraction prompt, so a prompt change invalidates the checkpoint.

    The prompt is a code constant, not config, so nothing else would notice it moving — and a
    resume under a changed prompt would mix two different extraction meanings in one graph.
    """
    return hashlib.sha256(prompt_template.encode()).hexdigest()[:16]


def run_key(document_id: str, model: str, prompt_digest_: str) -> str:
    """Identity of the (document, model, prompt) a checkpoint belongs to.

    Deliberately does **not** include the chunk list — entries are validated against the current
    chunk list on read instead (see the module docstring).
    """
    h = hashlib.sha256()
    h.update(f"schema={_SCHEMA_VERSION}\x00scheme={_DIGEST_SCHEME}".encode())
    h.update(f"\x00doc={document_id}\x00model={model}\x00prompt={prompt_digest_}".encode())
    return h.hexdigest()[:16]


@dataclass
class GraphCheckpoint:
    """Append-only JSONL of completed concept extractions for one Phase 3 build."""

    path: Path
    document_id: str
    chunk_ids: set[str]
    digest: str
    model: str
    prompt_digest: str

    # Filled by _load(): chunk_ids already extracted cleanly, and what they produced.
    done: set[str] = field(default_factory=set)
    extractions: dict[str, dict] = field(default_factory=dict)
    resumed_chunks: int = 0
    retried_chunks: int = 0
    ignored_chunks: int = 0

    _fh: IO[str] | None = None
    _since_flush: int = 0
    _last_flush: float = 0.0

    # -- construction ---------------------------------------------------------

    @classmethod
    def open(
        cls,
        directory: str | Path,
        document_id: str,
        chunk_ids: list[str],
        model: str,
        prompt_digest_: str,
        fresh: bool = False,
    ) -> GraphCheckpoint:
        """Open (or create) the checkpoint for this build, loading whatever is already done.

        ``fresh=True`` deletes any existing file for this key first, so a re-run that wants no
        resume cannot inherit it.
        """
        digest = run_key(document_id, model, prompt_digest_)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{document_id[:8]}__{digest}.jsonl"
        if fresh and path.exists():
            logger.warning("Graph checkpoint: discarding {} (fresh run requested)", path)
            path.unlink()
        cp = cls(path=path, document_id=document_id, chunk_ids=set(chunk_ids),
                 digest=digest, model=model, prompt_digest=prompt_digest_)
        cp._load()
        return cp

    # -- load -----------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("Graph checkpoint: new file {}", self.path)
            return

        good_bytes = 0
        header: dict | None = None
        entries: list[dict] = []
        torn = False
        try:
            with self.path.open("rb") as fh:
                for raw in fh:
                    try:
                        rec = json.loads(raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        torn = True
                        break
                    if rec.get("kind") == "header":
                        header = rec
                    elif rec.get("kind") == "chunk":
                        entries.append(rec)
                    else:
                        torn = True
                        break
                    good_bytes += len(raw)
        except OSError as exc:
            logger.warning("Graph checkpoint unreadable ({}): {} — starting fresh", self.path, exc)
            return

        # The header is the identity check (§I19a): a file that does not match this run's
        # (document, key, model, prompt, schema) is not resumed, whatever its name says.
        if header is None:
            logger.warning("Graph checkpoint {} has no header — ignoring it", self.path)
            return
        if (header.get("document_id") != self.document_id
                or header.get("digest") != self.digest
                or header.get("model") != self.model
                or header.get("prompt_digest") != self.prompt_digest
                or header.get("schema") != _SCHEMA_VERSION
                or header.get("digest_scheme") != _DIGEST_SCHEME):
            logger.warning(
                "Graph checkpoint {} does not match this build (doc/digest/model/prompt/schema) "
                "— ignoring it and starting a fresh file", self.path,
            )
            return

        for rec in entries:
            cid = rec.get("chunk_id")
            if not cid or cid not in self.chunk_ids:
                # Written for a chunk that is not in the chunk set being built now (a re-ingest,
                # the §I21 filter, a probe over a subset): it must not be counted as done.
                self.ignored_chunks += 1
                continue
            if not rec.get("ok", False):
                # NOT "done": an extraction that failed gets another chance (§I23).
                self.retried_chunks += 1
                continue
            if cid in self.done:
                continue
            self.done.add(cid)
            self.extractions[cid] = {
                "concepts": rec.get("concepts") or [],
                "prerequisites": rec.get("prerequisites") or [],
                "ok": True,
                "error": None,
            }

        self.resumed_chunks = len(self.done)

        if torn:
            # Rewind to the last complete record so the next append is not preceded by a fragment.
            logger.warning(
                "Graph checkpoint {} ends mid-record — truncating to {} bytes (one chunk lost)",
                self.path, good_bytes,
            )
            with self.path.open("r+b") as fh:
                fh.truncate(good_bytes)

        if self.resumed_chunks or self.retried_chunks or self.ignored_chunks:
            logger.info(
                "Graph checkpoint {}: {} of {} chunks already extracted — {} to retry after a "
                "failed extraction, {} for chunks not in this build's chunk set (dropped)",
                self.path.name, self.resumed_chunks, len(self.chunk_ids),
                self.retried_chunks, self.ignored_chunks,
            )

    # -- write ----------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._fh is not None:
            return
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        self._fh = self.path.open("a", encoding="utf-8")
        if is_new:
            self._write({
                "kind": "header",
                "schema": _SCHEMA_VERSION,
                "digest_scheme": _DIGEST_SCHEME,
                "document_id": self.document_id,
                "digest": self.digest,
                "model": self.model,
                "prompt_digest": self.prompt_digest,
                "n_chunks": len(self.chunk_ids),
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

    def _write(self, rec: dict) -> None:
        assert self._fh is not None
        self._fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def record(self, chunk_id: str, chunk_index: int, extraction: dict) -> None:
        """Checkpoint one chunk's extraction, whether it succeeded or failed.

        A failed extraction is written with ``ok: false`` so it is re-attempted on resume rather
        than counted as done.
        """
        self._ensure_open()
        self._write({
            "kind": "chunk",
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "ok": bool(extraction.get("ok", False)),
            "error": extraction.get("error"),
            "concepts": extraction.get("concepts") or [],
            "prerequisites": extraction.get("prerequisites") or [],
        })
        self._since_flush += 1
        self._last_flush = time.monotonic()

    def due(self, every: int, every_seconds: float) -> bool:
        """True when enough chunks or enough wall-clock time has passed to justify a report.

        The clock half matters because chunk cost is not uniform: this workload measured ~10 s per
        call healthy and ~80 s per call under shared-cluster contention (§I23), so a pure
        chunk-count interval can be an hour of silence.
        """
        if self._since_flush >= max(1, every):
            return True
        if self._last_flush and (time.monotonic() - self._last_flush) >= every_seconds:
            return True
        return False

    def note_flushed(self) -> None:
        self._since_flush = 0
        self._last_flush = time.monotonic()

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None
