"""Interval checkpoint + resume for §G2 community summarisation (IMPROVEMENTS.md §I53).

**The problem this solves.** `summarize_communities` makes its ~600 LLM calls in one pass and the
caller writes the artifact once, after the last one. The 2026-10-22 build issued **597 sequential
calls** over 19 min 42 s and logged **nothing per call**, so an abort at call 596 would have
discarded all of it — and nothing in the log could have distinguished "healthy and slow" from
"stalled" (§I23's lesson, measured there as an 18-minute 58× throughput stall that a single-request
liveness probe read as all-clear).

**Why a side-car and not incremental artifact writes.** The JSON artifact is the single write point
and it stays that way: a partially-written summary tree is indistinguishable from a complete one to
V1 (the modularity gate), V4 (the cost ledger) and the retrieval path V5 will build — exactly the
"an artifact existing is not the item done" failure (§I25's class). So the checkpoint holds the
*summary output* beside the artifact, as `graph_checkpoint` does for concept extraction (§I23) and
`embed_cache` does for the late-chunk phase (§I19).

**Key.** ``(document, model, seed, resolutions, prompt budget, prompt digests)`` — the identity of
the *run*, not of its inputs. The model is ``cfg.openai_model``, the **summariser** — a different
model from the graph build's extractor (§I52); the seed must match ``g2_leiden_gate.py``'s or the
communities summarised are not the communities the gate approved (§I50 Finding 4); the prompt
digests matter because the prompts are code constants and nothing else would notice them moving.

**An entry is reused only if its input digest matches** — the digest of the exact material the
summary was built from (a leaf's ordered passages, a parent's ordered child summaries). That is what
makes a resume *correct* rather than merely cheap: a parent whose child was re-attempted and now
summarises differently has a different input, so its checkpointed summary is not reused.

**A community whose calls returned empty is NOT done** — it is re-attempted on resume. `call_llm`
returns ``""`` on failure rather than raising (§I24), so a checkpoint that recorded those as complete
would bake the loss in permanently (§I25). A community with genuinely no source material makes no
call at all and is not recorded; that direction is the safe one, since a transiently empty read is
then re-read rather than frozen.

**Crash safety.** Append-only JSONL, ``flush()`` + ``fsync()`` on every write. A crash can tear at
most the final line; the loader stops at the last line that parses and truncates the file back to
it, so a torn record costs one community, never the file.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from loguru import logger

# Bump when the checkpoint FORMAT or the summary serialisation changes. Config cannot capture a code
# change, and a stale entry read back after one would be silently wrong.
_SCHEMA_VERSION = 1

# The digest scheme for the run key, stored in the header and checked on read (§I19a).
_DIGEST_SCHEME = "sha256:16"


def input_digest(parts: list[str]) -> str:
    """Digest of the material a summary was built from — the checkpoint's validity key.

    For a leaf this is its ordered passages; for a parent, its ordered child summaries. Two runs
    whose material differs (a re-attempted child, a changed chunk, a different passage cap) produce
    different digests, so the entry is re-computed rather than reused.
    """
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def prompt_digest(template: str) -> str:
    """Digest of one prompt template, so a prompt change invalidates the checkpoint."""
    return hashlib.sha256(template.encode()).hexdigest()[:16]


def run_key(
    document_id: str,
    model: str,
    seed: int,
    resolutions: tuple[float, ...],
    max_prompt_chars: int,
    prompt_digests: dict[str, str],
) -> str:
    """Identity of the (document, model, seed, resolutions, budget, prompts) a checkpoint belongs to."""
    h = hashlib.sha256()
    h.update(f"schema={_SCHEMA_VERSION}\x00scheme={_DIGEST_SCHEME}".encode())
    h.update(f"\x00doc={document_id}\x00model={model}\x00seed={seed}".encode())
    h.update(f"\x00res={','.join(f'{r:g}' for r in resolutions)}".encode())
    h.update(f"\x00budget={max_prompt_chars}".encode())
    for name in sorted(prompt_digests):
        h.update(f"\x00prompt:{name}={prompt_digests[name]}".encode())
    return h.hexdigest()[:16]


@dataclass
class SummaryCheckpoint:
    """Append-only JSONL of completed community summaries for one §G2 build."""

    path: Path
    document_id: str
    digest: str
    model: str
    seed: int
    resolutions: tuple[float, ...]
    max_prompt_chars: int
    prompt_digests: dict[str, str]

    # Filled by _load(): (level, community_id) -> {"ok", "input_digest", "summary"}.
    entries: dict[tuple[int, int], dict] = field(default_factory=dict)
    resumed_communities: int = 0
    stale_communities: int = 0
    retried_communities: int = 0

    _fh: IO[str] | None = None

    # -- construction ---------------------------------------------------------

    @classmethod
    def open(
        cls,
        directory: str | Path,
        document_id: str,
        model: str,
        seed: int,
        resolutions: tuple[float, ...],
        max_prompt_chars: int,
        prompt_digests: dict[str, str],
        fresh: bool = False,
    ) -> SummaryCheckpoint:
        """Open (or create) the checkpoint for this run, loading whatever is already done.

        ``fresh=True`` deletes any existing file for this key first, so a re-run that wants no resume
        cannot inherit it.
        """
        digest = run_key(document_id, model, seed, resolutions, max_prompt_chars, prompt_digests)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{document_id[:8]}__{digest}.jsonl"
        if fresh and path.exists():
            logger.warning("Summary checkpoint: discarding {} (fresh run requested)", path)
            path.unlink()
        cp = cls(path=path, document_id=document_id, digest=digest, model=model, seed=seed,
                 resolutions=tuple(resolutions), max_prompt_chars=max_prompt_chars,
                 prompt_digests=dict(prompt_digests))
        cp._load()
        return cp

    # -- load -----------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("Summary checkpoint: new file {}", self.path)
            return

        good_bytes = 0
        header: dict | None = None
        records: list[dict] = []
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
                    elif rec.get("kind") == "community":
                        records.append(rec)
                    else:
                        torn = True
                        break
                    good_bytes += len(raw)
        except OSError as exc:
            logger.warning("Summary checkpoint unreadable ({}): {} — starting fresh", self.path, exc)
            return

        # The header is the identity check (§I19a): a file that does not match this run's
        # (document, key, model, seed, resolutions, budget, prompts, schema) is not resumed,
        # whatever its name says.
        if header is None:
            logger.warning("Summary checkpoint {} has no header — ignoring it", self.path)
            return
        if (header.get("document_id") != self.document_id
                or header.get("digest") != self.digest
                or header.get("model") != self.model
                or header.get("seed") != self.seed
                or header.get("schema") != _SCHEMA_VERSION
                or header.get("digest_scheme") != _DIGEST_SCHEME):
            logger.warning(
                "Summary checkpoint {} does not match this run (doc/digest/model/seed/schema) — "
                "ignoring it and starting a fresh file", self.path,
            )
            return

        for rec in records:
            level, cid = rec.get("level"), rec.get("community")
            if level is None or cid is None:
                continue
            # Last record wins: a community recorded as failed and then re-attempted successfully
            # on a resume must end up marked done, not stuck at the earlier failure.
            self.entries[(int(level), int(cid))] = {
                "ok": bool(rec.get("ok", False)),
                "input_digest": rec.get("input_digest"),
                "summary": rec.get("summary") or "",
            }

        if torn:
            # Rewind to the last complete record so the next append is not preceded by a fragment.
            logger.warning(
                "Summary checkpoint {} ends mid-record — truncating to {} bytes (one community lost)",
                self.path, good_bytes,
            )
            with self.path.open("r+b") as fh:
                fh.truncate(good_bytes)

        if self.entries:
            logger.info(
                "Summary checkpoint {}: {} community(ies) already summarised", self.path.name,
                len(self.entries),
            )

    # -- lookup / write -------------------------------------------------------

    def lookup(self, level: int, community: int, digest: str) -> str | None:
        """The recorded summary for a community, or None when it must be re-computed.

        A hit requires all three: an entry, a matching input digest, and a non-empty summary. An
        entry whose calls returned empty is a failure, not a summary, and is re-attempted (§I25).
        """
        rec = self.entries.get((level, community))
        if rec is None:
            return None
        if rec["input_digest"] != digest:
            self.stale_communities += 1
            return None
        if not rec["ok"]:
            self.retried_communities += 1
            return None
        self.resumed_communities += 1
        return rec["summary"]

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
                "seed": self.seed,
                "resolutions": list(self.resolutions),
                "max_prompt_chars": self.max_prompt_chars,
                "prompt_digests": self.prompt_digests,
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

    def _write(self, rec: dict) -> None:
        assert self._fh is not None
        self._fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def record(self, level: int, community: int, digest: str, summary: str, ok: bool) -> None:
        """Checkpoint one community's summary. A community that returned empty is written with
        ``ok=False`` so it is re-attempted on resume rather than counted as done."""
        self._ensure_open()
        self._write({
            "kind": "community",
            "level": int(level),
            "community": int(community),
            "input_digest": digest,
            "ok": bool(ok),
            "summary": summary or "",
        })
        self.entries[(int(level), int(community))] = {
            "ok": bool(ok), "input_digest": digest, "summary": summary or "",
        }

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None
