"""Tests for the re-ingest write path (plan §5 Step 7).

Three things are pinned here, all of them decisions that are invisible until they are wrong:

1. **Which dense vector name gets written.** ``dense_1024`` on a collection built by the
   re-ingest, ``dense_768`` on the deployed one — read off the collection, not hard-coded,
   so the old index stays writable and queryable for the old-vs-new comparison (plan R1).
2. **The payload/SQLite contract**: ``parent_id`` and ``parent_text`` reach Qdrant, and
   ``parent_id`` reaches SQLite, so the hierarchy is usable at retrieval time.
3. **The stub tokenizer agrees with the stub embedder's token count** — if it did not,
   ``LateChunkEmbedder._content_tokens`` would raise on every parent in the test suite and
   nobody would notice the pooling path had stopped being exercised.

No Docling, no tokenizer download, no cluster: the parent and child producers are injected.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest
from qdrant_client.models import Distance, VectorParams

from src.core.config import Settings
from src.pdf_ingestion.chunker import SemanticChunker, TextChunk
from src.pdf_ingestion.chunking_pipeline import ChunkingPipeline
from src.pdf_ingestion.cluster_embedder import StubClusterEmbedder, StubTokenizer
from src.pdf_ingestion.embedder import EmbeddedChunk
from src.pdf_ingestion.late_chunk_embedder import EnrichedChunk, LateChunkEmbedder
from src.pdf_ingestion.models import ParentChunk
from src.pdf_ingestion.parent_chunker import ParentChunker
from src.pdf_ingestion.store import _dense_name_from, _dense_vectors

PARENT_TEXT = (
    "The lever is a rigid bar that rotates about a fulcrum. "
    "This is the simplest machine of all. "
    "The mechanical advantage equals the ratio of the two arms."
)


# ── 1. Vector-name resolution ───────────────────────────────────────────────

@pytest.mark.parametrize("vectors,expected", [
    ({"dense_64": object(), "dense_1024": object()}, "dense_1024"),
    ({"dense_64": object(), "dense_768": object()}, "dense_768"),
    ({"dense_64": object()}, None),          # 4-vector schema, no full-dim dense vector
    ({"dense": object()}, None),             # legacy single-vector collection
    (VectorParams(size=768, distance=Distance.COSINE), None),   # unnamed single vector
    (None, None),                            # schema unreadable (cluster down)
])
def test_dense_name_resolution(vectors, expected):
    assert _dense_name_from(vectors) == expected


def test_dense_name_prefers_1024_when_both_are_present():
    """A collection carrying both is mid-migration; the newest lane wins."""
    both = {"dense_64": object(), "dense_768": object(), "dense_1024": object()}
    assert _dense_name_from(both) == "dense_1024"


# ── 2. The two chunk shapes reach one write path ─────────────────────────────

def _text_chunk() -> TextChunk:
    return TextChunk(
        chunk_id=str(uuid.uuid4()), document_id="doc", tenant_id="global", chunk_index=0,
        text=PARENT_TEXT, char_start=0, char_end=len(PARENT_TEXT), token_count=30,
        page_number=1, parent_id=7, parent_text=PARENT_TEXT,
    )


def test_dense_vectors_reads_an_enriched_chunk():
    ec = EnrichedChunk(
        chunk=_text_chunk(),
        dense_1024=np.ones(1024, dtype=np.float32),
        dense_64=np.ones(64, dtype=np.float32),
    )
    full, low = _dense_vectors(ec)
    assert full.shape == (1024,) and low.shape == (64,)


def test_dense_vectors_reads_a_legacy_embedded_chunk():
    ec = EmbeddedChunk(
        chunk=_text_chunk(),
        embedding=np.ones(768, dtype=np.float32),
        embedding_low=np.ones(64, dtype=np.float32),
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )
    full, low = _dense_vectors(ec)
    assert full.shape == (768,) and low.shape == (64,)


def test_dense_vectors_falls_back_to_a_truncated_prefix_without_embedding_low():
    """A legacy chunk with an empty ``embedding_low`` is truncated, not written as 0-dim."""
    ec = EmbeddedChunk(
        chunk=_text_chunk(),
        embedding=np.arange(768, dtype=np.float32),
        embedding_low=np.array([], dtype=np.float32),
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )
    full, low = _dense_vectors(ec, dim_low=64)
    assert low.shape == (64,)
    assert np.allclose(low, full[:64])


# ── 3. The stub tokenizer must match the stub embedder ──────────────────────

@pytest.mark.parametrize("text", ["x" * 100, "ab", "", "short text here", "y" * 5])
def test_stub_tokenizer_agrees_with_the_stub_embedder(text):
    offsets = StubTokenizer()(text, add_special_tokens=False,
                              return_offsets_mapping=True)["offset_mapping"]
    n_vectors = StubClusterEmbedder().embed_documents_tokens([text])[0].shape[0]
    assert len(offsets) == n_vectors


def test_stub_tokenizer_offsets_tile_the_text():
    text = "x" * 100
    offsets = StubTokenizer()(text, add_special_tokens=False,
                              return_offsets_mapping=True)["offset_mapping"]
    assert offsets[0][0] == 0 and offsets[-1][1] == len(text)
    assert all(offsets[i][1] == offsets[i + 1][0] for i in range(len(offsets) - 1))


# ── 4. The write path, end to end, with injected producers ───────────────────

class _FakeParentChunker:
    """Stands in for Docling: two parents, a 2-page document."""

    def convert(self, path):
        parents = [
            ParentChunk(parent_id=0, text=PARENT_TEXT, page_map={0: 1}),
            ParentChunk(parent_id=1, text=PARENT_TEXT, page_map={0: 2}),
        ]
        return SimpleNamespace(pages={1: None, 2: None}), parents


class _FakeChunker:
    """Stands in for chonkie: one child per parent, carrying its parent's context."""

    def chunk_parents(self, document_id, tenant_id, parents):
        return [
            TextChunk(
                chunk_id=str(uuid.uuid4()), document_id=document_id,
                tenant_id=tenant_id, chunk_index=i, text=p.text,
                char_start=0, char_end=len(p.text), token_count=30,
                page_number=p.page_for_offset(0), parent_id=p.parent_id,
                parent_text=p.text, is_content=True,
            )
            for i, p in enumerate(parents)
        ]


