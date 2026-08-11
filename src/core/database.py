"""SQLModel table definitions, SQLite engine, and Qdrant collection bootstrap."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    MultiVectorConfig,
    MultiVectorComparator,
    PayloadSchemaType,
    VectorParams,
)
from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, Session, SQLModel, create_engine

from src.core.config import Settings, get_settings


# -- Phase 1: Relational tables ------------------------------------------------

class Document(SQLModel, table=True):
    """One ingested PDF -- base textbook or user upload."""
    __tablename__ = "documents"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    source_type: str = Field(index=True)        # "base_textbook" | "user_upload"
    is_global_baseline: bool = Field(default=False, index=True)
    filename: str
    source_path: Optional[str] = None          # full path at ingest time; used by Phase 3 to locate PDF
    title: Optional[str] = None
    subject: Optional[str] = None
    grade_level: Optional[str] = None
    difficulty: Optional[int] = None
    language: str = "en"
    page_count: int = 0
    chunk_count: int = 0
    embedding_version: str = "jina-v3"
    colpali_status: str = Field(default="pending", index=True)  # pending|processing|ready|failed
    version: int = Field(default=1)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(SQLModel, table=True):
    """A text chunk produced by Chonkie, linked to its Qdrant point."""
    __tablename__ = "chunks"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    tenant_id: str = Field(index=True)
    chunk_index: int
    text: str
    page_number: Optional[int] = None
    qdrant_point_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    char_start: int = 0
    char_end: int = 0
    token_count: int = 0
    version: int = Field(default=1)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# -- Phase 2: Derivative artifact tables ---------------------------------------

class Card(SQLModel, table=True):
    """
    One of 7 pedagogical cards per chunk (Llama 3.2).
    card_type: summary | definition | example | misconception |
               question | objective | formula
    """
    __tablename__ = "cards"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    chunk_id: str = Field(foreign_key="chunks.id", index=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    tenant_id: str = Field(index=True)
    card_type: str = Field(index=True)
    title: str
    content: str
    answer: Optional[str] = None
    metadata_json: Optional[str] = None
    version: int = Field(default=1)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RaptorNode(SQLModel, table=True):
    """
    RAPTOR hierarchical summary node.
    level=1 -> cluster summaries of leaf chunks
    level=2 -> meta-summary (root)
    """
    __tablename__ = "raptor_nodes"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    tenant_id: str = Field(index=True)
    level: int = Field(index=True)
    parent_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, ForeignKey("raptor_nodes.id"), nullable=True),
    )
    cluster_id: int = 0
    summary: str
    child_ids_json: str = "[]"
    qdrant_point_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = Field(default=1)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# -- Phase 3: Visual + Graph tables --------------------------------------------

class PageImage(SQLModel, table=True):
    """One rasterized page image per PDF page."""
    __tablename__ = "page_images"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    page_number: int = Field(index=True)
    image_key: str                           # path or object key in image store
    width: int = 0
    height: int = 0
    colpali_point_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# -- SQLite engine factory -----------------------------------------------------

_engine = None


def _migrate_add_columns(engine) -> None:
    """Add columns introduced after the initial schema without breaking existing DBs."""
    migrations = [
        ("documents", "colpali_status", "TEXT DEFAULT 'pending'"),
        ("documents", "source_path",    "TEXT"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                )
                conn.commit()
                logger.debug("Migration: added {}.{}", table, column)
            except Exception:
                pass  # column already exists


def get_engine(settings: Settings | None = None):
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        cfg.ensure_dirs()
        _engine = create_engine(
            cfg.sqlite_url,
            connect_args={"check_same_thread": False},
            echo=cfg.debug,
        )
        try:
            SQLModel.metadata.create_all(_engine)
        except Exception as exc:
            # Indexes for existing tables may already exist when the same
            # DB file is reused across test runs. Safe to ignore.
            if "already exists" in str(exc).lower():
                logger.debug("DB schema already present, skipping: {}", exc)
            else:
                raise
        # Add columns that were introduced after initial schema creation.
        # SQLite does not support ALTER TABLE ADD COLUMN IF NOT EXISTS, so
        # we catch the "duplicate column" error and continue.
        _migrate_add_columns(_engine)
        logger.info("SQLite engine ready: {}", cfg.sqlite_url)
    return _engine


def get_session(settings: Settings | None = None):
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session


# -- Qdrant client factory -----------------------------------------------------

_qdrant: QdrantClient | None = None


def get_qdrant(settings: Settings | None = None) -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        cfg = settings or get_settings()

        if cfg.qdrant_in_memory:
            _qdrant = QdrantClient(":memory:")
            logger.info("Qdrant: in-memory mode (tests)")

        elif cfg.qdrant_url:
            # Remote cloud (Qdrant Cloud, Support Vectors, etc.)
            # Also works for self-hosted: set QDRANT_URL=http://host:port
            kwargs = {"url": cfg.qdrant_url}
            if cfg.qdrant_api_key:
                kwargs["api_key"] = cfg.qdrant_api_key
            _qdrant = QdrantClient(**kwargs)
            logger.info("Qdrant: server at '{}'", cfg.qdrant_url)

        elif cfg.qdrant_host and cfg.qdrant_host != "localhost":
            # Self-hosted via explicit QDRANT_HOST + QDRANT_PORT
            _qdrant = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)
            logger.info("Qdrant: server at {}:{}", cfg.qdrant_host, cfg.qdrant_port)

        else:
            # Local file-based persistence (no server needed for dev)
            from pathlib import Path
            Path(cfg.qdrant_local_path).mkdir(parents=True, exist_ok=True)
            _qdrant = QdrantClient(path=cfg.qdrant_local_path)
            logger.info("Qdrant: local path '{}'", cfg.qdrant_local_path)

        _ensure_collection(_qdrant, cfg)
        _ensure_colpali_collection(_qdrant, cfg)
    return _qdrant


def _ensure_collection(client: QdrantClient, cfg: Settings) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if cfg.qdrant_collection not in existing:
        client.create_collection(
            collection_name=cfg.qdrant_collection,
            vectors_config=VectorParams(size=cfg.embedding_dim, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '{}'", cfg.qdrant_collection)

    for field, schema in (
        ("tenant_id",          PayloadSchemaType.KEYWORD),
        ("source_type",        PayloadSchemaType.KEYWORD),
        ("is_global_baseline", PayloadSchemaType.BOOL),
        ("document_id",        PayloadSchemaType.KEYWORD),
        ("raptor_level",       PayloadSchemaType.INTEGER),
    ):
        try:
            client.create_payload_index(
                collection_name=cfg.qdrant_collection,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            pass


def _ensure_colpali_collection(client: QdrantClient, cfg: Settings) -> None:
    """Create the ColPali multi-vector collection for visual search."""
    existing = {c.name for c in client.get_collections().collections}
    if cfg.colpali_collection not in existing:
        client.create_collection(
            collection_name=cfg.colpali_collection,
            vectors_config={
                "colpali": VectorParams(
                    size=cfg.colpali_patch_dim,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(
                        comparator=MultiVectorComparator.MAX_SIM
                    ),
                )
            },
        )
        logger.info("Created Qdrant ColPali collection '{}'", cfg.colpali_collection)

    for field, schema in (
        ("tenant_id",   PayloadSchemaType.KEYWORD),
        ("document_id", PayloadSchemaType.KEYWORD),
        ("page_number", PayloadSchemaType.INTEGER),
    ):
        try:
            client.create_payload_index(
                collection_name=cfg.colpali_collection,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            pass


# -- Memgraph (Neo4j Bolt) factory ---------------------------------------------

_memgraph = None


def get_memgraph(settings: Settings | None = None):
    """Return a neo4j Driver connected to Memgraph via Bolt."""
    global _memgraph
    if _memgraph is None:
        cfg = settings or get_settings()
        try:
            from neo4j import GraphDatabase
            uri = f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}"
            _memgraph = GraphDatabase.driver(
                uri,
                auth=(cfg.memgraph_user, cfg.memgraph_password),
            )
            logger.info("Memgraph: connected at {}", uri)
        except Exception as exc:
            logger.warning("Memgraph unavailable ({})", exc)
            _memgraph = None
    return _memgraph


def reset_singletons() -> None:
    """Test helper -- tear down cached singletons between test runs."""
    global _engine, _qdrant, _memgraph
    if _memgraph is not None:
        try:
            _memgraph.close()
        except Exception:
            pass
    _engine = None
    _qdrant = None
    _memgraph = None
