"""Qdrant + SQLite storage layer — Phase 1 (ingestion) + Phase 2 (cards, RAPTOR) + Phase 3 (ColPali, GraphRAG)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import numpy as np
from loguru import logger
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
from sqlmodel import Session, select

from src.core.config import Settings, get_settings
from src.core.database import Card, Chunk, Document, PageImage, RaptorNode, get_engine, get_qdrant
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
            source_path=meta.get("source_path"),
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
        source_type=None → Hybrid (user docs + global baseline), chunks only.
        RAPTOR summary vectors in the same collection are always excluded here;
        they are fetched separately via search_raptor().
        """
        _NOT_RAPTOR = FieldCondition(
            key="source_type", match=MatchValue(value="raptor_summary")
        )
        if source_type is None:
            filter_ = Filter(
                must_not=[_NOT_RAPTOR],
                should=[
                    Filter(must=[FieldCondition(key="tenant_id",
                                 match=MatchValue(value=tenant_id))]),
                    Filter(must=[FieldCondition(key="tenant_id",
                                 match=MatchValue(value=self._cfg.global_tenant_id))]),
                ],
            )
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

    def search_raptor(
        self,
        query_vector: np.ndarray,
        tenant_id: str,
        source_type_filter: Optional[str] = None,
        limit: int = 2,
    ) -> list[dict]:
        """Fetch RAPTOR cluster-summary vectors, respecting study-mode filter."""
        raptor_must = [FieldCondition(
            key="source_type", match=MatchValue(value="raptor_summary")
        )]
        if source_type_filter == "user_upload":
            filter_ = Filter(must=raptor_must + [
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            ])
        else:
            filter_ = Filter(
                must=raptor_must,
                should=[
                    Filter(must=[FieldCondition(key="tenant_id",
                                 match=MatchValue(value=tenant_id))]),
                    Filter(must=[FieldCondition(key="tenant_id",
                                 match=MatchValue(value=self._cfg.global_tenant_id))]),
                ],
            )
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

    def _deactivate_cards(self, document_id: str, session: Session) -> int:
        existing = session.exec(
            select(Card)
            .where(Card.document_id == document_id)
            .where(Card.is_active == True)
        ).all()
        for card in existing:
            card.is_active = False
        return len(existing)

    def _deactivate_raptor_nodes(self, document_id: str, session: Session) -> int:
        existing = session.exec(
            select(RaptorNode)
            .where(RaptorNode.document_id == document_id)
            .where(RaptorNode.is_active == True)
        ).all()
        for node in existing:
            node.is_active = False
        return len(existing)

    def save_cards(self, cards: list[GeneratedCard]) -> int:
        if not cards:
            return 0
        document_id = cards[0].document_id
        with Session(self._engine) as session:
            deactivated = self._deactivate_cards(document_id, session)
            if deactivated:
                logger.info(
                    "Deactivated {} existing cards for doc {} before re-generating",
                    deactivated, document_id,
                )
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

        document_id = nodes[0].document_id
        with Session(self._engine) as session:
            deactivated = self._deactivate_raptor_nodes(document_id, session)
            if deactivated:
                logger.info(
                    "Deactivated {} existing RAPTOR nodes for doc {} before re-generating",
                    deactivated, document_id,
                )
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

    # ── Phase 3: visual (ColPali) ─────────────────────────────────────────

    def update_colpali_status(self, document_id: str, status: str) -> None:
        with Session(self._engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.colpali_status = status
                doc.updated_at = datetime.utcnow()
                session.add(doc)
                session.commit()

    def save_page_images(
        self,
        document_id: str,
        pages: list,           # list of PageContent
        settings: Settings | None = None,
    ) -> list[PageImage]:
        """
        Upload page PNGs to the image store, deactivate any existing PageImage
        rows for this document, then insert fresh ones.
        Returns the newly created PageImage records (with image_key set).
        """
        from src.pdf_ingestion.image_store import get_image_store
        cfg = settings or self._cfg
        image_store = get_image_store(cfg)

        with Session(self._engine) as session:
            # Deactivate existing records
            existing = session.exec(
                select(PageImage)
                .where(PageImage.document_id == document_id)
                .where(PageImage.is_active == True)
            ).all()
            for pi in existing:
                pi.is_active = False

            records: list[PageImage] = []
            for page in pages:
                if not page.image_bytes:
                    continue
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(page.image_bytes))
                    w, h = img.size
                except Exception:
                    w, h = 0, 0

                key = image_store.save(document_id, page.page_number, page.image_bytes)
                pi = PageImage(
                    document_id=document_id,
                    page_number=page.page_number,
                    image_key=key,
                    width=w,
                    height=h,
                )
                session.add(pi)
                records.append(pi)

            session.commit()
            # Refresh to get auto-generated ids
            for pi in records:
                session.refresh(pi)

        logger.info("Saved {} page images for doc {}", len(records), document_id)
        return records

    def save_colpali_embeddings(
        self,
        page_image_records: list[PageImage],
        patch_matrices: list,    # parallel list of np.ndarray (N_patches, patch_dim)
        tenant_id: str,
        is_global_baseline: bool,
        source_type: str,
    ) -> int:
        from qdrant_client.models import PointStruct
        cfg = self._cfg
        points = []
        for pi, patches in zip(page_image_records, patch_matrices):
            if patches is None or len(patches) == 0:
                continue
            points.append(PointStruct(
                id=pi.colpali_point_id,
                vector={"colpali": patches.tolist()},
                payload={
                    "tenant_id":          tenant_id,
                    "source_type":        "page_image",
                    "is_global_baseline": is_global_baseline,
                    "document_id":        pi.document_id,
                    "page_image_id":      pi.id,
                    "page_number":        pi.page_number,
                    "image_key":          pi.image_key,
                },
            ))

        for i in range(0, len(points), 32):
            self._qdrant.upsert(
                collection_name=cfg.colpali_collection,
                points=points[i : i + 32],
            )
        logger.info("Upserted {} ColPali vectors for doc {}", len(points),
                    page_image_records[0].document_id if page_image_records else "?")
        return len(points)

    def visual_search(
        self,
        query_patches: "np.ndarray",
        tenant_id: str,
        source_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """MaxSim late-interaction search against the ColPali collection.

        source_type=None  → hybrid (user docs + global baseline)
        source_type='user_upload' → user docs only
        source_type='base_textbook' → global baseline only
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        if source_type == "user_upload":
            filter_ = Filter(must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            ])
        elif source_type == "base_textbook":
            filter_ = Filter(must=[
                FieldCondition(key="tenant_id",
                               match=MatchValue(value=self._cfg.global_tenant_id)),
            ])
        else:
            filter_ = Filter(should=[
                Filter(must=[FieldCondition(key="tenant_id",
                             match=MatchValue(value=tenant_id))]),
                Filter(must=[FieldCondition(key="tenant_id",
                             match=MatchValue(value=self._cfg.global_tenant_id))]),
            ])
        try:
            response = self._qdrant.query_points(
                collection_name=self._cfg.colpali_collection,
                query=query_patches.tolist(),
                using="colpali",
                query_filter=filter_,
                limit=limit,
                with_payload=True,
            )
            return [{"score": h.score, **h.payload} for h in response.points]
        except Exception as exc:
            logger.warning("Visual search failed ({})", exc)
            return []

    def get_page_images(self, document_id: str) -> list[PageImage]:
        with Session(self._engine) as session:
            return session.exec(
                select(PageImage)
                .where(PageImage.document_id == document_id)
                .where(PageImage.is_active == True)
                .order_by(PageImage.page_number)
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
    from pathlib import Path

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
        extra_meta={**(extra_meta or {}), "source_path": str(Path(pdf_path).resolve())},
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


# ── Phase 3 pipeline orchestrator ─────────────────────────────────────────

def generate_phase3_artifacts(
    document_id: str,
    pdf_path: str | None = None,
    settings: Settings | None = None,
    force: bool = False,
) -> dict:
    """
    Generate ColPali visual embeddings + Memgraph concept graph for an
    already-ingested document.

    pdf_path is required for rasterizing page images. When omitted the
    function attempts to locate the PDF automatically under the configured
    upload/textbook directories.

    If force=False (default), ColPali is skipped when PageImage records
    already exist for the document, and Memgraph is skipped when the
    Document node already exists in the graph.
    """
    from pathlib import Path
    from sqlmodel import Session as S

    from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
    from src.pdf_ingestion.graph_builder import GraphBuilder, get_graph_builder
    from src.pdf_ingestion.parser import PDFParser

    cfg = settings or get_settings()
    store = DocumentStore(settings=cfg)

    with S(store._engine) as session:
        doc = session.get(Document, document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    store.update_colpali_status(document_id, "processing")

    import io
    from PIL import Image

    # ── Locate the PDF if path not provided ───────────────────────────────
    if pdf_path is None:
        # 1. Use the path recorded at ingest time (most reliable)
        if doc.source_path and Path(doc.source_path).exists():
            pdf_path = doc.source_path
        else:
            # 2. Fall back: search configured dirs by filename
            for base in (cfg.base_textbook_dir, cfg.upload_dir):
                candidate = Path(base) / doc.filename
                if candidate.exists():
                    pdf_path = str(candidate)
                    break
        if pdf_path is None:
            logger.warning(
                "PDF not found for doc {} (filename='{}', source_path='{}') — skipping visual embeddings",
                document_id, doc.filename, doc.source_path,
            )

    # ── ColPali: rasterize → embed in batches → store ─────────────────────
    n_visual = 0
    colpali_error: str | None = None
    try:
        existing_page_images = store.get_page_images(document_id)
        if existing_page_images and not force:
            n_visual = len(existing_page_images)
            logger.info(
                "ColPali: skipping — {} page images already stored for doc {} (use force=True to re-run)",
                n_visual, document_id,
            )
        elif pdf_path:
            parser = PDFParser(use_gpu=cfg.use_gpu, rasterize_pages=True)
            parsed = parser.parse(pdf_path)

            pages_with_images = [p for p in parsed.pages if p.image_bytes]
            if pages_with_images:
                page_records = store.save_page_images(
                    document_id=document_id,
                    pages=pages_with_images,
                    settings=cfg,
                )

                colpali = get_colpali_embedder(cfg)
                batch_size = cfg.colpali_page_batch_size
                logger.info(
                    "ColPali: embedding {} pages in batches of {}",
                    len(pages_with_images), batch_size,
                )
                for i in range(0, len(pages_with_images), batch_size):
                    batch_pages   = pages_with_images[i : i + batch_size]
                    batch_records = page_records[i : i + batch_size]
                    pil_images    = [Image.open(io.BytesIO(p.image_bytes)) for p in batch_pages]
                    patch_matrices = colpali.embed_pages(pil_images)
                    n_visual += store.save_colpali_embeddings(
                        page_image_records=batch_records,
                        patch_matrices=patch_matrices,
                        tenant_id=doc.tenant_id,
                        is_global_baseline=doc.is_global_baseline,
                        source_type=doc.source_type,
                    )
                    del pil_images, patch_matrices  # free RAM between batches
    except Exception as exc:
        colpali_error = str(exc)
        logger.error("ColPali failed for doc {}: {}", document_id, exc)

    # ── Memgraph: build concept graph ──────────────────────────────────────
    graph_stats: dict = {}
    graph_error: str | None = None
    try:
        graph = get_graph_builder(cfg)
        # Skip if document node already exists in Memgraph and not forcing
        graph_already_built = (
            not force
            and not cfg.use_stub_graph
            and isinstance(graph, GraphBuilder)
            and graph.document_exists(document_id)
        )
        if graph_already_built:
            logger.info(
                "Memgraph: skipping — Document node already exists for doc {} (use force=True to re-run)",
                document_id,
            )
            graph_stats = {"skipped": True}
        else:
            chunks_db, _ = store.get_chunks_with_embeddings(document_id)
            logger.info(
                "Memgraph: building graph for doc '{}' ({} chunks)",
                doc.filename, len(chunks_db),
            )
            graph_stats = graph.build_graph(
                document_id=document_id,
                tenant_id=doc.tenant_id,
                chunks=chunks_db,
                doc_title=doc.title or "",
                doc_subject=doc.subject or "",
            )
    except Exception as exc:
        graph_error = str(exc)
        logger.error("Memgraph failed for doc {}: {}", document_id, exc)

    # ── Final status ───────────────────────────────────────────────────────
    failed = colpali_error or graph_error
    status = "failed" if failed else "ready"
    store.update_colpali_status(document_id, status)

    if not failed:
        logger.success(
            "Phase 3 complete for '{}': {} visual vectors, {} concept nodes",
            doc.filename, n_visual, graph_stats.get("concept_nodes", 0),
        )
    else:
        logger.warning(
            "Phase 3 partial/failed for '{}': colpali={} graph={}",
            doc.filename,
            "ok" if not colpali_error else f"FAILED({colpali_error[:60]})",
            "ok" if not graph_error   else f"FAILED({graph_error[:60]})",
        )

    return {
        "document_id":    document_id,
        "filename":       doc.filename,
        "visual_vectors": n_visual,
        "graph_stats":    graph_stats,
        "colpali_status": status,
        "colpali_error":  colpali_error,
        "graph_error":    graph_error,
    }
