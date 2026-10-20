"""Tests for the shared LLM caller's retry + total-request deadline (IMPROVEMENTS.md §I24).

The defect these pin: `_call_openai` issued **one un-retried POST** with a 120 s per-read
timeout, and httpx's read timeout is per READ OPERATION, not per request — so a response body
that keeps trickling resets the timer on every chunk and outlives any read timeout. Measured
cost on the Phase B card run: a **41-minute silent window** (22:12:44 → 22:53:48) inside
requests the timeout could not bound, and with no retry there was nothing to catch it.

All offline: `_post_json` is driven with a fake client, and the end-to-end paths with
`httpx.MockTransport`. Nothing here touches the cluster.
"""
from __future__ import annotations

import time

import httpx
import pytest

from src.core import llm
from src.core.config import Settings


def _settings(**over) -> Settings:
    base = dict(
        llm_backend="openai",
        openai_api_base="http://cluster.test:8000",
        openai_model="openai/gpt-oss-20b",
        openai_api_key="none",
        ollama_timeout=120,
        use_stub_llm=False,
    )
    base.update(over)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_stats_and_backoff(monkeypatch):
    """Zero the counters and shrink the backoff so a retry test does not sleep for seconds."""
    llm.reset_llm_call_stats()
    monkeypatch.setattr(llm, "_LLM_RETRY_BACKOFF", 0.01)
    yield
    llm.reset_llm_call_stats()


