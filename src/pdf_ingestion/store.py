"""Qdrant + SQLite storage layer — Phase 1 (ingestion) + Phase 2 (cards, RAPTOR)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import numpy as np
from loguru import logger
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
from sqlmodel import Session, select

from src.core.config import Settings, get_settings
from src.core.database import Card, Chunk, Document, RaptorNode, get_engine, get_qdrant
from src.pdf_ingestion.card_generator import GeneratedCard
from src.pdf_ingestion.embedder import EmbeddedChunk
from src.pdf_ingestion.parser import ParsedDocument
from src.pdf_ingestion.raptor_tree import RaptorNodeData


# ── Qdrant payload builder ─────────────────────────────────────────────────

def _build_payload(
    ec: EmbeddedChunk,
    doc: ParsedDocument,
    tenant_id: str,
    source_type: str,
    is_global_baseline: bool,
    extra_meta: dict | None = None,
) -> dict:
    meta = extra_meta or {}
    return {
        "tenant_id":          tenant_id,
        "source_type":        source_type,
        "is_global_baseline": is_global_baseline,
        "document_id":        doc.document_id,
        "chunk_id":           ec.chunk.chunk_id,
        "chunk_index":        ec.chunk.chunk_index,
        "text":               ec.chunk.text,
        "page_number":        ec.chunk.page_number,
        "title":              doc.title,
        "subject":            meta.get("subject"),
        "grade_level":        meta.get("grade_level"),
        "difficulty":         meta.get("difficulty"),
        "embedding_version":  ec.model_name,
        "char_start":         ec.chunk.char_start,
        "char_end":           ec.chunk.char_end,
    }


# ── DocumentStore ─────────────────────────────────────────────────────────

class DocumentStore:
    """
    Single facade for Qdrant + SQLite.
    Multi-tenancy is enforced via Qdrant payload filters on tenant_id / source_type.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg    = settings or get_settings()
        self._qdrant = get_qdrant(self._cfg)
        self._engine = get_engine(self._cfg)

    # ── Phase 1: write ────────────────────────────────────────────────────

    def save_document(
        self,
        parsed_doc: ParsedDocument,
        embedded_chunks: list[EmbeddedChunk],
        tenant_id: str,
        source_type: str,
        is_global_baseline: bool,
        extra_meta: dict | None = None,
    ) -> str:
        doc_id = parsed_doc.document_id
        meta   = extra_meta or {}

        db_doc = Document(
            id=doc_id,
            tenant_id=tenant_id,
            source_type=source_type,
            is_global_baseline=is_global_baseline,
            filename=parsed_doc.filename,
            title=parsed_doc.title or meta.get("title"),
            subject=meta.get("subject"),
            grade_level=meta.get("grade_level"),
            difficulty=meta.get("difficulty"),
            page_count=parsed_doc.page_count,
            chunk_count=len(embedded_chunks),
            embedding_version=embedded_chunks[0].model_name if embedded_chunks else "unknown",
        )

        with Session(self._engine) as session:
            existing = session.get(Document, doc_id)
            if existing:
                existing.chunk_count = db_doc.chunk_count
                existing.updated_at  = datetime.utcnow()
                session.add(existing)
            else:
                session.add(db_doc)

            for ec in embedded_chunks:
                session.add(Chunk(
                    id=ec.chunk.chunk_id,
                    document_id=doc_id,
                    tenant_id=tenant_id,
                    chunk_index=ec.chunk.chunk_index,
                    text=ec.chunk.text,
                    page_number=ec.chunk.page_number,
                    qdrant_point_id=ec.chunk.chunk_id,
                    char_start=ec.chunk.char_start,
                    char_end=ec.chunk.char_end,
                    token_count=ec.chunk.token_count,
                ))
            session.commit()

        logger.info("SQLite: saved doc {} with {} chunks", doc_id, len(embedded_chunks))

        points = [
            PointStruct(
                id=ec.chunk.chunk_id,
                vector=ec.embedding.tolist(),
                payload=_build_payload(ec, parsed_doc, tenant_id, source_type,
                                       is_global_baseline, meta),
            )
            for ec in embedded_chunks
        ]
        for i in range(0, len(points), 128):
            self._qdrant.upsert(
                collection_name=self._cfg.qdrant_collection,
                points=points[i : i + 128],
            )
        logger.success("Qdrant: upserted {} points for doc {}", len(points), doc_id)
        return doc_id

    # ── Phase 1: read ─────────────────────────────────────────────────────

    def search(
        self,
        query_vector: np.ndarray,
        tenant_id: str,
        source_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Semantic search with multi-tenant scoping.
        source_type=None → Hybrid (user docs + global baseline)
        """
        if source_type is None:
            filter_ = Filter(should=[
                Filter(must=[FieldCondition(key="tenant_id",
                             match=MatchValue(value=tenant_id))]),
                Filter(must=[FieldCondition(key="tenant_id",
                             match=MatchValue(value=self._cfg.global_tenant_id))]),
            ])
        else:
            must = [FieldCondition(key="source_type", match=MatchValue(value=source_type))]
            if source_type == "base_textbook":
                must.append(FieldCondition(key="tenant_id",
                            match=MatchValue(value=self._cfg.global_tenant_id)))
            else:
                must.append(FieldCondition(key="tenant_id",
                            match=MatchValue(value=tenant_id)))
            filter_ = Filter(must=must)

        response = self._qdrant.query_points(
            collection_name=self._cfg.qdrant_collection,
            query=query_vector.tolist(),
            query_filter=filter_,
            limit=limit,
            with_payload=True,
        )
        return [{"score": h.score, **h.payload} for h in response.points]

    def get_document_stats(self, document_id: str) -> dict:
        with Session(self._engine) as session:
            doc = session.get(Document, document_id)
            if not doc:
                return {}
            chunks = session.exec(
                select(Chunk).where(Chunk.document_id == document_id)
            ).all()
        return {
            "document_id":       doc.id,
            "filename":          doc.filename,
            "tenant_id":         doc.tenant_id,
            "source_type":       doc.source_type,
            "page_count":        doc.page_count,
            "chunk_count":       len(chunks),
            "embedding_version": doc.embedding_version,
            "created_at":        str(doc.created_at),
        }

    def list_documents(self, tenant_id: Optional[str] = None) -> list[Document]:
        with Session(self._engine) as session:
            stmt = select(Document).where(Document.is_active == True)
            if tenant_id:
                stmt = stmt.where(Document.tenant_id == tenant_id)
            return session.exec(stmt).all()

    def get_chunks_with_embeddings(
        self, document_id: str
    ) -> tuple[list[Chunk], np.ndarray]:
        """Return ordered chunks + their Qdrant vectors for RAPTOR clustering."""
        with Session(self._engine) as session:
            chunks = session.exec(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .where(Chunk.is_active == True)
                .order_by(Chunk.chunk_index)
            ).all()

        if not chunks:
            return [], np.array([])

        try:
            results = self._qdrant.retrieve(
                collection_name=self._cfg.qdrant_collection,
                ids=[c.qdrant_point_id for c in chunks],
                with_vectors=True,
            )
            id_to_vec = {str(r.id): np.array(r.vector, dtype=np.float32) for r in results}
            embeddings = np.array(
                [id_to_vec.get(c.qdrant_point_id, np.zeros(self._cfg.embedding_dim))
                 for c in chunks],
                dtype=np.float32,
            )
        except Exception as exc:
            logger.warning("Could not fetch chunk vectors: {}", exc)
            embeddings = np.zeros((len(chunks), self._cfg.embedding_dim), dtype=np.float32)

        return list(chunks), embeddings

    # ── Phase 2: cards ────────────────────────────────────────────────────

    def save_cards(self, cards: list[GeneratedCard]) -> int:
        if not cards:
            return 0
        with Session(self._engine) as session:
            for gc in cards:
                session.add(Card(
                    id=gc.card_id,
                    chunk_id=gc.chunk_id,
                    document_id=gc.document_id,
                    tenant_id=gc.tenant_id,
                    card_type=gc.card_type,
                    title=gc.title,
                    content=gc.content,
                    answer=gc.answer,
                    metadata_json=json.dumps(gc.metadata) if gc.metadata else None,
                ))
            session.commit()
        logger.info("Saved {} cards to SQLite", len(cards))
        return len(cards)

    def get_cards(
        self,
        document_id: str,
        card_type: Optional[str] = None,
    ) -> list[Card]:
        with Session(self._engine) as session:
            stmt = (
                select(Card)
                .where(Card.document_id == document_id)
                .where(Card.is_active == True)
            )
            if card_type:
                stmt = stmt.where(Card.card_type == card_type)
            return session.exec(stmt).all()

    # ── Phase 2: RAPTOR ───────────────────────────────────────────────────

    def save_raptor_tree(
        self,
        nodes: list[RaptorNodeData],
        is_global_baseline: bool,
        source_type: str,
    ) -> int:
        if not nodes:
            return 0

        with Session(self._engine) as session:
            for nd in nodes:
                session.add(RaptorNode(
                    id=nd.node_id,
                    document_id=nd.document_id,
                    tenant_id=nd.tenant_id,
                    level=nd.level,
                    parent_id=nd.parent_id,
                    cluster_id=nd.cluster_id,
                    summary=nd.summary,
                    child_ids_json=json.dumps(nd.child_ids),
                    qdrant_point_id=nd.qdrant_point_id,
                ))
            session.commit()

        points = [
            PointStruct(
                id=nd.qdrant_point_id,
                vector=nd.embedding.tolist(),
                payload={
                    "tenant_id":          nd.tenant_id,
                    "source_type":        "raptor_summary",
                    "is_global_baseline": is_global_baseline,
                    "document_id":        nd.document_id,
                    "raptor_node_id":     nd.node_id,
                    "raptor_level":       nd.level,
                    "cluster_id":         nd.cluster_id,
                    "text":               nd.summary,
                    "child_chunk_count":  len(nd.child_ids),
                    "embedding_version":  "jina-v3",
                },
            )
            for nd in nodes
            if nd.embedding is not None
        ]
        for i in range(0, len(points), 64):
            self._qdrant.upsert(
                collection_name=self._cfg.qdrant_collection,
                points=points[i : i + 64],
            )
        if points:
            logger.info("Upserted {} RAPTOR vectors to Qdrant", len(points))

        logger.success("Saved {} RAPTOR nodes", len(nodes))
        return len(nodes)

    def get_raptor_tree(self, document_id: str) -> list[RaptorNode]:
        with Session(self._engine) as session:
            return session.exec(
                select(RaptorNode)
                .where(RaptorNode.document_id == document_id)
                .where(RaptorNode.is_active == True)
                .order_by(RaptorNode.level, RaptorNode.cluster_id)
            ).all()


# ── Phase 1 pipeline orchestrator ─────────────────────────────────────────

def ingest_pdf(
    pdf_path: str,
    tenant_id: str,
    source_type: str,
    is_global_baseline: bool,
    extra_meta: dict | None = None,
    settings: Settings | None = None,
) -> dict:
    """Parse → chunk → embed → store. Returns summary dict."""
    from src.pdf_ingestion.chunker import SemanticChunker
    from src.pdf_ingestion.embedder import get_embedder
    from src.pdf_ingestion.parser import PDFParser

    cfg      = settings or get_settings()
    parser   = PDFParser(use_gpu=cfg.use_gpu)
    chunker  = SemanticChunker(settings=cfg)
    embedder = get_embedder(settings=cfg)
    store    = DocumentStore(settings=cfg)

    parsed   = parser.parse(pdf_path)
    page_map = chunker.build_page_map(parsed.full_text, parsed.pages)
    chunks   = chunker.chunk_document(
        document_id=parsed.document_id,
        tenant_id=tenant_id,
        full_text=parsed.full_text,
        page_map=page_map,
    )
    if not chunks:
        raise ValueError(f"No chunks produced from {pdf_path}")

    embedded = embedder.embed_chunks(chunks)
    doc_id   = store.save_document(
        parsed_doc=parsed,
        embedded_chunks=embedded,
        tenant_id=tenant_id,
        source_type=source_type,
        is_global_baseline=is_global_baseline,
        extra_meta=extra_meta,
    )
    return {
        "document_id": doc_id,
        "filename":    parsed.filename,
        "page_count":  parsed.page_count,
        "chunk_count": len(embedded),
        "tenant_id":   tenant_id,
        "source_type": source_type,
    }


# ── Phase 2 pipeline orchestrator ─────────────────────────────────────────

def generate_phase2_artifacts(
    document_id: str,
    settings: Settings | None = None,
) -> dict:
    """Generate cards + RAPTOR tree for an already-ingested document."""
    from src.pdf_ingestion.card_generator import get_card_generator
    from src.pdf_ingestion.chunker import TextChunk
    from src.pdf_ingestion.raptor_tree import RaptorBuilder
    from sqlmodel import Session as S

    cfg   = settings or get_settings()
    store = DocumentStore(settings=cfg)

    with S(store._engine) as session:
        doc = session.get(Document, document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    chunks_db, embeddings = store.get_chunks_with_embeddings(document_id)
    if not chunks_db:
        raise ValueError(f"No chunks for document {document_id}")

    chunk_objects = [
        TextChunk(
            chunk_id=c.id,
            document_id=c.document_id,
            tenant_id=c.tenant_id,
            chunk_index=c.chunk_index,
            text=c.text,
            char_start=c.char_start,
            char_end=c.char_end,
            token_count=c.token_count,
            page_number=c.page_number,
        )
        for c in chunks_db
    ]

    generator = get_card_generator(cfg)
    cards     = generator.generate_cards_for_chunks(chunk_objects)
    n_cards   = store.save_cards(cards)

    builder = RaptorBuilder(settings=cfg)
    nodes   = builder.build_tree(
        document_id=document_id,
        tenant_id=doc.tenant_id,
        is_global_baseline=doc.is_global_baseline,
        chunk_texts=[c.text for c in chunks_db],
        chunk_ids=[c.id for c in chunks_db],
        chunk_embeddings=embeddings,
    )
    n_nodes = store.save_raptor_tree(
        nodes=nodes,
        is_global_baseline=doc.is_global_baseline,
        source_type=doc.source_type,
    )

    logger.success(
        "Phase 2 complete for '{}': {} cards, {} RAPTOR nodes",
        doc.filename, n_cards, n_nodes,
    )
    return {
        "document_id":     document_id,
        "filename":        doc.filename,
        "cards_generated": n_cards,
        "raptor_nodes":    n_nodes,
        "raptor_levels":   sorted({nd.level for nd in nodes}),
    }
