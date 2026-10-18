"""Tests for the cluster dense embedder (src/pdf_ingestion/cluster_embedder.py).

Two things are pinned here:

1. the **payload contract** of the cluster endpoint — in particular that
   ``return_token_embeddings`` is what produces per-token vectors, and that a reordered
   response is reassembled by ``index`` rather than by array position;
2. the MRL slice, which must re-normalise (a truncated prefix of a unit vector is not unit).

All offline: the cluster is replaced by ``httpx.MockTransport``.
"""
from __future__ import annotations

import httpx
import numpy as np
import pytest

from src.core.config import Settings
from src.pdf_ingestion.cluster_embedder import (
    ClusterDenseEmbedder,
    StubClusterEmbedder,
    get_cluster_embedder,
    mrl_slice,
    reset_cluster_embedder,
)

URL = "http://cluster.test/embed-text/v1/embeddings"


def _settings(**over) -> Settings:
    base = dict(
        sv_embed_url=URL,
        dense_model="Qwen/Qwen3-Embedding-0.6B",
        dense_dim=1024,
        dense_dim_low=64,
        query_instruction="Instruct: test\nQuery: ",
        embedding_batch_size=8,
    )
    base.update(over)
    return Settings(**base)


def _unit(rng, shape):
    a = rng.random(shape).astype(np.float32)
    return a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9)


# ── MRL ────────────────────────────────────────────────────────────────────

def test_mrl_slice_truncates_and_renormalises():
    rng = np.random.default_rng(0)
    vec = _unit(rng, (1024,))
    low = mrl_slice(vec, 64)
    assert low.shape == (64,)
    assert np.isclose(np.linalg.norm(low), 1.0, atol=1e-5)
    # The slice is the leading coordinates, not a projection.
    assert np.allclose(low, vec[:64] / np.linalg.norm(vec[:64]), atol=1e-6)


def test_mrl_slice_of_a_mean_equals_mean_of_slices():
    """The linearity the plan leans on: mean(tok)[:64] == mean(tok[:64]).

    This is what lets a late-chunked (mean-pooled) vector still have a meaningful 64d MRL
    view — so late chunking and the two-dim design compose.
    """
    rng = np.random.default_rng(1)
    toks = _unit(rng, (7, 1024))
    pooled = toks.mean(axis=0)
    left = mrl_slice(pooled, 64)                      # slice AFTER pooling
    right = mrl_slice(toks[:, :64].mean(axis=0), 64)  # pool AFTER slicing, re-normalised
    assert np.allclose(left, right, atol=1e-6)


# ── Stub ───────────────────────────────────────────────────────────────────

def test_stub_shapes_and_determinism():
    stub = StubClusterEmbedder(dim=1024, dim_low=64)
    docs = stub.embed_documents(["alpha", "beta"])
    assert [d.shape for d in docs] == [(1024,), (1024,)]
    assert np.allclose(np.linalg.norm(docs[0]), 1.0, atol=1e-5)
    assert np.allclose(stub.embed_documents(["alpha"])[0], docs[0])  # deterministic
    assert stub.embed_query("alpha").shape == (1024,)
    toks = stub.embed_documents_tokens(["abcdefgh"])
    assert toks[0].ndim == 2 and toks[0].shape[1] == 1024


# ── Cluster client: payload contract ───────────────────────────────────────

def _capturing_client(handler, requests: list):
    def wrapped(request: httpx.Request) -> httpx.Response:
        import json

        requests.append(json.loads(request.content.decode()))
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped))


def test_documents_payload_has_no_token_flag_and_pools():
    import json

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        data = [
            {"index": i, "embedding": _unit(np.random.default_rng(i), (1024,)).tolist()}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"data": data})

    reqs: list = []
    emb = ClusterDenseEmbedder(settings=_settings(), client=_capturing_client(handler, reqs))
    out = emb.embed_documents(["one", "two"])

    assert len(out) == 2 and out[0].shape == (1024,)
    assert "return_token_embeddings" not in reqs[0]
    assert reqs[0]["model"] == "Qwen/Qwen3-Embedding-0.6B"


