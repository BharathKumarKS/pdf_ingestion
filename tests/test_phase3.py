"""Phase 3 tests — ColPali, image store, graph builder, orchestration."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from src.core.config import Settings
from src.pdf_ingestion.colpali_embedder import StubColPaliEmbedder, get_colpali_embedder
from src.pdf_ingestion.graph_builder import StubGraphBuilder, get_graph_builder
from src.pdf_ingestion.image_store import LocalImageStore


# ── Fixtures ------------------------------------------------------------------

@pytest.fixture
def p3_settings(tmp_path):
    return Settings(
        use_stub_embedder=True,
        use_stub_llm=True,
        use_stub_colpali=True,
        use_stub_graph=True,
        qdrant_in_memory=True,
        sqlite_url=f"sqlite:///{tmp_path}/test_p3.db",
        page_images_dir=str(tmp_path / "page_images"),
        debug=False,
    )


@pytest.fixture
def local_image_store(tmp_path):
    return LocalImageStore(base_dir=str(tmp_path / "images"))


# ── ColPali embedder ----------------------------------------------------------

class TestColPaliEmbedder:
    def test_stub_factory_returns_stub(self, p3_settings):
        emb = get_colpali_embedder(p3_settings)
        assert isinstance(emb, StubColPaliEmbedder)

    def test_stub_embed_pages_shape(self):
        emb = StubColPaliEmbedder()
        # Pass opaque objects — stub only uses id()
        results = emb.embed_pages([object(), object(), object()])
        assert len(results) == 3
        for patches in results:
            assert patches.ndim == 2
            assert patches.shape[1] == StubColPaliEmbedder.STUB_DIM

    def test_stub_embed_query_shape(self):
        emb = StubColPaliEmbedder()
        patches = emb.embed_query_image(object())
        assert patches.ndim == 2
        assert patches.shape == (StubColPaliEmbedder.STUB_PATCHES, StubColPaliEmbedder.STUB_DIM)

    def test_stub_patches_are_normalised(self):
        emb = StubColPaliEmbedder()
        patches = emb.embed_pages([object()])[0]
        norms = np.linalg.norm(patches, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_stub_patch_dim_property(self):
        assert StubColPaliEmbedder().patch_dim == StubColPaliEmbedder.STUB_DIM


# ── Image store ---------------------------------------------------------------

class TestImageStore:
    def test_save_and_get_roundtrip(self, local_image_store):
        data = b"\x89PNG\r\nfake-image-bytes"
        key  = local_image_store.save("doc-001", 1, data)
        assert local_image_store.get(key) == data

    def test_key_format(self, local_image_store):
        key = local_image_store.save("doc-abc", 3, b"data")
        assert "doc-abc" in key
        assert "page_0003" in key
        assert key.endswith(".png")

    def test_multiple_pages(self, local_image_store):
        for pg in range(1, 6):
            local_image_store.save("doc-multi", pg, b"page" + str(pg).encode())
        for pg in range(1, 6):
            key   = f"doc-multi/page_{pg:04d}.png"
            data  = local_image_store.get(key)
            assert data == b"page" + str(pg).encode()

    def test_overwrite_same_key(self, local_image_store):
        local_image_store.save("doc-ow", 1, b"original")
        local_image_store.save("doc-ow", 1, b"updated")
        key  = "doc-ow/page_0001.png"
        assert local_image_store.get(key) == b"updated"


# ── Graph builder -------------------------------------------------------------

class TestGraphBuilder:
    def _make_chunks(self, n=5):
        from src.pdf_ingestion.chunker import TextChunk
        return [
            TextChunk(
                chunk_id=f"chunk-{i}",
                document_id="doc-graph",
                tenant_id="global",
                chunk_index=i,
                text=f"Physics text about Newton's laws and force number {i}.",
                char_start=i * 100,
                char_end=(i + 1) * 100,
                token_count=20,
                page_number=i + 1,
            )
            for i in range(n)
        ]

    def test_stub_factory(self, p3_settings):
        builder = get_graph_builder(p3_settings)
        assert isinstance(builder, StubGraphBuilder)

    def test_stub_build_graph_returns_summary(self):
        builder = StubGraphBuilder()
        chunks  = self._make_chunks(5)
        result  = builder.build_graph("doc-g", "global", chunks, "Feynman Lectures")
        assert result["chunk_nodes"] == 5
        assert result["concept_nodes"] > 0

    def test_stub_graph_search_returns_results(self):
        builder = StubGraphBuilder()
        chunks  = self._make_chunks(3)
        builder.build_graph("doc-g", "global", chunks)
        results = builder.graph_search("Newton's law", "global", limit=3)
        assert isinstance(results, list)
        for r in results:
            assert "chunk_id" in r
            assert "concept_path" in r

    def test_stub_graph_search_empty_when_no_tenant_match(self):
        builder = StubGraphBuilder()
        chunks  = self._make_chunks(2)
        builder.build_graph("doc-g", "user_xyz", chunks)
        # global chunks are always returned; user_xyz tenant ones too
        results = builder.graph_search("any", "global", limit=5)
        assert isinstance(results, list)


# ── PageImage store -----------------------------------------------------------

class TestPageImageStore:
    def _make_png_bytes(self):
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _ingest_doc(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.store import ingest_pdf
        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=p3_settings,
        )
        return result["document_id"]

    def test_save_page_images_creates_records(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.parser import PageContent
        from src.pdf_ingestion.store import DocumentStore

        doc_id = self._ingest_doc(p3_settings, sample_pdf)
        store  = DocumentStore(settings=p3_settings)

        png = self._make_png_bytes()
        pages = [
            PageContent(page_number=1, text="page 1", image_bytes=png),
            PageContent(page_number=2, text="page 2", image_bytes=png),
        ]
        records = store.save_page_images(doc_id, pages, settings=p3_settings)
        assert len(records) == 2
        assert all(r.document_id == doc_id for r in records)
        assert records[0].page_number == 1
        assert records[1].page_number == 2

    def test_save_page_images_idempotent(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.parser import PageContent
        from src.pdf_ingestion.store import DocumentStore

        doc_id = self._ingest_doc(p3_settings, sample_pdf)
        store  = DocumentStore(settings=p3_settings)

        png   = self._make_png_bytes()
        pages = [PageContent(page_number=1, text="p1", image_bytes=png)]

        store.save_page_images(doc_id, pages, settings=p3_settings)
        store.save_page_images(doc_id, pages, settings=p3_settings)

        active = store.get_page_images(doc_id)
        assert len(active) == 1  # deactivation guard prevents doubling

    def test_get_page_images_returns_active_only(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.parser import PageContent
        from src.pdf_ingestion.store import DocumentStore

        doc_id = self._ingest_doc(p3_settings, sample_pdf)
        store  = DocumentStore(settings=p3_settings)

        png   = self._make_png_bytes()
        pages = [PageContent(page_number=i, text=f"p{i}", image_bytes=png) for i in range(1, 4)]
        store.save_page_images(doc_id, pages, settings=p3_settings)

        active = store.get_page_images(doc_id)
        assert len(active) == 3


# ── Phase 3 orchestration -----------------------------------------------------

class TestPhase3Orchestration:
    def test_generate_phase3_invalid_doc_raises(self, p3_settings):
        from src.pdf_ingestion.store import generate_phase3_artifacts
        with pytest.raises(ValueError, match="not found"):
            generate_phase3_artifacts("nonexistent-id", settings=p3_settings)

    def test_generate_phase3_sets_status_ready(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.store import DocumentStore, generate_phase3_artifacts, ingest_pdf
        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=p3_settings,
        )
        doc_id = result["document_id"]

        p3_result = generate_phase3_artifacts(
            document_id=doc_id,
            pdf_path=str(sample_pdf),
            settings=p3_settings,
        )
        assert p3_result["colpali_status"] == "ready"
        assert "graph_stats" in p3_result

    def test_generate_phase3_returns_summary_keys(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.store import generate_phase3_artifacts, ingest_pdf
        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=p3_settings,
        )
        p3 = generate_phase3_artifacts(
            document_id=result["document_id"],
            pdf_path=str(sample_pdf),
            settings=p3_settings,
        )
        for key in ("document_id", "filename", "visual_vectors", "graph_stats", "colpali_status"):
            assert key in p3

    def test_colpali_status_update(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.store import DocumentStore, ingest_pdf
        from sqlmodel import Session, select
        from src.core.database import Document, get_engine

        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=p3_settings,
        )
        doc_id = result["document_id"]
        store  = DocumentStore(settings=p3_settings)
        store.update_colpali_status(doc_id, "processing")

        with Session(get_engine(p3_settings)) as session:
            doc = session.get(Document, doc_id)
        assert doc.colpali_status == "processing"


# ── Phase 3 regression ────────────────────────────────────────────────────────

class TestPhase3Regression:
    def test_phase1_and_phase2_still_work(self, p3_settings, sample_pdf):
        from src.pdf_ingestion.store import (
            DocumentStore,
            generate_phase2_artifacts,
            ingest_pdf,
        )
        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=p3_settings,
        )
        assert result["chunk_count"] > 0

        p2 = generate_phase2_artifacts(result["document_id"], settings=p3_settings)
        assert p2["cards_generated"] > 0
        assert p2["raptor_nodes"] >= 0

    def test_page_image_table_exists(self, p3_settings):
        """PageImage table is created without error."""
        from src.core.database import get_engine
        engine = get_engine(p3_settings)
        from sqlalchemy import inspect
        inspector = inspect(engine)
        assert "page_images" in inspector.get_table_names()

    def test_colpali_collection_created(self, p3_settings):
        from src.core.database import get_qdrant
        client = get_qdrant(p3_settings)
        names  = {c.name for c in client.get_collections().collections}
        assert p3_settings.colpali_collection in names
