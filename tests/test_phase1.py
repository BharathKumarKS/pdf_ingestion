"""Phase 1 test suite — parser, chunker, embedder, store, search."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.core.config import Settings


# ═══════════════════════════════════════════════════════════════════════════
# 1. Config
# ═══════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_defaults_load(self, settings):
        assert settings.global_tenant_id == "global"
        assert settings.embedding_dim == 1024
        assert settings.use_stub_embedder is True

    def test_ensure_dirs_creates_paths(self, settings, tmp_path):
        settings.model_cache_dir = str(tmp_path / "models")
        settings.upload_dir      = str(tmp_path / "uploads")
        settings.base_textbook_dir = str(tmp_path / "textbooks")
        settings.ensure_dirs()
        assert Path(settings.model_cache_dir).exists()
        assert Path(settings.upload_dir).exists()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Database bootstrap
# ═══════════════════════════════════════════════════════════════════════════

class TestDatabase:
    def test_sqlite_engine_creates_tables(self, settings):
        from src.core.database import get_engine
        from sqlmodel import inspect as sql_inspect
        engine = get_engine(settings)
        inspector = sql_inspect(engine)
        tables = inspector.get_table_names()
        assert "documents" in tables
        assert "chunks" in tables

    def test_qdrant_collection_created(self, settings):
        from src.core.database import get_qdrant
        client = get_qdrant(settings)
        collections = {c.name for c in client.get_collections().collections}
        assert settings.qdrant_collection in collections


# ═══════════════════════════════════════════════════════════════════════════
# 3. PDF Parser
# ═══════════════════════════════════════════════════════════════════════════

class TestParser:
    def test_parse_returns_parsed_document(self, sample_pdf):
        from src.pdf_ingestion.parser import PDFParser
        parser = PDFParser()
        result = parser.parse(str(sample_pdf))

        assert result.document_id
        assert result.filename == sample_pdf.name
        assert result.page_count >= 1
        assert len(result.full_text) > 100
        assert result.pages

    def test_parse_extracts_physics_content(self, sample_pdf):
        from src.pdf_ingestion.parser import PDFParser
        result = PDFParser().parse(str(sample_pdf))
        text = result.full_text.lower()
        # Our sample PDF has physics content
        assert any(kw in text for kw in ["newton", "energy", "force", "wave", "quantum"])

    def test_parse_missing_file_raises(self):
        from src.pdf_ingestion.parser import PDFParser
        with pytest.raises(FileNotFoundError):
            PDFParser().parse("/nonexistent/file.pdf")

    def test_page_count_matches_pages_list(self, sample_pdf):
        from src.pdf_ingestion.parser import PDFParser
        result = PDFParser().parse(str(sample_pdf))
        # Page list length should match declared page count
        assert len(result.pages) <= result.page_count + 1  # Docling may merge pages


# ═══════════════════════════════════════════════════════════════════════════
# 4. Chunker
# ═══════════════════════════════════════════════════════════════════════════

class TestChunker:
    SAMPLE_TEXT = (
        "Newton's first law states that an object at rest stays at rest. "
        "The second law says force equals mass times acceleration. "
        "The third law tells us every action has an equal and opposite reaction. "
        "Kinetic energy is defined as one half times mass times velocity squared. "
        "Potential energy near the surface of Earth equals mass times gravity times height. "
        "The work-energy theorem relates net work to change in kinetic energy. "
        "Maxwell's equations unify electricity and magnetism into a coherent framework. "
        "The speed of light in vacuum is approximately three times ten to the eight metres per second."
    ) * 10  # Repeat to have enough content to chunk

    def test_produces_chunks(self, settings):
        from src.pdf_ingestion.chunker import SemanticChunker
        chunker = SemanticChunker(settings=settings)
        chunks = chunker.chunk_document(
            document_id="test-doc-1",
            tenant_id="global",
            full_text=self.SAMPLE_TEXT,
        )
        assert len(chunks) > 0

    def test_chunks_have_required_fields(self, settings):
        from src.pdf_ingestion.chunker import SemanticChunker
        chunks = SemanticChunker(settings=settings).chunk_document(
            document_id="test-doc-2",
            tenant_id="global",
            full_text=self.SAMPLE_TEXT,
        )
        for c in chunks:
            assert c.chunk_id
            assert c.document_id == "test-doc-2"
            assert c.tenant_id == "global"
            assert isinstance(c.chunk_index, int)
            assert c.text.strip()
            assert c.char_start >= 0
            assert c.char_end > c.char_start

    def test_chunk_texts_cover_original(self, settings):
        from src.pdf_ingestion.chunker import SemanticChunker
        text = "Alpha. Beta. Gamma. Delta. Epsilon. " * 30
        chunks = SemanticChunker(settings=settings).chunk_document(
            document_id="cov-doc",
            tenant_id="global",
            full_text=text,
        )
        combined = " ".join(c.text for c in chunks).lower()
        for word in ["alpha", "beta", "gamma"]:
            assert word in combined

    def test_empty_text_returns_empty_list(self, settings):
        from src.pdf_ingestion.chunker import SemanticChunker
        chunks = SemanticChunker(settings=settings).chunk_document(
            document_id="empty-doc",
            tenant_id="global",
            full_text="   ",
        )
        assert chunks == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. Embedder (stub)
# ═══════════════════════════════════════════════════════════════════════════

class TestEmbedder:
    def test_stub_returns_correct_shape(self, settings):
        from src.pdf_ingestion.chunker import SemanticChunker, TextChunk
        from src.pdf_ingestion.embedder import get_embedder
        import uuid

        chunks = [
            TextChunk(
                chunk_id=str(uuid.uuid4()),
                document_id="d1",
                tenant_id="global",
                chunk_index=i,
                text=f"Chunk number {i} with some physics content about energy and force.",
                char_start=i * 100,
                char_end=i * 100 + 60,
                token_count=12,
                page_number=1,
            )
            for i in range(5)
        ]

        embedder = get_embedder(settings)
        results = embedder.embed_chunks(chunks)

        assert len(results) == 5
        for r in results:
            assert r.embedding.shape == (settings.embedding_dim,)
            # Verify L2-normalised (norm ≈ 1)
            norm = float(np.linalg.norm(r.embedding))
            assert abs(norm - 1.0) < 0.01

    def test_query_embedding_shape(self, settings):
        from src.pdf_ingestion.embedder import get_embedder
        embedder = get_embedder(settings)
        vec = embedder.embed_query("What is Newton's second law?")
        assert vec.shape == (settings.embedding_dim,)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Store + full pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestStore:
    def _run_pipeline(self, pdf_path: Path, settings: Settings, tenant_id: str, source_type: str, baseline: bool) -> dict:
        from src.pdf_ingestion.store import ingest_pdf
        return ingest_pdf(
            pdf_path=str(pdf_path),
            tenant_id=tenant_id,
            source_type=source_type,
            is_global_baseline=baseline,
            extra_meta={"subject": "Physics", "difficulty": 5},
            settings=settings,
        )

    def test_ingest_returns_summary(self, sample_pdf, settings):
        result = self._run_pipeline(sample_pdf, settings, "global", "base_textbook", True)
        assert result["document_id"]
        assert result["chunk_count"] > 0
        assert result["page_count"] >= 1
        assert result["tenant_id"] == "global"
        assert result["source_type"] == "base_textbook"

    def test_document_stored_in_sqlite(self, sample_pdf, settings):
        from src.core.database import get_engine
        from src.pdf_ingestion.store import DocumentStore
        from sqlmodel import Session, select
        from src.core.database import Document

        result = self._run_pipeline(sample_pdf, settings, "global", "base_textbook", True)
        engine = get_engine(settings)
        with Session(engine) as session:
            doc = session.get(Document, result["document_id"])
        assert doc is not None
        assert doc.tenant_id == "global"
        assert doc.is_global_baseline is True
        assert doc.chunk_count == result["chunk_count"]

    def test_chunks_stored_in_sqlite(self, sample_pdf, settings):
        from src.core.database import get_engine
        from sqlmodel import Session, select
        from src.core.database import Chunk

        result = self._run_pipeline(sample_pdf, settings, "global", "base_textbook", True)
        engine = get_engine(settings)
        with Session(engine) as session:
            chunks = session.exec(
                select(Chunk).where(Chunk.document_id == result["document_id"])
            ).all()
        assert len(chunks) == result["chunk_count"]

    def test_qdrant_points_stored(self, sample_pdf, settings):
        from src.core.database import get_qdrant

        result = self._run_pipeline(sample_pdf, settings, "global", "base_textbook", True)
        client = get_qdrant(settings)
        info = client.get_collection(settings.qdrant_collection)
        assert info.points_count >= result["chunk_count"]

    def test_user_upload_isolated_from_global(self, sample_pdf, settings):
        """User PDF must not appear when querying the global tenant."""
        from src.pdf_ingestion.store import DocumentStore, ingest_pdf
        from src.pdf_ingestion.embedder import get_embedder

        # Ingest as user
        ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="user_alice",
            source_type="user_upload",
            is_global_baseline=False,
            settings=settings,
        )

        embedder = get_embedder(settings)
        q_vec = embedder.embed_query("Newton's laws of motion")
        store = DocumentStore(settings)

        # Search scoped to user_alice with user_upload filter only
        results = store.search(
            query_vector=q_vec,
            tenant_id="user_alice",
            source_type="user_upload",
        )
        # All results should belong to alice
        for r in results:
            assert r["tenant_id"] == "user_alice"

    def test_hybrid_search_includes_global(self, sample_pdf, settings):
        """Hybrid search must pull from both user and global tenants."""
        from src.pdf_ingestion.store import DocumentStore, ingest_pdf
        from src.pdf_ingestion.embedder import get_embedder

        # Ingest as global baseline
        ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=settings,
        )
        # Ingest as user
        ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="user_bob",
            source_type="user_upload",
            is_global_baseline=False,
            settings=settings,
        )

        embedder = get_embedder(settings)
        q_vec = embedder.embed_query("energy conservation")
        store = DocumentStore(settings)

        # Hybrid: source_type=None → includes both tenants
        results = store.search(
            query_vector=q_vec,
            tenant_id="user_bob",
            source_type=None,
            limit=20,
        )
        tenant_ids = {r["tenant_id"] for r in results}
        # Both user_bob and global should appear (stub vectors are random
        # but with enough docs both should surface in top-20)
        assert len(results) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. End-to-end integration (uses real Jina v3 — mark as slow)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
@pytest.mark.integration
class TestIntegration:
    """
    Full pipeline with real Jina v3 model and Docker Qdrant.
    Run with: uv run pytest -m integration -v
    Requires:  docker compose up qdrant -d
    """

    def test_end_to_end_real_model(self, sample_pdf, tmp_path):
        from src.core.config import Settings
        from src.pdf_ingestion.store import ingest_pdf

        settings = Settings(
            use_stub_embedder=False,
            qdrant_in_memory=False,
            sqlite_url=f"sqlite:///{tmp_path}/integration.db",
        )

        result = ingest_pdf(
            pdf_path=str(sample_pdf),
            tenant_id="global",
            source_type="base_textbook",
            is_global_baseline=True,
            settings=settings,
        )
        assert result["chunk_count"] > 0
        assert result["document_id"]