def test_token_flag_unwraps_batch_dimension():
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode())
        data = [
            {"index": i, "embedding": [_unit(np.random.default_rng(i), (5, 1024)).tolist()]}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"data": data})

    reqs: list = []
    emb = ClusterDenseEmbedder(settings=_settings(), client=_capturing_client(handler, reqs))
    out = emb.embed_documents_tokens(["hello world"])

    assert reqs[0]["return_token_embeddings"] is True
    assert out[0].shape == (5, 1024)  # (1, n_tokens, dim) unwrapped


def test_response_is_reassembled_by_index_not_position():
    """A reordered response must not attach embeddings to the wrong texts."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Deliberately reversed: item 1 first.
        a = _unit(np.random.default_rng(7), (1024,))
        b = _unit(np.random.default_rng(9), (1024,))
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": b.tolist()},
                           {"index": 0, "embedding": a.tolist()}]},
        )

    emb = ClusterDenseEmbedder(
        settings=_settings(), client=_capturing_client(handler, [])
    )
    out = emb.embed_documents(["first", "second"])
    assert np.allclose(out[0], _unit(np.random.default_rng(7), (1024,)))
    assert np.allclose(out[1], _unit(np.random.default_rng(9), (1024,)))


def test_query_prepends_the_instruction():
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode())
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": _unit(np.random.default_rng(0), (1024,)).tolist()}]}
        )

    reqs: list = []
    emb = ClusterDenseEmbedder(settings=_settings(), client=_capturing_client(handler, reqs))
    emb.embed_query("what is a lever")
    assert reqs[0]["input"] == ["Instruct: test\nQuery: what is a lever"]


def test_pooled_paths_normalise_an_unnormalised_endpoint():
    """The endpoint does NOT return unit vectors — the client must normalise.

    Measured live 2026-07 (Qwen3-Embedding-0.6B): pooled query norm ≈ 70, pooled passage
    ≈ 84. The index side (``late_chunk_embedder._finish``) always normalised; the query
    side did not, so a bare ``query @ doc`` was off by ~6,000. Invisible under Qdrant's
    COSINE distance, fatal for any dot-product consumer.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode())
        # Deliberately UNNORMALISED: scale a unit vector by 100.
        data = [
            {"index": i, "embedding": (_unit(np.random.default_rng(i), (1024,)) * 100).tolist()}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"data": data})

    emb = ClusterDenseEmbedder(settings=_settings(), client=_capturing_client(handler, []))

    docs = emb.embed_documents(["one", "two"])
    assert all(np.isclose(np.linalg.norm(d), 1.0, atol=1e-5) for d in docs)

    q = emb.embed_query("one")
    assert np.isclose(np.linalg.norm(q), 1.0, atol=1e-5)
    # Same text → the two lanes agree once normalised (they differ only by the instruction).
    assert float(np.dot(q, docs[0])) > 0.5


def test_per_token_path_stays_raw():
    """Per-token vectors must NOT be normalised: the mean is taken before normalising."""

    def handler(request: httpx.Request) -> httpx.Response:
        raw = (_unit(np.random.default_rng(3), (5, 1024)) * 50).tolist()
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [raw]}]})

    emb = ClusterDenseEmbedder(settings=_settings(), client=_capturing_client(handler, []))
    toks = emb.embed_documents_tokens(["hello world"])
    assert toks[0].shape == (5, 1024)
    assert np.linalg.norm(toks[0][0]) > 10.0, "per-token vectors must stay unnormalised"


def test_missing_url_is_loud():
    with pytest.raises(ValueError, match="sv_embed_url"):
        ClusterDenseEmbedder(settings=_settings(sv_embed_url=""))


# ── Factory ────────────────────────────────────────────────────────────────

def test_factory_returns_stub_under_stub_flag():
    reset_cluster_embedder()
    emb = get_cluster_embedder(settings=_settings(use_stub_embedder=True))
    assert isinstance(emb, StubClusterEmbedder)


def test_factory_returns_cluster_client_when_url_set():
    reset_cluster_embedder()
    emb = get_cluster_embedder(settings=_settings(use_stub_embedder=False))
    assert isinstance(emb, ClusterDenseEmbedder)


def test_factory_is_memoised_and_resettable():
    reset_cluster_embedder()
    first = get_cluster_embedder(settings=_settings(use_stub_embedder=True))
    assert get_cluster_embedder(settings=_settings(use_stub_embedder=True)) is first
    reset_cluster_embedder()
    assert get_cluster_embedder(settings=_settings(use_stub_embedder=True)) is not first
