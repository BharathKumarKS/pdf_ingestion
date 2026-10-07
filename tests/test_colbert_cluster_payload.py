"""Payload-contract tests for the CLUSTER ColBERT embedder.

`tests/test_colbert_embedder.py` covers only `StubColBERTEmbedder`, which is why a real
bug survived there: `ClusterColBERTEmbedder._post` sent the parameter `encoding_type`,
but the SV cluster endpoint ignores that key entirely and expects **`is_query`** (bool).

Verified against the live cluster on 2026-10-06:

    encoding_type='query'     -> 8x128     (same as the document encoding)
    encoding_type='document'  -> 8x128
    is_query=True             -> 32x128    (query padding + augmentation)
    is_query=False            -> 8x128

    query-encoded == doc-encoded ? True    <- encoding_type is IGNORED

So every query we ever encoded went through the DOCUMENT encoder — discarding exactly the
query/document asymmetry that late interaction exists to exploit.

These tests pin the payload shape so that cannot regress.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.core.config import Settings
from src.pdf_ingestion.colbert_embedder import ClusterColBERTEmbedder


def _settings() -> Settings:
    return Settings(
        use_stub_colbert=False,
        colbert_enabled=True,
        colbert_model="colbert-ir/colbertv2.0",
        sv_colbert_url="http://cluster.invalid/embed-text/v1/multivector-embeddings",
        qdrant_in_memory=True,
        sqlite_url="sqlite:///./data/test_synapse.db",
    )


def _capture(monkeypatch, data, method, *args, **kwargs):
    """Run `method` with httpx.post stubbed; return (payload, sent_batches)."""
    import httpx

    sent = []

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": data}

    def fake_post(url, **kw):
        sent.append(kw.get("json", {}))
        return FakeResp()

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = ClusterColBERTEmbedder(_settings())
    getattr(emb, method)(*args, **kwargs)
    return sent[0], sent


# ── the parameter NAME and VALUE ─────────────────────────────────────────────

class TestPayloadContract:
    def test_query_sends_is_query_true(self, monkeypatch):
        payload, _ = _capture(
            monkeypatch, [{"embedding": [[0.1, 0.2]], "index": 0}],
            "embed_query", "what is kinetic energy?",
        )
        assert payload.get("is_query") is True, (
            "the cluster expects is_query=True for queries; without it the query is "
            f"encoded as a passage. payload={payload!r}"
        )

    def test_passages_send_is_query_false(self, monkeypatch):
        payload, _ = _capture(
            monkeypatch, [{"embedding": [[0.1, 0.2]], "index": 0}],
            "embed_passages", ["a physics passage"],
        )
        assert payload.get("is_query") is False, f"payload={payload!r}"

    def test_encoding_type_is_not_sent(self, monkeypatch):
        """The key the server ignores must not linger in the payload."""
        q, _ = _capture(monkeypatch, [{"embedding": [[0.1, 0.2]], "index": 0}],
                        "embed_query", "q")
        p, _ = _capture(monkeypatch, [{"embedding": [[0.1, 0.2]], "index": 0}],
                        "embed_passages", ["p"])
        assert "encoding_type" not in q, q
        assert "encoding_type" not in p, p

    def test_model_and_input_still_sent(self, monkeypatch):
        payload, _ = _capture(monkeypatch, [{"embedding": [[0.1, 0.2]], "index": 0}],
                              "embed_query", "kinetic energy")
        assert payload["model"] == "colbert-ir/colbertv2.0"
        assert payload["input"] == ["kinetic energy"]


# ── the response ORDER contract ──────────────────────────────────────────────

class TestResponseOrder:
    def test_results_follow_item_index_not_position(self, monkeypatch):
        """The server returns `index`; attaching by position silently mis-assigns vectors.

        Send two items with the indices swapped relative to their array order. Ordered
        correctly (by index) the first matrix is index 0's -> [1, 0]; by position it
        would be index 1's -> [0, 1].
        """
        data = [
            {"embedding": [[0.0, 1.0]], "index": 1},   # appears FIRST, is index 1
            {"embedding": [[1.0, 0.0]], "index": 0},   # appears SECOND, is index 0
        ]
        emb = ClusterColBERTEmbedder(_settings())
        import httpx

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"data": data}

        monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResp())
        mats = emb.embed_passages(["first text", "second text"])
        assert len(mats) == 2
        np.testing.assert_allclose(mats[0][0], [1.0, 0.0], atol=1e-6)
        np.testing.assert_allclose(mats[1][0], [0.0, 1.0], atol=1e-6)


# ── the batch-size contract ──────────────────────────────────────────────────

class TestBatchSize:
    def test_batch_size_within_cluster_limit(self, monkeypatch):
        """The ColBERT tab documents 'Max 8 inputs per request'."""
        _, payloads = _capture(
            monkeypatch, [{"embedding": [[0.1, 0.2]], "index": 0}],
            "embed_passages", [f"passage {i}" for i in range(20)],
        )
        assert payloads, "no request was sent"
        for p in payloads:
            assert len(p["input"]) <= 8, (
                f"sent {len(p['input'])} inputs in one request; cluster max is 8"
            )
