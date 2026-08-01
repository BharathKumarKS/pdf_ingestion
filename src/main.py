"""FastAPI application — Phase 1 ingestion endpoints."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from src.core.config import Settings, get_settings
from src.core.database import get_session
from src.pdf_ingestion.store import DocumentStore, ingest_pdf

app = FastAPI(
    title="Synapse Learning Worlds API",
    version="0.1.0",
    description="Phase 1 — PDF Ingestion & Knowledge Base Bootstrap",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────

class IngestRequest(BaseModel):
    tenant_id: str
    source_type: str = "user_upload"
    is_global_baseline: bool = False
    title: str | None = None
    subject: str | None = None
    grade_level: str | None = None
    difficulty: int | None = None


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    chunk_count: int
    tenant_id: str
    source_type: str


class SearchRequest(BaseModel):
    query: str
    tenant_id: str
    source_type: str | None = None   # None = hybrid
    limit: int = 10


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    file: UploadFile,
    tenant_id: str,
    source_type: str = "user_upload",
    title: str | None = None,
    subject: str | None = None,
    settings: Settings = Depends(get_settings),
):
    """Upload and ingest a user PDF (runtime, per-user tenant)."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted")

    upload_dir = Path(settings.upload_dir) / tenant_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4()}_{file.filename}"

    try:
        with dest.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        result = ingest_pdf(
            pdf_path=str(dest),
            tenant_id=tenant_id,
            source_type=source_type,
            is_global_baseline=False,
            extra_meta={"title": title, "subject": subject},
            settings=settings,
        )
        return IngestResponse(**result)
    except Exception as exc:
        logger.error("Ingestion failed: {}", exc)
        raise HTTPException(500, str(exc))


@app.post("/search")
def search(req: SearchRequest, settings: Settings = Depends(get_settings)):
    """Semantic search with optional source_type filtering."""
    from src.pdf_ingestion.embedder import get_embedder

    embedder = get_embedder(settings)
    query_vec = embedder.embed_query(req.query)
    store = DocumentStore(settings)
    results = store.search(
        query_vector=query_vec,
        tenant_id=req.tenant_id,
        source_type=req.source_type,
        limit=req.limit,
    )
    return {"results": results, "count": len(results)}


@app.get("/documents")
def list_documents(tenant_id: str | None = None, settings: Settings = Depends(get_settings)):
    store = DocumentStore(settings)
    docs = store.list_documents(tenant_id)
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "tenant_id": d.tenant_id,
            "source_type": d.source_type,
            "page_count": d.page_count,
            "chunk_count": d.chunk_count,
            "created_at": str(d.created_at),
        }
        for d in docs
    ]


if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run("src.main:app", host=cfg.api_host, port=cfg.api_port, reload=True)
