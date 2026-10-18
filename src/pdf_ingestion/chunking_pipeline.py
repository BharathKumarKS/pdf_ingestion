"""Chunking pipeline orchestrator (E1/E2/E3) — the re-ingest's write path.

Mirrors the class repo's ``Labs/Week_6/sv_rag_pipeline/src/svrag/chunking_pipeline.py``:
one module per stage, and this file is the only place that knows the order they run in.

    PDF ──ParentChunker.convert──> DoclingDocument + ParentChunk[]        (E2)
         └─ SemanticChunker.chunk_parents──> TextChunk[] (children)       (E1)
              └─ LateChunkEmbedder.embed_children──> EnrichedChunk[]      (E3)
                   └─ DocumentStore.save_document──> Qdrant + SQLite

Why the order matters:

* children are cut **inside** a parent, so a child never spans two sections, and its
  ``page_number`` comes from the parent's provenance map (§D4) rather than chunk-start fuzz;
* the late-chunk embedder embeds each **parent** once (one cluster call per parent) and
  mean-pools the token vectors inside each child's span, so a child that opens *"This is
  proportional to…"* carries its antecedent's hidden states (E3).

``store.ingest_pdf`` delegates here, so there is exactly one ingest path: the script, the
UI's upload path and the tests all build the same index.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import SemanticChunker
from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder
from src.pdf_ingestion.parent_chunker import ParentChunker
from src.pdf_ingestion.parser import ParsedDocument
from src.pdf_ingestion.store import DocumentStore


class ChunkingPipeline:
    """Parse → parents → semantic children → late-chunked vectors → store.

    Every stage is injectable so tests can run the whole pipeline without Docling, a
    tokenizer download or the cluster.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        parent_chunker: ParentChunker | None = None,
        chunker: SemanticChunker | None = None,
        embedder: LateChunkEmbedder | None = None,
        store: DocumentStore | None = None,
    ) -> None:
        self._cfg = settings or get_settings()
        self._parent_chunker = parent_chunker or ParentChunker(settings=self._cfg)
        self._chunker = chunker or SemanticChunker(settings=self._cfg)
        self._embedder = embedder or LateChunkEmbedder(settings=self._cfg)
        self._store = store or DocumentStore(settings=self._cfg)

    # -- Public API ------------------------------------------------------------

    def _make_cache(self, path: Path):
        """The resume cache for this document, or ``None`` when disabled.

        Constructed here rather than in ``__init__`` because the key needs the PDF, and the
        fingerprint reads it — so this is the first point that can know what the cache is valid
        for. A cache is a pure optimisation: any failure to build one must degrade to
        ``None`` (embed everything), never abort the ingest.
        """
        if not getattr(self._cfg, "embed_cache_enabled", False):
            return None
        try:
            from src.pdf_ingestion.embed_cache import EmbeddingCache, fingerprint

            cache = EmbeddingCache(self._cfg.embed_cache_dir, fingerprint(path, self._cfg))
            logger.info("Late-chunk resume cache: {}", cache.directory)
            return cache
        except Exception as exc:  # noqa: BLE001 - never fail an ingest over a cache
            logger.warning("Resume cache unavailable ({}: {}) — embedding everything",
                           type(exc).__name__, exc)
            return None

    def process_pdf(
        self,
        pdf_path: str,
        tenant_id: str,
        source_type: str,
        is_global_baseline: bool,
        extra_meta: dict | None = None,
        document_id: str | None = None,
    ) -> dict:
        """Ingest one PDF. Returns the same summary dict ``store.ingest_pdf`` returns."""
        path = Path(pdf_path)
        meta = extra_meta or {}
        doc_id = document_id or str(uuid.uuid4())

        doc, parents = self._parent_chunker.convert(path)
        if not parents:
            raise ValueError(f"No parent chunks produced from {pdf_path}")

        children = self._chunker.chunk_parents(doc_id, tenant_id, parents)
        if not children:
            raise ValueError(f"No chunks produced from {pdf_path}")

        cache = self._make_cache(path)
        enriched = self._embedder.embed_children(parents, children, cache=cache)

        parsed = _parsed_document(doc, path, parents, doc_id, meta)
        saved_id = self._store.save_document(
            parsed_doc=parsed,
            embedded_chunks=enriched,
            tenant_id=tenant_id,
            source_type=source_type,
            is_global_baseline=is_global_baseline,
            extra_meta={**meta, "source_path": str(path.resolve())},
        )

        logger.success(
            "Ingested '{}' → {} parents → {} children ({} pages)",
            path.name, len(parents), len(enriched), parsed.page_count,
        )
        return {
            "document_id": saved_id,
            "filename":    path.name,
            "page_count":  parsed.page_count,
            "parent_count": len(parents),
            "chunk_count": len(enriched),
            "tenant_id":   tenant_id,
            "source_type": source_type,
        }


# -- Internals -----------------------------------------------------------------

def _page_count(doc, parents) -> int:
    """PDF pages in the Docling document, falling back to the provenance maps.

    ``DoclingDocument.pages`` is the authority; the fallback keeps a converted document
    that exposes no page table (a test fake, or a Docling change) from reporting 0.
    """
    pages = getattr(doc, "pages", None)
    if pages:
        return len(pages)
    seen = {p for parent in parents for p in parent.page_numbers}
    return max(seen) if seen else 0


def _parsed_document(doc, path: Path, parents, doc_id: str, meta: dict) -> ParsedDocument:
    """A ``ParsedDocument`` for the storage layer, built from the parents.

    ``save_document`` and the payload builder read only ``document_id``, ``filename``,
    ``title`` and ``page_count`` from it. ``full_text`` is the parents' text joined in
    order — the same text the children were cut from, so it stays truthful.

    ``pages`` is deliberately **empty** on this path: per-page text is no longer carried
    (each ``ParentChunk`` carries a char→page map instead), and synthesising page objects
    here would create a second source of truth for page numbers. Nothing downstream reads
    the field on this path.
    """
    return ParsedDocument(
        document_id=doc_id,
        filename=path.name,
        full_text="\n\n".join(p.text for p in parents),
        pages=[],
        page_count=_page_count(doc, parents),
        char_count=sum(len(p.text) for p in parents),
        title=meta.get("title"),
    )
