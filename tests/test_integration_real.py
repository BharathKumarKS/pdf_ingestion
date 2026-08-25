"""
Integration test: real Nomic embed v1.5 + ColBERT v2.0, in-memory Qdrant, real sample PDF.
No Docker required. Downloads Nomic model on first run (~270 MB).

Run: uv run pytest tests/test_integration_real.py -v -s
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Override the autouse conftest reset so integration state persists ─────
# The main conftest resets DB singletons between every test (needed for unit
# tests).  Integration tests share Qdrant/SQLite state across the class, so
# we override the fixture here with a no-op for this file only.
@pytest.fixture(autouse=True)
def reset_db_singletons():
    yield  # intentional no-op — integration tests manage their own state


# ── Module-level fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_settings(tmp_path_factory):
    """Real Nomic embed v1.5 + in-memory Qdrant + isolated SQLite for this module."""
    from src.core.database import reset_singletons
    reset_singletons()  # start clean
    from src.core.config import Settings
    db_path = tmp_path_factory.mktemp("integration") / "real.db"
    return Settings(
        use_stub_embedder=False,
        use_stub_colbert=True,   # skip ColBERT download in integration tests
        qdrant_in_memory=True,
        sqlite_url=f"sqlite:///{db_path}",
        debug=False,
        embedding_model="nomic-ai/nomic-embed-text-v1.5",
        embedding_dim=768,
        embedding_dim_low=64,
        embedding_batch_size=4,
    )


@pytest.fixture(scope="module")
def real_pdf(tmp_path_factory) -> Path:
    from scripts.create_test_pdf import create_test_pdf
    out = tmp_path_factory.mktemp("pdfs") / "sample_physics.pdf"
    create_test_pdf(str(out))
    return out


@pytest.fixture(scope="module")
def ingested_result(real_settings, real_pdf):
    """
    Ingest the sample PDF once for the whole module.
    All E2E tests read from this shared result.
    """
    from src.pdf_ingestion.store import ingest_pdf
    print(f"\n[Fixture] Ingesting {real_pdf.name} once for module…")
    result = ingest_pdf(
        pdf_path=str(real_pdf),
        tenant_id="global",
        source_type="base_textbook",
        is_global_baseline=True,
        extra_meta={"subject": "Physics", "difficulty": 5},
        settings=real_settings,
    )
    print(f"[Fixture] Ingested: {result['chunk_count']} chunks, {result['page_count']} pages")
    return result


# ── Nomic v1.5 embedder tests ─────────────────────────────────────────────────

class TestRealNomicEmbedder:
    def test_model_loads(self, real_settings):
        from src.pdf_ingestion.embedder import NomicEmbedder
        print("\n[Nomic v1.5] Loading model…")
        emb = NomicEmbedder(settings=real_settings)
        emb._load()
        assert emb._model is not None
        print("[Nomic v1.5] Model loaded successfully")

    def test_query_embedding_shape_and_norm(self, real_settings):
        from src.pdf_ingestion.embedder import NomicEmbedder
        emb = NomicEmbedder(settings=real_settings)
        vec = emb.embed_query("What is Newton's second law of motion?")
        assert vec.shape == (real_settings.embedding_dim,)
        norm = float(np.linalg.norm(vec))
        assert abs(norm - 1.0) < 0.02, f"Expected unit norm, got {norm:.4f}"
        print(f"\n[Nomic v1.5] Query embedding: shape={vec.shape}, norm={norm:.4f}")

    def test_similar_queries_close_in_space(self, real_settings):
        """Semantically similar sentences must have higher cosine sim than unrelated."""
        from src.pdf_ingestion.embedder import NomicEmbedder
        emb = NomicEmbedder(settings=real_settings)
        v1 = emb.embed_query("force equals mass times acceleration")
        v2 = emb.embed_query("F = m * a, Newton's second law")
        v3 = emb.embed_query("the capital of France is Paris")
        sim_related   = float(np.dot(v1, v2))
        sim_unrelated = float(np.dot(v1, v3))
        print(f"\n[Nomic v1.5] Cosine sim (F=ma vs F=ma paraphrase): {sim_related:.4f}")
        print(f"[Nomic v1.5] Cosine sim (F=ma vs Paris capital):    {sim_unrelated:.4f}")
        assert sim_related > sim_unrelated

    def test_embed_chunks_correct_count(self, real_settings):
        """embed_chunks must return exactly one EmbeddedChunk per input."""
        from src.pdf_ingestion.chunker import TextChunk
        from src.pdf_ingestion.embedder import NomicEmbedder
        import uuid

        chunks = [
            TextChunk(
                chunk_id=str(uuid.uuid4()),
                document_id="test-count",
                tenant_id="global",
                chunk_index=i,
                text=f"Physics concept {i}: " + (
                    "Newton's law of motion describes force and acceleration. " * 3
                ),
                char_start=i * 200, char_end=i * 200 + 180,
                token_count=40, page_number=i + 1,
            )
            for i in range(6)
        ]
        emb = NomicEmbedder(settings=real_settings)
        results = emb.embed_chunks(chunks)
        assert len(results) == 6
        for r in results:
            assert r.embedding.shape == (real_settings.embedding_dim,)
            norm = float(np.linalg.norm(r.embedding))
            assert abs(norm - 1.0) < 0.02, f"Non-unit norm: {norm:.4f}"
        print(f"\n[Nomic v1.5] embed_chunks: 6 chunks → 6 unit-norm embeddings ✓")

    def test_embed_chunks_mrl_low_dim(self, real_settings):
        """EmbeddedChunk.embedding_low must be 64d and unit-normed (MRL truncation)."""
        from src.pdf_ingestion.chunker import TextChunk
        from src.pdf_ingestion.embedder import NomicEmbedder
        import uuid

        texts = [
            "The photoelectric effect shows light has particle-like properties.",
            "Einstein explained this using the concept of photons.",
            "Each photon carries energy proportional to its frequency.",
        ]
        chunks = [
            TextChunk(
                chunk_id=str(uuid.uuid4()), document_id="mrl-test",
                tenant_id="global", chunk_index=i, text=t,
                char_start=i * 80, char_end=i * 80 + len(t),
                token_count=12, page_number=1,
            )
            for i, t in enumerate(texts)
        ]
        emb = NomicEmbedder(settings=real_settings)
        results = emb.embed_chunks(chunks)

        for i, r in enumerate(results):
            assert r.embedding.shape == (real_settings.embedding_dim,), f"Chunk {i}: wrong 768d shape"
            assert r.embedding_low.shape == (real_settings.embedding_dim_low,), f"Chunk {i}: wrong 64d shape"
            norm_768 = float(np.linalg.norm(r.embedding))
            norm_64  = float(np.linalg.norm(r.embedding_low))
            assert abs(norm_768 - 1.0) < 0.02, f"Chunk {i} 768d non-unit norm: {norm_768:.4f}"
            assert abs(norm_64 - 1.0) < 0.02, f"Chunk {i} 64d non-unit norm: {norm_64:.4f}"

        print(f"\n[Nomic v1.5] MRL: 3 chunks → 768d+64d embeddings ✓")


# ── End-to-end pipeline tests (share one ingestion via module fixture) ─────

class TestRealEndToEnd:
    def test_full_ingest_pipeline(self, ingested_result):
        """Parse → chunk → embed (Nomic v1.5) → store in Qdrant + SQLite."""
        r = ingested_result
        print(f"\n[E2E] document_id={r['document_id']}, chunks={r['chunk_count']}, pages={r['page_count']}")
        assert r["document_id"]
        assert r["chunk_count"] > 0
        assert r["page_count"] >= 1
        assert r["tenant_id"] == "global"
        assert r["source_type"] == "base_textbook"

    def test_sqlite_document_record(self, real_settings, ingested_result):
        from src.core.database import get_engine
        from sqlmodel import Session
        from src.core.database import Document

        engine = get_engine(real_settings)
        with Session(engine) as session:
            doc = session.get(Document, ingested_result["document_id"])
        assert doc is not None
        assert doc.tenant_id == "global"
        assert doc.is_global_baseline is True
        assert doc.chunk_count == ingested_result["chunk_count"]
        print(f"\n[SQLite] Document verified: {doc.filename}, chunks={doc.chunk_count}")

    def test_qdrant_points_stored(self, real_settings, ingested_result):
        from src.core.database import get_qdrant
        info = get_qdrant(real_settings).get_collection(real_settings.qdrant_collection)
        assert info.points_count == ingested_result["chunk_count"]
        print(f"\n[Qdrant] Points stored: {info.points_count}")

    def test_qdrant_payload_metadata(self, real_settings, ingested_result):
        """Every Qdrant point must carry correct multi-tenancy payload."""
        from src.core.database import get_qdrant
        client = get_qdrant(real_settings)
        points, _ = client.scroll(
            collection_name=real_settings.qdrant_collection,
            limit=5,
            with_payload=True,
        )
        assert points, "Qdrant scroll returned no points"
        for pt in points:
            p = pt.payload
            assert p["tenant_id"] == "global"
            assert p["source_type"] == "base_textbook"
            assert p["is_global_baseline"] is True
            assert p["text"]
            assert p["embedding_version"]
        print(f"\n[Payload] Verified {len(points)} Qdrant points ✓")

    def test_sqlite_qdrant_count_match(self, real_settings, ingested_result):
        """SQLite chunk rows must match Qdrant point count exactly."""
        from src.core.database import get_engine, get_qdrant
        from sqlmodel import Session, select, func
        from src.core.database import Chunk

        engine = get_engine(real_settings)
        with Session(engine) as session:
            sql_count = session.exec(
                select(func.count()).select_from(Chunk)
                .where(Chunk.tenant_id == "global")
                .where(Chunk.is_active == True)
            ).one()

        qdrant_count = get_qdrant(real_settings).get_collection(
            real_settings.qdrant_collection
        ).points_count

        print(f"\n[Sync] SQLite={sql_count} | Qdrant={qdrant_count}")
        assert sql_count == qdrant_count

    def test_semantic_search_returns_relevant_results(self, real_settings, ingested_result):
        """Real Nomic v1.5 search should rank physics-relevant chunks at the top."""
        from src.pdf_ingestion.store import DocumentStore
        from src.pdf_ingestion.embedder import NomicEmbedder

        emb   = NomicEmbedder(settings=real_settings)
        store = DocumentStore(settings=real_settings)

        queries = [
            ("Newton second law force mass acceleration",
             ["force", "acceleration", "mass", "newton"]),
            ("conservation of energy kinetic potential work",
             ["energy", "kinetic", "potential", "work"]),
            ("electromagnetic waves Maxwell speed of light",
             ["maxwell", "electromagnetic", "light", "speed"]),
        ]

        for query, keywords in queries:
            q_vec = emb.embed_query(query)
            results = store.search(
                query_vector=q_vec,
                tenant_id="global",
                source_type="base_textbook",
                limit=5,
            )
            assert len(results) > 0, f"No results for: {query!r}"
            all_text = " ".join(r["text"].lower() for r in results)
            matched = [kw for kw in keywords if kw in all_text]
            top_score = results[0]["score"]
            print(f"\n[Search] '{query}'")
            print(f"  top score : {top_score:.4f}")
            print(f"  top chunk : {results[0]['text'][:100]}…")
            print(f"  keywords  : {matched} / {keywords}")
            assert matched, f"None of {keywords} found in top-5 results for {query!r}"
