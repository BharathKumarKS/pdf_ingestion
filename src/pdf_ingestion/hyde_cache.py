"""HyDE cache — one frozen hypothetical per query id (plan §2).

**Why this exists.** `evaluate_rag.py` generates a HyDE hypothetical per query with an LLM
whenever `hyde_enabled` and the query is `factual`/`overview`. There was **no cache**, so every
arm of an A/B embedded a *different* hypothetical for the same query — the query vector was
nondeterministic per arm, which makes any arm-to-arm comparison meaningless. Same defect class as
§I68 (the nondeterministic fusion): the instrument, not the treatment, moves the number.

**Cache the TEXT, not the vector.** The hypothetical string is **embedder-independent**, so ONE
cache serves every candidate embedder in §I70's screen *and* the eventual re-ingest. A vector
cache would have to be rebuilt per embedder and would defeat the purpose.

**The file is keyed by the RUN**, so a model or prompt change cannot silently reuse stale text:

    data/hyde_cache/<queries-digest>__<model>__<prompt-digest>.json

and the model, the prompt and the system message are **frozen inside the file** as well, and
**re-validated on read**. A filename is a hint; the header is the contract (§I25's lesson: a cache
that reports a hit for something it cannot use is worse than a miss).

⚠️ **A miss is LOUD, never a live LLM call.** `get()` raises `HydeCacheMiss`. Generation happens
only in `build()`, which is an explicit, one-time, reported step. A run that silently falls back to
the LLM mid-measurement reintroduces exactly the nondeterminism this module removes (§I25's class:
a total loss that reads as a success).

⚠️ **This module is NOT wired into §I70's embedder screen** — the screen is HyDE-off by design.
It is for the product-path comparison in the plan's §3.

⚠️ **The prompt is duplicated in the repo today** — `scripts/evaluate_rag.py` and
`scripts/funnel_boundary_recall.py` each carry a verbatim copy. Those copies are the source of
truth for what the *deployed* system sends; `HYDE_PROMPT_TEMPLATE` / `HYDE_SYSTEM` here are the
same strings, and `tests/test_hyde_cache.py` asserts they still match the `evaluate_rag.py` call
site so a change in either place is caught rather than silently forking the cache key.

Usage:

    from src.pdf_ingestion.hyde_cache import build, load
    build(QUERIES, queries, cfg=cfg)      # one-time; costs one LLM call per factual/overview query
    cache = load(QUERIES, cfg=cfg)        # later runs: free, deterministic
    hyp = cache.get(qid)                  # raises HydeCacheMiss if absent
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

# ── the frozen prompt (must stay identical to the deployed call sites) ────────────────────────

HYDE_PROMPT_TEMPLATE = (
    "Write 2-3 sentences of physics textbook content "
    "that directly answers: {query}"
)
HYDE_SYSTEM = (
    "You are a physics textbook author. Write factual content only. "
    "No preamble, no 'Here is...', just the content itself."
)

# `evaluate_rag.py` applies HyDE to exactly these types. Anything else keeps its raw query vector.
HYDE_QUERY_TYPES = ("factual", "overview")

# Bump when the FILE SHAPE changes (not when the prompt changes — the prompt digest covers that).
HYDE_SCHEMA_VERSION = 1

CACHE_DIR = "data/hyde_cache"


class HydeCacheError(RuntimeError):
    """The cache file exists but cannot be trusted for this run."""


class HydeCacheMiss(HydeCacheError):
    """The cache is valid for this run but holds no entry for the requested query id."""


def prompt_for(query_text: str) -> str:
    """The user prompt for one query — the single definition of it."""
    return HYDE_PROMPT_TEMPLATE.format(query=query_text)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def prompt_digest() -> str:
    """Digest of BOTH the prompt template and the system message.

    Both go to the model, so a change to either changes the text the cache holds — keying on the
    template alone would silently reuse entries generated under a different system message.
    """
    return _digest(HYDE_PROMPT_TEMPLATE + "\x00" + HYDE_SYSTEM)


def queries_digest(queries_path: Path) -> str:
    """Digest of the queries file's BYTES — so editing a query text invalidates the cache."""
    return hashlib.sha256(Path(queries_path).read_bytes()).hexdigest()[:16]


def cache_path(queries_path: Path, model: str, repo_root: Path | None = None) -> Path:
    """`data/hyde_cache/<queries-digest>__<model>__<prompt-digest>.json`."""
    root = repo_root or Path(__file__).resolve().parents[2]
    safe_model = model.replace("/", "_")
    name = f"{queries_digest(queries_path)}__{safe_model}__{prompt_digest()}.json"
    return root / CACHE_DIR / name


@dataclass
class HydeCache:
    """A loaded, validated cache. `get` is loud; `lookup` is quiet."""

    path: Path
    meta: dict
    entries: dict[str, str] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return str(self.meta.get("model", ""))

    def lookup(self, query_id: str) -> str | None:
        """The hypothetical for `query_id`, or None. Never raises, never generates."""
        return self.entries.get(query_id)

    def get(self, query_id: str) -> str:
        """The hypothetical for `query_id`, or raise `HydeCacheMiss`.

        ⚠️ Deliberately NOT a fallback to a live LLM call: that would make one arm's query vector
        differ from another's for the same query, which is the whole defect this cache exists to
        remove.
        """
        hyp = self.entries.get(query_id)
        if not hyp:
            raise HydeCacheMiss(
                f"HyDE cache {self.path.name} has no hypothetical for query {query_id!r}. "
                f"Generate it with `build(..., force=False)` (one LLM call per factual/overview "
                f"query), or run with hyde disabled. Refusing to call the LLM mid-run."
            )
        return hyp

    def __len__(self) -> int:
        return len(self.entries)


