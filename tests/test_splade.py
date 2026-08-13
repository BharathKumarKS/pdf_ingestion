"""Tests for SPLADE sparse embedder and hybrid search (Phase 4)."""
from __future__ import annotations

import numpy as np
import pytest


class TestStubSpladeEmbedder:
    def test_encode_sparse_returns_indices_and_values(self):
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder
        emb = StubSpladeEmbedder()
        sv = emb.encode_sparse("Newton's second law")
        assert len(sv.indices) > 0
        assert len(sv.values) == len(sv.indices)
        assert all(v > 0 for v in sv.values)

    def test_encode_sparse_deterministic(self):
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder
        emb = StubSpladeEmbedder()
        sv1 = emb.encode_sparse("kinetic energy")
        sv2 = emb.encode_sparse("kinetic energy")
        assert sv1.indices == sv2.indices
        assert sv1.values  == sv2.values

    def test_encode_batch(self):
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder
        emb = StubSpladeEmbedder()
        texts = ["Newton's law", "kinetic energy", "wave propagation"]
        results = emb.encode_batch(texts)
        assert len(results) == 3
        for sv in results:
            assert len(sv.indices) > 0

    def test_to_qdrant(self):
        from qdrant_client.models import SparseVector as QSparseVector
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder
        emb = StubSpladeEmbedder()
        sv = emb.encode_sparse("test text")
        qsv = sv.to_qdrant()
        assert isinstance(qsv, QSparseVector)
        assert qsv.indices == sv.indices
        assert qsv.values  == sv.values

    def test_different_texts_different_vectors(self):
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder
        emb = StubSpladeEmbedder()
        sv1 = emb.encode_sparse("momentum conservation")
        sv2 = emb.encode_sparse("electromagnetic induction")
        assert sv1.indices != sv2.indices


class TestSpladeFactory:
    def test_get_splade_returns_stub_when_flag_set(self):
        from src.core.config import Settings
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder, get_splade_embedder
        cfg = get_splade_embedder.__wrapped__ if hasattr(get_splade_embedder, '__wrapped__') else None
        emb = get_splade_embedder(Settings(use_stub_splade=True))
        assert isinstance(emb, StubSpladeEmbedder)

    def test_get_splade_returns_stub_when_disabled(self):
        from src.core.config import Settings
        from src.pdf_ingestion.splade_embedder import StubSpladeEmbedder, get_splade_embedder
        emb = get_splade_embedder(Settings(splade_enabled=False))
        assert isinstance(emb, StubSpladeEmbedder)

    def test_singleton(self):
        from src.pdf_ingestion.splade_embedder import get_splade_embedder
        e1 = get_splade_embedder()
        e2 = get_splade_embedder()
        assert e1 is e2

    def test_reset_clears_singleton(self):
        from src.pdf_ingestion.splade_embedder import get_splade_embedder, reset_splade_embedder
        e1 = get_splade_embedder()
        reset_splade_embedder()
        e2 = get_splade_embedder()
        assert e1 is not e2


class TestHybridIngest:
    """Verify SPLADE vectors are included in Qdrant points during ingest."""

    def test_ingest_with_splade_creates_named_vectors(self, tmp_path):
        import os
        from src.core.config import Settings
        from src.core.database import get_qdrant, reset_singletons
        from src.pdf_ingestion.splade_embedder import reset_splade_embedder
        from src.pdf_ingestion.store import ingest_pdf

        reset_singletons()
        reset_splade_embedder()

        db_path = str(tmp_path / "test.db")
        cfg = Settings(
            qdrant_in_memory=True,
            sqlite_url=f"sqlite:///{db_path}",
            use_stub_embedder=True,
            use_stub_llm=True,
            use_stub_splade=True,
            splade_enabled=True,
        )

        r = ingest_pdf(
            pdf_path="tests/data/sample_physics.pdf",
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=False,
            settings=cfg,
        )
        assert r["chunk_count"] > 0

        # Verify collection has sparse vector config
        qdrant = get_qdrant(cfg)
        info = qdrant.get_collection(cfg.qdrant_collection)
        assert info.config.params.sparse_vectors is not None or \
               "sparse" in (info.config.params.sparse_vectors or {})

    def test_search_with_splade_enabled(self, tmp_path):
        import numpy as np
        from src.core.config import Settings
        from src.core.database import reset_singletons
        from src.pdf_ingestion.splade_embedder import reset_splade_embedder
        from src.pdf_ingestion.store import DocumentStore, ingest_pdf

        reset_singletons()
        reset_splade_embedder()

        db_path = str(tmp_path / "test.db")
        cfg = Settings(
            qdrant_in_memory=True,
            sqlite_url=f"sqlite:///{db_path}",
            use_stub_embedder=True,
            use_stub_llm=True,
            use_stub_splade=True,
            splade_enabled=True,
        )

        r = ingest_pdf(
            pdf_path="tests/data/sample_physics.pdf",
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=False,
            settings=cfg,
        )

        store = DocumentStore(settings=cfg)
        q_vec = np.random.rand(cfg.embedding_dim).astype(np.float32)
        q_vec /= np.linalg.norm(q_vec)

        results = store.search(
            query_vector=q_vec,
            tenant_id="global",
            limit=3,
            query_text="What is Newton's second law?",
        )
        assert isinstance(results, list)
