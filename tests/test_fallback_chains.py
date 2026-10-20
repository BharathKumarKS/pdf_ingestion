"""Fallback-chain tests (I6).

Stub tests structurally cannot reach these paths: with ``USE_STUB_LLM`` /
``USE_STUB_EMBEDDER`` set, the stubs return before any backend call happens, so the
failure branches never execute. A lane that silently falls back in *production* is a
silent-failure class the P0-2 work did not cover.

Each test drives the REAL class with a deliberately broken backend and pins what the
fallback returns — so a future change that makes a fallback quieter, or makes a stub's
answer indistinguishable from a real one, fails here.
"""
from __future__ import annotations

import numpy as np
import pytest
from loguru import logger

from src.core import llm
from src.core.config import Settings
from src.pdf_ingestion.embedder import NomicEmbedder
from src.pdf_ingestion.store import DocumentStore


class _BrokenQdrant:
    """Any attribute access returns a callable that raises — a simulated outage."""

    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise RuntimeError("cluster unreachable (simulated outage)")
        return _boom


class _FailingModel:
    """Stand-in for the loaded SentenceTransformer whose encode() blows up."""

    def eval(self):
        return self

    def encode(self, *args, **kwargs):
        raise RuntimeError("model encode failed (simulated)")


@pytest.fixture
def log_records():
    """Collect loguru records at ERROR so a silent fallback is detectable."""
    records: list[str] = []
    sink_id = logger.add(lambda msg: records.append(msg), level="ERROR")
    yield records
    logger.remove(sink_id)


@pytest.fixture
def log_warnings():
    """Collect loguru records at WARNING (the store's fallbacks log at WARNING)."""
    records: list[str] = []
    sink_id = logger.add(lambda msg: records.append(msg), level="WARNING")
    yield records
    logger.remove(sink_id)


def _cfg(backend: str = "openai", stub_llm: bool = False) -> Settings:
    return Settings(
        llm_backend=backend,
        use_stub_llm=stub_llm,
        use_stub_embedder=False,
        qdrant_in_memory=True,
        sqlite_url="sqlite:///./data/test_synapse.db",
        embedding_dim=768,
        embedding_dim_low=64,
    )


# ── LLM: a failed call returns "" and says so ──────────────────────────────
#
# The transport boundary moved in the §I24 fix: `call_llm` no longer issues a bare
# `httpx.post(...)`, it builds a `Client` and reads the body in chunks against a wall-clock
# deadline. So these tests break the backend at `llm._post_json` — the one place a request is
# actually made — rather than at `httpx.post`, which no longer exists and which would have left
# the patch silently inert (and the test making a real call).

@pytest.mark.parametrize("backend", ["openai", "ollama"])
def test_llm_failure_returns_empty_string(monkeypatch, backend, log_records):
    def _boom(*args, **kwargs):
        raise ConnectionError("no route to host (simulated)")

    monkeypatch.setattr(llm, "_post_json", _boom)
    monkeypatch.setattr(llm, "_LLM_RETRY_BACKOFF", 0.01)
    out = llm.call_llm("hello", settings=_cfg(backend=backend))
    assert out == ""
    assert any("LLM CALL FAILED" in r for r in log_records), "dead backend must log at ERROR"


def test_llm_failure_is_not_the_stub_answer(monkeypatch):
    """A production failure must not be mistakable for the stub's '{}'."""
    def _boom(*args, **kwargs):
        raise ConnectionError("simulated")

    monkeypatch.setattr(llm, "_post_json", _boom)
    monkeypatch.setattr(llm, "_LLM_RETRY_BACKOFF", 0.01)
    failed = llm.call_llm("hello", settings=_cfg())
    stubbed = llm.call_llm("hello", settings=_cfg(stub_llm=True))
    assert failed == ""
    assert stubbed == "{}"
    assert failed != stubbed


def test_empty_llm_response_is_flagged_by_the_caller_contract(monkeypatch):
    """A 200 with no choices returns "" (not an exception)."""
    monkeypatch.setattr(llm, "_post_json", lambda *a, **k: {"choices": []})
    assert llm.call_llm("hello", settings=_cfg()) == ""


def test_a_client_that_cannot_be_built_also_returns_empty_string(monkeypatch, log_records):
    """A failure before the first attempt must not escape as an exception (§I24)."""
    class _NoClient:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("no route to host (simulated)")

    monkeypatch.setattr(llm.httpx, "Client", _NoClient)
    assert llm.call_llm("hello", settings=_cfg()) == ""
    assert any("LLM CALL FAILED" in r for r in log_records)


def test_a_dead_backend_is_counted(monkeypatch):
    """§I24: the failure count is what a phase asserts on, so it must actually increment."""
    import httpx

    def _boom(*args, **kwargs):
        raise httpx.ConnectError("simulated")

    monkeypatch.setattr(llm, "_post_json", _boom)
    monkeypatch.setattr(llm, "_LLM_RETRY_BACKOFF", 0.01)
    llm.reset_llm_call_stats()
    llm.call_llm("hello", settings=_cfg())
    stats = llm.llm_call_stats()
    assert stats["calls"] == 1
    assert stats["failures"] == 1
    assert stats["retries"] == llm._LLM_RETRY_ATTEMPTS - 1


# ── Embedder: a failed encode degrades to ZERO vectors ─────────────────────

def test_embedder_failure_returns_zero_vectors(log_records):
    """The embedder swallows an encode failure into zero vectors — pinned, and logged.

    This is the silent-degradation risk: zero vectors are stored and searched as if
    they were real, so retrieval quietly returns nonsense instead of failing. The test
    pins both the shape and the ERROR log so the behaviour cannot change unnoticed.
    """
    emb = NomicEmbedder(_cfg())
    emb._model = _FailingModel()          # _load() sees a non-None model and skips the download

    vec = emb.embed_query("anything")
    assert vec.shape == (768,)
    assert not vec.any(), "expected all-zero fallback vector"
    assert any("Nomic encoding failed" in r for r in log_records)


# ── Store: a broken cluster degrades to empty/zero, not an exception ───────

def test_visual_search_returns_empty_on_store_failure(log_warnings):
    store = DocumentStore(_cfg())
    store._qdrant = _BrokenQdrant()
    assert store.visual_search(np.zeros((1, 128), dtype=np.float32), "global") == []
    # prove the exception path was taken, not an early return
    assert any("Visual search failed" in r for r in log_warnings)


def test_count_visual_vectors_returns_zero_on_store_failure(log_warnings):
    store = DocumentStore(_cfg())
    store._qdrant = _BrokenQdrant()
    assert store.count_visual_vectors(["global"]) == 0
    assert any("Visual index count failed" in r for r in log_warnings)


def test_count_collection_counts_points_and_survives_an_outage(log_warnings):
    """I3: the Admin Status panel's store-side count."""
    from qdrant_client.models import Distance, PointStruct, VectorParams

    store = DocumentStore(_cfg())
    store._qdrant.create_collection(
        "test_count", vectors_config=VectorParams(size=4, distance=Distance.COSINE))
    store._qdrant.upsert("test_count", points=[
        PointStruct(id=1, vector=[0.1, 0.2, 0.3, 0.4]),
        PointStruct(id=2, vector=[0.4, 0.3, 0.2, 0.1]),
    ])
    assert store.count_collection("test_count") == 2

    store._qdrant = _BrokenQdrant()
    assert store.count_collection("test_count") == 0
    assert any("Collection count failed" in r for r in log_warnings)
