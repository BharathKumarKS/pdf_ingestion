"""
Phoenix Arize observability — Phase E.

Sends OpenTelemetry traces to a running Phoenix server.
Every query becomes a root span with child spans for each retrieval stage:
  embed → intent_route → vector_search → rerank → synthesize

Usage
-----
Start Phoenix server (once, in a separate terminal):
    pip install arize-phoenix   # or: uv tool install arize-phoenix
    phoenix serve               # dashboard at http://localhost:6006

Enable in .env:
    PHOENIX_ENABLED=true
    PHOENIX_ENDPOINT=http://localhost:6006   # default

Auto-instrumentation covers all OpenAI-compatible LLM calls (synthesis,
card generation, RAPTOR). Manual spans cover retrieval stages.
"""
from __future__ import annotations

import functools
from contextlib import contextmanager
from typing import Any, Generator

_initialized = False
_tracer = None


def init_phoenix(settings=None) -> bool:
    """
    Initialize Phoenix tracing. Safe to call multiple times.
    Returns True if Phoenix is active, False if disabled or unavailable.
    """
    global _initialized, _tracer

    if _initialized:
        return _tracer is not None

    from src.core.config import get_settings
    cfg = settings or get_settings()

    if not cfg.phoenix_enabled:
        _initialized = True
        return False

    try:
        from phoenix.otel import register
        from openinference.instrumentation.openai import OpenAIInstrumentor
        from opentelemetry import trace

        # Register Phoenix as the OTLP trace endpoint
        tracer_provider = register(
            project_name="synapse-learning",
            endpoint=f"{cfg.phoenix_endpoint.rstrip('/')}/v1/traces",
            set_global_tracer_provider=True,
        )

        # Auto-instrument all OpenAI-compatible LLM calls
        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

        _tracer = trace.get_tracer("synapse.retrieval")
        _initialized = True
        return True

    except Exception as exc:
        import warnings
        warnings.warn(f"Phoenix tracing unavailable: {exc}", stacklevel=2)
        _initialized = True
        return False


def get_tracer():
    """Return the OpenTelemetry tracer (None if Phoenix is disabled)."""
    return _tracer


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator:
    """
    Context manager that creates a span when Phoenix is active.
    Falls back to a no-op when tracing is disabled.

    Usage:
        with telemetry.span("vector_search", {"query": q, "limit": 20}) as s:
            results = store.search(...)
            telemetry.set_attr(s, "hits", len(results))
    """
    if _tracer is None:
        yield None
        return

    from opentelemetry.trace import SpanKind
    with _tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, _safe(v))
        yield s


def set_attr(span_obj, key: str, value: Any) -> None:
    """Set an attribute on a span if the span exists."""
    if span_obj is not None:
        span_obj.set_attribute(key, _safe(value))


def _safe(v: Any) -> str | int | float | bool:
    """Coerce value to an OTEL-safe scalar."""
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)
