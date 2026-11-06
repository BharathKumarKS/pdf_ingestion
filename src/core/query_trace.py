"""Per-query route/latency trace — README Phase 6, the cheap half.

One structured record per query: the **intent route**, the **lanes that fired**, **k**, the **top-1
score**, and the **per-stage latency** (embed / search / rerank / synthesize). Records go to
(a) one loguru line (JSON) and (b) a **process-local ring buffer** the Status tab reads.

Why a module and not just log lines: a guardrail/metric that is not COUNTED is invisible (§12's
"record the decision in the artifact"). This is the counting surface.

Deliberately **no DB, no collection write, no network** — a deque guarded by a lock. The buffer is
process-local on purpose (a Streamlit process shows its own recent queries); it is a diagnostic, not
a store.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Iterator

from loguru import logger

STAGES = ("embed", "search", "rerank", "synthesize")
MAX_RECENT = 50

_LOCK = threading.Lock()
_RECENT: deque["QueryTrace"] = deque(maxlen=MAX_RECENT)


@dataclass
class QueryTrace:
    """One query's route + latency record. All fields scalar/JSON-safe."""

    query: str = ""
    intent: str = ""
    lanes: list[str] = field(default_factory=list)
    k: int = 0
    top1: float | None = None
    n_hits: int = 0
    stages_ms: dict[str, float] = field(default_factory=dict)
    total_ms: float | None = None
    error: str | None = None
    ts: float = field(default_factory=time.time)

    def as_log(self) -> str:
        """One JSON line — the structured log form."""
        return json.dumps(asdict(self), default=str, sort_keys=True)


def record(trace: QueryTrace) -> QueryTrace:
    """Append a finished trace to the ring buffer and emit one log line."""
    with _LOCK:
        _RECENT.append(trace)
    logger.info("QUERY_TRACE {}", trace.as_log())
    return trace


def recent(n: int = 10) -> list[QueryTrace]:
    """The last `n` traces, NEWEST LAST (chronological, like the log)."""
    with _LOCK:
        items = list(_RECENT)
    return items[-n:] if n > 0 else []


def clear() -> None:
    with _LOCK:
        _RECENT.clear()


class Tracer:
    """Context manager timing a query's stages and recording the result.

    Usage:
        with Tracer(query, intent=intent, lanes=lanes, k=20) as tr:
            with tr.stage("embed"):
                q_vec = embedder.embed_query(query)
            with tr.stage("search"):
                hits = store.search_with_das(...)
            tr.set(top1=..., n_hits=len(hits))
        # on exit: total_ms set, the trace appended, one line logged
    """

    def __init__(self, query: str, intent: str = "", lanes: list[str] | None = None, k: int = 0):
        self.trace = QueryTrace(query=query[:200], intent=intent, lanes=list(lanes or []), k=k)
        self._t0 = 0.0
        self._stage_t0 = 0.0
        self._last_mark = 0.0

    def start(self) -> "Tracer":
        self._t0 = time.perf_counter()
        self._last_mark = self._t0
        return self

    def __enter__(self) -> "Tracer":
        return self.start()

    def set(self, **kw) -> None:
        for key, val in kw.items():
            if not hasattr(self.trace, key):
                raise AttributeError(f"QueryTrace has no field {key!r}")
            setattr(self.trace, key, val)

    def mark(self, name: str) -> None:
        """Record elapsed ms since the previous mark (or start()) under `name`.

        For callers that cannot wrap each stage in a `with` block (a long function body): call
        `mark("embed")` after the embed step, `mark("search")` after the search, etc.
        """
        now = time.perf_counter()
        self.trace.stages_ms[name] = self.trace.stages_ms.get(name, 0.0) + round((now - self._last_mark) * 1000, 1)
        self._last_mark = now

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time one stage; record it even if the body raises, then re-raise."""
        self._stage_t0 = time.perf_counter()
        try:
            yield
        finally:
            ms = round((time.perf_counter() - self._stage_t0) * 1000, 1)
            self.trace.stages_ms[name] = self.trace.stages_ms.get(name, 0.0) + ms

    def finish(self, **fields) -> QueryTrace:
        """Set fields, stamp total_ms and record. Used by __exit__ and by non-context-manager callers."""
        if fields:
            self.set(**fields)
        self.trace.total_ms = round((time.perf_counter() - self._t0) * 1000, 1)
        return record(self.trace)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None and self.trace.error is None:
            self.trace.error = f"{exc_type.__name__}: {exc}"
        self.finish()
        return False  # never swallow
