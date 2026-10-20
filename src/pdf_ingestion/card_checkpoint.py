"""Interval checkpoint + resume for card generation (IMPROVEMENTS.md §I27).

**The problem this solves.** `generate_cards_for_chunks` holds every card in memory and
`DocumentStore.save_cards` writes **once**, after the last chunk. There is no resume and no
cards-only rebuild flag, so an abort at chunk 3,700 of 3,791 discards the whole card run — and
the measured healthy rate for this workload is ~10 s/chunk, i.e. **~10.6 hours** at
`CARD_GEN_WORKERS=1` (§I26). Retry and the per-request deadline (`src/core/llm.py`, §I24) reduce
the *probability* of an abort; only a checkpoint reduces its *cost*.

**Why a side-car and not incremental SQLite writes.** `save_cards` calls `_deactivate_cards()`
first — every call deactivates the document's existing cards before inserting. Saving every N
chunks would therefore **delete the previous interval's cards**, leaving only the last batch. Even
with that fixed, a partially-written card set in the DB is indistinguishable from a complete one
to `evaluate_rag.py`, the UI and the §A3 volume count: exactly the "an artifact existing is not the
item done" failure (§I25's class). So the single write point stays where it is, and the checkpoint
lives beside it, as `embed_cache` does for the late-chunk phase (§I19).

**Key, and why it is not the chunk list.** The file is named by
``(document_id, card types, model)`` — the identity of the *run*, not of its inputs. An entry is
used only if its ``chunk_id`` is present in the chunk list being generated **now**, so a corpus
change (a re-ingest, a different content filter, a changed chunk budget) does not have to be
detected to be safe: chunk ids are ``uuid4()`` per ingest, so entries for a changed corpus simply
do not match anything and the cards they hold are dropped rather than written. Keying the *file* on
the full sorted chunk list was rejected as brittle in the other direction — any knob that changed
the filtered chunk set would make the previous 10.6 h unfindable rather than partially reusable.

The digest scheme is written **into** the header and checked **on read**, per §I19a: a change to
the identity function must show up as an honest miss, not as a file that loads and is wrong.

**Crash safety.** Append-only JSONL, `flush()` + `fsync()` on every checkpoint write. A crash can
therefore tear at most the final line; the loader stops at the last line that parses and truncates
the file back to it, so a torn record costs one chunk, never the file.

**A chunk that had a failed card type is not treated as done** — it is re-attempted on resume.
Without that, a run aborted during an endpoint outage would resume having "already completed" the
chunks whose every card call timed out, and §I25's swallow would be baked into the checkpoint.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from loguru import logger

# Bump when the checkpoint FORMAT or the card serialisation changes. Config cannot capture a code
# change, and a stale entry read back after one would be silently wrong.
_SCHEMA_VERSION = 1

# The digest scheme for the run key, stored in the header and checked on read (§I19a).
_DIGEST_SCHEME = "sha256:16"


def run_key(document_id: str, card_types: list[str], model: str) -> str:
    """Identity of the (document, card types, model) a checkpoint belongs to.

    Deliberately does **not** include the chunk list — see the module docstring. Entries are
    validated against the current chunk list on read instead.
    """
    h = hashlib.sha256()
    h.update(f"schema={_SCHEMA_VERSION}\x00scheme={_DIGEST_SCHEME}".encode())
    h.update(f"\x00doc={document_id}\x00model={model}".encode())
    h.update(f"\x00types={','.join(sorted(card_types))}".encode())
    return h.hexdigest()[:16]


@dataclass
class CardCheckpoint:
    """Append-only JSONL of completed chunks for one card-generation run."""

    path: Path
    document_id: str
    chunk_ids: set[str]
    digest: str
    model: str

    # Filled by load(): chunk_ids already completed cleanly, and the cards they produced.
    done: set[str] = field(default_factory=set)
    cards: list[dict] = field(default_factory=list)
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
        card_types: list[str],
        model: str,
        fresh: bool = False,
    ) -> CardCheckpoint:
        """Open (or create) the checkpoint for this run, loading whatever is already done.

        ``fresh=True`` deletes any existing file for this key first, so a re-run that wants no
        resume cannot inherit it.
        """
        digest = run_key(document_id, card_types, model)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{document_id[:8]}__{digest}.jsonl"
        if fresh and path.exists():
            logger.warning("Card checkpoint: discarding {} (fresh run requested)", path)
            path.unlink()
        cp = cls(path=path, document_id=document_id, chunk_ids=set(chunk_ids),
                 digest=digest, model=model)
        cp._load()
        return cp

    # -- load -----------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("Card checkpoint: new file {}", self.path)
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
            logger.warning("Card checkpoint unreadable ({}): {} — starting fresh", self.path, exc)
            return

        # The header is the identity check (§I19a): a file that does not match this run's
        # (document, key, model, schema) is not resumed, whatever its name says.
        if header is None:
            logger.warning("Card checkpoint {} has no header — ignoring it", self.path)
            return
        if (header.get("document_id") != self.document_id
                or header.get("digest") != self.digest
                or header.get("model") != self.model
                or header.get("schema") != _SCHEMA_VERSION
                or header.get("digest_scheme") != _DIGEST_SCHEME):
            logger.warning(
                "Card checkpoint {} does not match this run (doc/digest/model/schema) — "
                "ignoring it and starting a fresh file", self.path,
            )
            return

        for rec in entries:
            cid = rec.get("chunk_id")
            if not cid or cid not in self.chunk_ids:
                # Written for a chunk that is not in the chunk set being generated now (a
                # re-ingest, a narrower content filter, a probe over a subset): its cards must
                # not be saved, and it must not be counted as done.
                self.ignored_chunks += 1
                continue
            if rec.get("failed_types"):
                # Not "done": a chunk whose card calls failed gets another chance (§I25).
                self.retried_chunks += 1
                continue
            if cid in self.done:
                continue
            self.done.add(cid)
            self.cards.extend(rec.get("cards") or [])

        self.resumed_chunks = len(self.done)

        if torn:
            # Rewind to the last complete record so the next append is not preceded by a fragment.
            logger.warning(
                "Card checkpoint {} ends mid-record — truncating to {} bytes (one chunk lost)",
                self.path, good_bytes,
            )
            with self.path.open("r+b") as fh:
                fh.truncate(good_bytes)

        if self.resumed_chunks or self.retried_chunks or self.ignored_chunks:
            logger.info(
                "Card checkpoint {}: {} of {} chunks already done ({} cards) — {} with a failed "
                "card type to retry, {} for chunks not in this run's chunk set (dropped)",
                self.path.name, self.resumed_chunks, len(self.chunk_ids),
                len(self.cards), self.retried_chunks, self.ignored_chunks,
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
                "n_chunks": len(self.chunk_ids),
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

    def _write(self, rec: dict) -> None:
        assert self._fh is not None
        self._fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def record(self, chunk_id: str, chunk_index: int,
               cards: list, failed_types: list[str]) -> None:
        """Checkpoint one completed chunk. ``cards`` are `GeneratedCard` dataclasses."""
        self._ensure_open()
        self._write({
            "kind": "chunk",
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "failed_types": list(failed_types),
            "cards": [dataclasses.asdict(c) for c in cards],
        })
        self._since_flush += 1
        self._last_flush = time.monotonic()

    def due(self, every: int, every_seconds: float) -> bool:
        """True when enough chunks or enough wall-clock time has passed to justify a report.

        The clock half matters because chunk cost is not uniform — the same workload measured
        7.6 s/chunk healthy and ~97 s/chunk under congestion collapse (§I26), so a pure
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
