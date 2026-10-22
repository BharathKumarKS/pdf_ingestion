#!/usr/bin/env python3
"""
Re-embed existing SQLite chunks into Qdrant without touching SQLite.

Use this when Qdrant is empty (points_count=0) but SQLite has valid chunk
records and cards. Re-embeds all chunks for a tenant/document and upserts
them to Qdrant using the existing qdrant_point_id values so card chunk_id
references remain valid.

⚠️ CURRENTLY REFUSES (IMPROVEMENTS.md §I13). It computes only the dense lane, while the collection
carries four (`dense_64`, `dense_1024`, `colbert`, `sparse`). A dense-only upsert is accepted by
Qdrant and leaves the ColBERT and SPLADE stages of the funnel empty — a degraded index that looks
recovered. Until the script is extended to recompute every lane (reusing the ingest's payload
builder), it exits with the reason rather than writing one. Rebuild with
`scripts/ingest_base_textbook.py --reindex` instead.

After running this, re-run RAPTOR:
    uv run python scripts/run_phase2.py --tenant global --raptor-only

Usage:
    uv run python scripts/reembed_chunks.py --tenant global
    uv run python scripts/reembed_chunks.py --doc-id <uuid>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="Re-embed SQLite chunks into Qdrant")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tenant", help="Re-embed all documents for this tenant")
    g.add_argument("--doc-id", help="Re-embed a specific document")
    p.add_argument("--batch", type=int, default=8, help="Embedding batch size (default 8, use 32 on GPU)")
    return p.parse_args()


def _refuse_partial_payload(cfg, qdrant) -> None:
    """Refuse when the collection expects lanes this script does not compute.

    See the block in `reembed_document`. Qdrant happily accepts a point with named vectors ABSENT,
    so a dense-only write "succeeds" and quietly yields a collection whose ColBERT and SPLADE
    stages see nothing.
    """
    try:
        params = qdrant.get_collection(cfg.qdrant_collection).config.params
        vectors = params.vectors
        names = list(vectors.keys()) if hasattr(vectors, "keys") else None
        # Sparse lanes live in a SEPARATE config key, so a named-vector check alone misses them.
        sparse = getattr(params, "sparse_vectors", None)
        sparse_names = list(sparse.keys()) if sparse else []
    except Exception:
        return                      # unreadable → let the upsert speak for itself
    if not names:
        return                      # a single-vector collection: dense-only IS complete
    computed = {"dense_64", "dense_768", "dense_1024", "dense"}
    missing = sorted(n for n in names if n not in computed)
    missing += sorted(sparse_names)     # this script computes no sparse lane at all
    if missing:
        raise SystemExit(
            f"REFUSING: collection '{cfg.qdrant_collection}' expects named vectors "
            f"{sorted(names)}, and this script computes only the dense lane(s). Writing it would "
            f"leave {missing} ABSENT on every point — a silently DEGRADED index presented as a "
            f"recovered one, discovered at the worst possible moment. Rebuild with the ingest "
            f"instead (IMPROVEMENTS.md §I13):\n"
            f"    uv run python scripts/ingest_base_textbook.py --pdf <pdf> --collection-name "
            f"{cfg.qdrant_collection} --reindex"
        )


def reembed_document(doc_id: str, batch_size: int) -> int:
    from sqlmodel import Session, select
    from qdrant_client.models import PointStruct

    from src.core.config import get_settings
    from src.core.database import get_qdrant, get_engine
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.store import DocumentStore
    from src.core.database import Chunk

    cfg      = get_settings()
    engine   = get_engine(cfg)
    qdrant   = get_qdrant(cfg)
    # The DENSE lane, not the retired 768d Nomic (§I13).
    embedder = get_cluster_embedder(cfg)
    store    = DocumentStore(cfg)

    # ── Why this refuses by default (IMPROVEMENTS.md §I13) ────────────────────
    # This script used the retired local 768d Nomic embedder and wrote `{"dense": [...]}` — or a
    # bare vector — neither of which matches the collection's NAMED vectors, so it has been broken
    # since the re-ingest (it failed at the upsert with a Qdrant vector-name error).
    #
    # Moving it onto the dense lane is NOT sufficient. `knowledge_base_v2` carries FOUR lanes on
    # every point — `dense_64`, `dense_1024`, `colbert` (128d multivector, max_sim) and the sparse
    # `sparse` — and this script computes only the dense one. A dense-only upsert succeeds, because
    # Qdrant permits absent named vectors, and leaves the ColBERT and SPLADE stages of the funnel
    # looking at nothing. That is a degraded index that LOOKS recovered.
    #
    # The register's fix — "reuse `store.save_document`'s payload builder" — is therefore a scoped
    # job: it must recompute all four lanes (the 64d MRL slice is a re-normalised truncation, not a
    # raw slice; ARCHITECTURE.md §8 trap 5), not re-point one embedder. Until that lands, refusing
    # is the correct behaviour: it is the difference between "recovery did not run" and "recovery
    # ran and produced a quietly worse index".
    _refuse_partial_payload(cfg, qdrant)

    # Load chunks from SQLite
    with Session(engine) as session:
        chunks = session.exec(
            select(Chunk)
            .where(Chunk.document_id == doc_id)
            .where(Chunk.is_active == True)
            .order_by(Chunk.chunk_index)
        ).all()

    if not chunks:
        logger.warning("No active chunks for document {}", doc_id)
        return 0

    logger.info("Re-embedding {} chunks for doc {}", len(chunks), doc_id[:8])

    upserted = 0
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(), TimeElapsedColumn(), console=console
    ) as progress:
        task = progress.add_task(f"Embedding {len(chunks)} chunks...", total=len(chunks))

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i: i + batch_size]
            texts = [c.text for c in batch]

            try:
                vectors = embedder.embed_documents(texts)
            except Exception as exc:
                logger.error("Embedding batch {}-{} FAILED: {} — {}", i, i + len(batch), type(exc).__name__, exc)
                progress.advance(task, len(batch))
                continue

            # Build the same payload that was stored during Phase 1
            points = []
            for chunk, vec in zip(batch, vectors):
                payload = {
                    "tenant_id":          chunk.tenant_id,
                    "document_id":        chunk.document_id,
                    "source_type":        "base_textbook",
                    "is_global_baseline": True,
                    "text":               chunk.text,
                    "page_number":        chunk.page_number,
                    "chunk_index":        chunk.chunk_index,
                    "char_start":         chunk.char_start,
                    "char_end":           chunk.char_end,
                    "token_count":        chunk.token_count,
                    "embedding_version":  cfg.embedding_model,
                    "title":              None,
                }
                # Named-vector collection (SPLADE hybrid) requires {"dense": [...]}
                vector = {"dense": vec.tolist()} if cfg.splade_enabled else vec.tolist()
                points.append(PointStruct(
                    id=chunk.qdrant_point_id,
                    vector=vector,
                    payload=payload,
                ))

            qdrant.upsert(
                collection_name=cfg.qdrant_collection,
                points=points,
            )
            upserted += len(points)
            progress.advance(task, len(batch))

    return upserted


def main():
    args = parse_args()

    from src.core.config import get_settings
    from src.pdf_ingestion.store import DocumentStore

    cfg   = get_settings()
    store = DocumentStore(cfg)

    if args.doc_id:
        doc_ids = [args.doc_id]
    else:
        docs = store.list_documents(tenant_id=args.tenant)
        doc_ids = [d.id for d in docs]
        if not doc_ids:
            console.print(f"[yellow]No documents for tenant '{args.tenant}'[/]")
            sys.exit(0)

    total = 0
    for doc_id in doc_ids:
        doc = next((d for d in store.list_documents() if d.id == doc_id), None)
        name = doc.filename if doc else doc_id[:8]
        console.print(f"\n[bold]Re-embedding:[/] {name}")
        n = reembed_document(doc_id, args.batch)
        console.print(f"  [green]✓[/] {n} vectors upserted")
        total += n

    console.print(f"\n[bold green]Done![/] {total} total vectors in Qdrant.")
    console.print("\nNext step — rebuild RAPTOR with real embeddings:")
    console.print("  uv run python scripts/run_phase2.py --tenant global --raptor-only")


if __name__ == "__main__":
    main()