def _pipeline(settings: Settings) -> ChunkingPipeline:
    # The fakes are duck-typed stand-ins for the two Docling/chonkie stages; the pipeline
    # only ever calls convert() / chunk_parents() on them.
    return ChunkingPipeline(
        settings=settings,
        parent_chunker=cast(ParentChunker, _FakeParentChunker()),
        chunker=cast(SemanticChunker, _FakeChunker()),
        embedder=LateChunkEmbedder(
            settings=settings, embedder=StubClusterEmbedder(), tokenizer=StubTokenizer()
        ),
    )


def test_pipeline_writes_the_hierarchy_to_qdrant_and_sqlite(settings, tmp_path):
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine

    settings.sqlite_url = f"sqlite:///{tmp_path}/pipeline.db"
    result = _pipeline(settings).process_pdf(
        pdf_path=str(tmp_path / "book.pdf"),
        tenant_id="global",
        source_type="base_textbook",
        is_global_baseline=True,
        extra_meta={"title": "Test Book"},
    )

    assert result["parent_count"] == 2
    assert result["chunk_count"] == 2
    assert result["page_count"] == 2

    # SQLite carries the parent link (and no page-number holes).
    engine = get_engine(settings)
    with Session(engine) as session:
        rows = session.exec(
            select(Chunk).where(Chunk.document_id == result["document_id"])
            .order_by(Chunk.chunk_index)
        ).all()
    assert [r.parent_id for r in rows] == [0, 1]
    assert [r.page_number for r in rows] == [1, 2]

    # Qdrant carries the parent link, the parent text, and the dense_1024 lane.
    from src.core.database import get_qdrant
    points = get_qdrant(settings).retrieve(
        collection_name=settings.qdrant_collection,
        ids=[r.qdrant_point_id for r in rows],
        with_payload=True, with_vectors=True,
    )
    by_id = {str(p.id): p for p in points}
    for r in rows:
        point = by_id[r.qdrant_point_id]
        assert point.payload["parent_id"] == r.parent_id
        assert point.payload["parent_text"] == PARENT_TEXT
        assert point.payload["is_content"] is True
        assert len(point.vector["dense_1024"]) == settings.dense_dim
        assert len(point.vector["dense_64"]) == settings.dense_dim_low


def test_pipeline_rejects_a_pdf_with_no_parents(settings, tmp_path):
    class _Empty(_FakeParentChunker):
        def convert(self, path):
            return SimpleNamespace(pages={}), []

    pipeline = _pipeline(settings)
    pipeline._parent_chunker = _Empty()
    with pytest.raises(ValueError, match="No parent chunks"):
        pipeline.process_pdf(str(tmp_path / "empty.pdf"), "global", "base_textbook", True)


# ── 5. The deployed collection keeps working (plan R1) ───────────────────────

def test_save_document_writes_dense_768_into_a_dense_768_collection(settings, tmp_path):
    """The old-vs-new comparison needs the deployed collection to stay writable.

    Same code path, same chunk shape — only the collection's schema differs, so the name
    must follow the schema. A hard-coded ``dense_1024`` would make the deployed index
    unwritable the moment this landed.
    """
    settings.sqlite_url = f"sqlite:///{tmp_path}/legacy.db"
    settings.qdrant_collection = "knowledge_base_legacy768"
    # This test is about the *dense* vector name; the extra lanes are exercised elsewhere
    # and would need their own slots in the hand-built collection below.
    settings.colbert_enabled = False
    settings.splade_enabled = False

    from src.pdf_ingestion.parser import ParsedDocument
    from src.pdf_ingestion.store import DocumentStore

    store = DocumentStore(settings)             # builds its own in-memory client
    client = store._qdrant
    # Replace the auto-created re-ingest collection with the deployed one's shape.
    client.delete_collection(settings.qdrant_collection)
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={
            "dense_64": VectorParams(size=settings.dense_dim_low, distance=Distance.COSINE),
            "dense_768": VectorParams(size=768, distance=Distance.COSINE),
        },
    )

    chunk = _text_chunk()
    embedded = EmbeddedChunk(
        chunk=chunk,
        embedding=np.ones(768, dtype=np.float32),
        embedding_low=np.ones(64, dtype=np.float32),
        model_name="nomic-ai/nomic-embed-text-v1.5",
    )
    parsed = ParsedDocument(
        document_id="doc-legacy", filename="book.pdf", full_text=PARENT_TEXT,
        pages=[], page_count=1, char_count=len(PARENT_TEXT), title="Legacy",
    )

    store.save_document(parsed, [embedded], "global", "base_textbook", True)

    points = client.retrieve(
        collection_name=settings.qdrant_collection,
        ids=[chunk.chunk_id], with_vectors=True, with_payload=True,
    )
    assert len(points) == 1
    assert set(points[0].vector) == {"dense_64", "dense_768"}
    assert len(points[0].vector["dense_768"]) == 768
    assert points[0].payload["parent_id"] == 7