def _install_transport(monkeypatch, handler):
    """Route every `httpx.Client` the module builds through a MockTransport."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(llm.httpx, "Client", factory)


# ── The deadline ───────────────────────────────────────────────────────────

class _TricklingStream:
    """A response that keeps yielding bytes without ever finishing — the §I24 shape."""

    def __init__(self, chunks: int, delay: float):
        self._chunks, self._delay = chunks, delay

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def request(self):
        return httpx.Request("POST", "http://cluster.test:8000/v1/chat/completions")

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        for _ in range(self._chunks):
            time.sleep(self._delay)
            yield b" "


class _FakeClient:
    def __init__(self, stream):
        self._stream = stream

    def stream(self, *args, **kwargs):
        return self._stream


def test_post_json_raises_when_the_total_deadline_is_exceeded():
    """A trickling body must be cut off by the wall clock, not by the per-read timeout."""
    client = _FakeClient(_TricklingStream(chunks=20, delay=0.02))
    started = time.monotonic()
    with pytest.raises(httpx.ReadTimeout) as excinfo:
        llm._post_json(client, "http://x", {}, {}, 120.0, 0.05)
    elapsed = time.monotonic() - started

    assert "total deadline" in str(excinfo.value)
    assert elapsed < 0.5, "the deadline did not fire promptly"
    assert llm.llm_call_stats()["deadline_hits"] == 1


def test_deadline_is_a_transport_error_so_the_retry_catches_it():
    """The deadline is raised as `ReadTimeout` deliberately — it must be classified retryable."""
    assert llm._retryable(httpx.ReadTimeout("x", request=httpx.Request("POST", "http://x")))


def test_post_json_returns_the_parsed_body_when_it_finishes_in_time():
    class _Whole:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        @property
        def request(self):
            return httpx.Request("POST", "http://x")

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield b'{"ok": '
            yield b"true}"

    body = llm._post_json(_FakeClient(_Whole()), "http://x", {}, {}, 120.0, 30.0)
    assert body == {"ok": True}


def test_budget_never_undercuts_an_explicit_longer_timeout():
    assert llm._budget(None) == llm._LLM_DEADLINE
    assert llm._budget(60) == llm._LLM_DEADLINE
    assert llm._budget(llm._LLM_DEADLINE + 600) == llm._LLM_DEADLINE + 600


# ── Retry policy ───────────────────────────────────────────────────────────

def test_transient_failures_are_retried_and_the_call_succeeds(monkeypatch):
    attempts = {"n": 0}

    def flaky(client, url, payload, headers, timeout, deadline_s):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("connection reset")
        return {"choices": [{"message": {"content": "hello"}}]}

    monkeypatch.setattr(llm, "_post_json", flaky)
    out = llm._call_openai("p", "", _settings(), 120, False)

    assert out == "hello"
    assert attempts["n"] == 3
    stats = llm.llm_call_stats()
    assert stats["retries"] == 2
    assert stats["failures"] == 0


def test_a_non_retryable_status_fails_fast(monkeypatch):
    attempts = {"n": 0}

    def bad_request(client, url, payload, headers, timeout, deadline_s):
        attempts["n"] += 1
        request = httpx.Request("POST", url)
        raise httpx.HTTPStatusError(
            "400", request=request, response=httpx.Response(400, request=request)
        )

    monkeypatch.setattr(llm, "_post_json", bad_request)
    out = llm._call_openai("p", "", _settings(), 120, False)

    assert out == ""
    assert attempts["n"] == 1, "a 4xx must not be retried — it would fail identically"
    assert llm.llm_call_stats()["failures"] == 1


def test_retry_is_bounded_and_the_failure_is_counted(monkeypatch):
    attempts = {"n": 0}

    def always_timeout(client, url, payload, headers, timeout, deadline_s):
        attempts["n"] += 1
        raise httpx.ReadTimeout("stalled", request=httpx.Request("POST", url))

    monkeypatch.setattr(llm, "_post_json", always_timeout)
    out = llm._call_openai("p", "", _settings(), 120, False)

    assert out == "", "the empty-string contract must survive the change"
    assert attempts["n"] == llm._LLM_RETRY_ATTEMPTS
    assert llm.llm_call_stats()["failures"] == 1


def test_retryable_classification():
    request = httpx.Request("POST", "http://x")
    assert llm._retryable(httpx.ConnectTimeout("t", request=request))
    assert llm._retryable(httpx.ReadTimeout("t", request=request))
    assert llm._retryable(httpx.HTTPStatusError(
        "500", request=request, response=httpx.Response(500, request=request)))
    assert llm._retryable(httpx.HTTPStatusError(
        "429", request=request, response=httpx.Response(429, request=request)))
    assert not llm._retryable(httpx.HTTPStatusError(
        "404", request=request, response=httpx.Response(404, request=request)))
    assert not llm._retryable(ValueError("not a transport problem"))


# ── End to end over a mock transport ───────────────────────────────────────

def test_openai_path_sends_the_right_url_and_payload(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _install_transport(monkeypatch, handler)
    out = llm._call_openai("the prompt", "be terse", _settings(), 120, True)

    assert out == "ok"
    # The base already ends in a bare host — no doubled /v1.
    assert seen["url"] == "http://cluster.test:8000/v1/chat/completions"
    assert '"response_format"' in seen["body"]
    assert "the prompt" in seen["body"]
    assert llm.llm_call_stats()["calls"] == 1


def test_a_v1_suffix_in_the_base_url_is_not_doubled(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _install_transport(monkeypatch, handler)
    llm._call_openai("p", "", _settings(openai_api_base="http://cluster.test:8000/v1"), 120, False)
    assert seen["url"] == "http://cluster.test:8000/v1/chat/completions"


def test_a_200_with_no_choices_is_a_counted_failure(monkeypatch):
    _install_transport(monkeypatch, lambda request: httpx.Response(200, json={"choices": []}))
    out = llm._call_openai("p", "", _settings(), 120, False)

    assert out == ""
    assert llm.llm_call_stats()["failures"] == 1


def test_a_5xx_is_retried_over_the_transport(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": "backend unreachable"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "recovered"}}]})

    _install_transport(monkeypatch, handler)
    out = llm._call_openai("p", "", _settings(), 120, False)

    assert out == "recovered"
    assert calls["n"] == 2


def test_the_stub_backend_short_circuits_before_any_http(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("stub mode must not build an HTTP client")

    monkeypatch.setattr(llm.httpx, "Client", boom)
    assert llm.call_llm("p", settings=_settings(use_stub_llm=True)) == "{}"
    assert llm.llm_call_stats()["calls"] == 0


def test_ollama_path_uses_its_own_endpoint(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"response": "from ollama"})

    _install_transport(monkeypatch, handler)
    out = llm._call_ollama("p", "", _settings(
        llm_backend="ollama", ollama_host="http://ollama.test:11434",
        ollama_model="llama3.2"), 120, False)

    assert out == "from ollama"
    assert seen["url"] == "http://ollama.test:11434/api/generate"