def load(queries_path: Path, model: str | None = None, cfg=None) -> HydeCache:
    """Load and VALIDATE the cache for this run.

    Raises `HydeCacheError` when the file is missing or its header disagrees with the run — a
    mismatch is an honest miss, never a silent reuse (§I25).
    """
    if cfg is None:
        from src.core.config import get_settings
        cfg = get_settings()
    model = model or cfg.openai_model
    path = cache_path(queries_path, model)
    if not path.exists():
        raise HydeCacheError(
            f"no HyDE cache at {path}. Build it once with `build({queries_path.name}, queries)`, "
            f"or run with hyde disabled. Refusing to call the LLM mid-run."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = payload.get("meta", {})
    entries = payload.get("entries", {})

    want = {
        "schema_version": HYDE_SCHEMA_VERSION,
        "model": model,
        "prompt_digest": prompt_digest(),
        "queries_digest": queries_digest(queries_path),
    }
    bad = {k: {"file": meta.get(k), "this_run": v} for k, v in want.items() if meta.get(k) != v}
    if bad:
        raise HydeCacheError(
            f"HyDE cache {path.name} does not match this run — refusing to reuse it. "
            f"Mismatched header field(s): {bad}. A model, prompt or query-set change must "
            f"invalidate the cache rather than silently reuse text generated under the old one."
        )
    logger.info("HyDE cache loaded: {} entries from {}", len(entries), path.name)
    return HydeCache(path=path, meta=meta, entries=entries)


def build(
    queries_path: Path,
    queries: list[dict],
    model: str | None = None,
    cfg=None,
    *,
    force: bool = False,
    on_call=None,
) -> HydeCache:
    """Generate the hypotheticals that are missing, then write the cache atomically.

    Only `HYDE_QUERY_TYPES` queries get one (that is what `evaluate_rag.py` does). Existing
    entries are reused unless `force`. ⚠️ An EMPTY model return is counted as a failure, is not
    cached, and is raised at the end — a silently empty hypothetical would make that query's
    vector the empty-string embedding (§I25/§I52's class).
    """
    if cfg is None:
        from src.core.config import get_settings
        cfg = get_settings()
    model = model or cfg.openai_model
    path = cache_path(queries_path, model)

    entries: dict[str, str] = {}
    if path.exists():
        try:
            entries = dict(json.loads(path.read_text(encoding="utf-8")).get("entries", {}))
        except Exception as exc:  # noqa: BLE001
            logger.warning("HyDE cache {} unreadable ({}); regenerating", path.name, exc)
            entries = {}

    targets = [
        q for q in queries
        if isinstance(q, dict) and q.get("id") and q.get("query_type") in HYDE_QUERY_TYPES
    ]
    from src.core.llm import call_llm

    reused = 0
    generated = 0
    failed: list[dict] = []
    t0 = time.time()
    for i, q in enumerate(targets, 1):
        qid, text = str(q["id"]), str(q.get("query", ""))
        if not force and entries.get(qid):
            reused += 1
            continue
        t = time.time()
        try:
            hyp = call_llm(prompt=prompt_for(text), system=HYDE_SYSTEM, settings=cfg)
        except Exception as exc:  # noqa: BLE001
            failed.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("HyDE FAILED {} ({})", qid, exc)
            continue
        if not hyp or not hyp.strip():
            # A 200 with empty content is the §I25 shape: it must not be cached as if it worked.
            failed.append({"id": qid, "error": "empty model return"})
            logger.error("HyDE EMPTY {} — not cached", qid)
            continue
        entries[qid] = hyp.strip()
        generated += 1
        # One line per call, plus a rolling rate — a phase that logs only totals cannot be told
        # apart from a stalled one (§I23's lesson).
        logger.info(
            "HyDE {} [{}/{}] {} chars in {:.1f}s",
            qid, i, len(targets), len(entries[qid]), time.time() - t,
        )
        if on_call:
            on_call(qid, len(entries[qid]), time.time() - t)
        if i % 25 == 0:
            rate = i / max(time.time() - t0, 1e-9) * 60
            logger.info("HyDE progress: {}/{} ({:.1f} calls/min)", i, len(targets), rate)

    meta = {
        "schema_version": HYDE_SCHEMA_VERSION,
        "model": model,
        "prompt_template": HYDE_PROMPT_TEMPLATE,
        "system": HYDE_SYSTEM,
        "prompt_digest": prompt_digest(),
        "queries_file": str(queries_path),
        "queries_digest": queries_digest(queries_path),
        "query_types": list(HYDE_QUERY_TYPES),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_entries": len(entries),
        "n_targets": len(targets),
        "n_reused": reused,
        "n_generated": generated,
        "n_failed": len(failed),
        "failures": failed,
        "wall_seconds": round(time.time() - t0, 1),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"meta": meta, "entries": entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)   # atomic: a crash mid-write cannot leave a half cache
    logger.info(
        "HyDE cache written: {} ({} entries: {} reused, {} generated, {} failed) in {}s",
        path, len(entries), reused, generated, len(failed), meta["wall_seconds"],
    )

    if failed:
        # Loud, and non-zero: an incomplete cache is a measurement defect, not a warning.
        print(
            f"HyDE build FAILED for {len(failed)} query/queries: "
            f"{[f['id'] for f in failed]} — see the cache meta. Refusing to report a complete "
            f"cache.",
            file=sys.stderr,
        )
    return HydeCache(path=path, meta=meta, entries=entries)
