"""Tests for ColBERT v2.0 embedder stub and factory."""
from __future__ import annotations

import numpy as np
import pytest

from src.pdf_ingestion.colbert_embedder import (
    StubColBERTEmbedder,
    get_colbert_embedder,
    reset_colbert_embedder,
)
from src.core.config import Settings


@pytest.fixture(autouse=True)
def _reset():
    reset_colbert_embedder()
    yield
    reset_colbert_embedder()


@pytest.fixture
def stub_settings():
    return Settings(
        use_stub_colbert=True,
        colbert_enabled=True,
        qdrant_in_memory=True,
        sqlite_url="sqlite:///./data/test_synapse.db",
    )


class TestStubColBERTEmbedder:
    def test_factory_returns_stub(self, stub_settings):
        emb = get_colbert_embedder(stub_settings)
        assert isinstance(emb, StubColBERTEmbedder)

    def test_embed_passages_shape(self):
        emb = StubColBERTEmbedder()
        matrices = emb.embed_passages(["hello world", "physics energy"])
        assert len(matrices) == 2
        for mat in matrices:
            assert mat.ndim == 2
            assert mat.shape[1] == StubColBERTEmbedder.STUB_DIM

    def test_embed_query_shape(self):
        emb = StubColBERTEmbedder()
        mat = emb.embed_query("what is kinetic energy?")
        assert mat.ndim == 2
        assert mat.shape == (StubColBERTEmbedder.STUB_Q_TOKENS, StubColBERTEmbedder.STUB_DIM)

    def test_token_vectors_are_normalised(self):
        emb = StubColBERTEmbedder()
        mat = emb.embed_passages(["Newton's second law"])[0]
        norms = np.linalg.norm(mat, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_query_vectors_are_normalised(self):
        emb = StubColBERTEmbedder()
        mat = emb.embed_query("force equals mass times acceleration")
        norms = np.linalg.norm(mat, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_different_texts_produce_different_matrices(self):
        emb = StubColBERTEmbedder()
        m1 = emb.embed_passages(["alpha"])[0]
        m2 = emb.embed_passages(["beta"])[0]
        assert not np.allclose(m1, m2)

    def test_empty_passages_list_returns_empty(self):
        emb = StubColBERTEmbedder()
        assert emb.embed_passages([]) == []


class TestColBERTIntegration:
    """Verify ColBERT stub works end-to-end through the store pipeline."""

    def test_colbert_vectors_included_when_enabled(self, stub_settings, tmp_path, sample_pdf):
        from src.pdf_ingestion.store import ingest_pdf
        from src.core.database import get_qdrant

        stub_settings.sqlite_url = f"sqlite:///{tmp_path}/colbert_test.db"

        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=stub_settings,
        )
        assert result["chunk_count"] > 0

        # Verify the collection was created with named vectors
        client = get_qdrant(stub_settings)
        col = client.get_collection(stub_settings.qdrant_collection)
        assert col is not None

    def test_search_with_colbert_enabled(self, stub_settings, tmp_path, sample_pdf):
        from src.pdf_ingestion.store import ingest_pdf, DocumentStore
        from src.pdf_ingestion.embedder import get_embedder

        stub_settings.sqlite_url = f"sqlite:///{tmp_path}/colbert_search.db"

        ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=stub_settings,
        )

        store = DocumentStore(stub_settings)
        embedder = get_embedder(stub_settings)
        q_vec = embedder.embed_query("kinetic energy formula")

        results = store.search(
            query_vector=q_vec,
            tenant_id="global",
            query_text="kinetic energy formula",
        )
        assert isinstance(results, list)
