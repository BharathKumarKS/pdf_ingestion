#!/usr/bin/env python3
"""
Re-embed existing chunks into Qdrant without touching SQLite.

Two modes:

(a) **SQLite → Qdrant** (``--tenant`` / ``--doc-id``): the original recovery path. It computes only
    the dense lane and therefore **REFUSES** on a multi-lane collection (§I13) — a dense-only upsert
    is accepted by Qdrant and leaves the ColBERT and SPLADE stages empty, a degraded index that
    *looks* recovered.

(b) **Shape B re-embed** (``--from-collection SRC``): reads the SOURCE collection's payloads,
    recomputes the dense lanes with the configured embedder (**late-chunked**, one cluster call per
    parent), **carries the ``colbert`` and ``sparse`` lanes over** from the source (different models,
    unchanged vectors — plan §2), and upserts into the destination collection **preserving every
    point id**. This is the nomic re-ingest into ``knowledge_base_v3`` (plan §3 Stage C).

    ``--pooled`` swaps the dense construction from **late-chunked** to **pooled**: each child is
    embedded from its own ``text`` alone (``LateChunkEmbedder.embed_isolated_batch``) instead of
    mean-pooled from its parent's token vectors. §I87 measured late chunking costing nomic
    **+0.1547** coverage (RESOLVED) and §I88 established it is a **method** choice, not a pooling
    defect — so dropping it is a same-corpus, same-model, ids-preserved rewrite of the dense lanes
    only. ⚠️ ``mode`` is part of the checkpoint identity: a pooled run and a late-chunked run against
    the same ``src``/``dst`` must not resume each other's parents, or the second run skips all of
    them and reports success having written nothing.

    ⚠️ Shape B is reproducible **without re-parsing**: the source payloads carry ``text`` /
    ``parent_text`` / ``char_start`` / ``char_end`` / ``parent_id`` / ``chunk_index`` / ``page_number``,
    so the parent→child hierarchy and each child's span are reconstructed exactly. That is why the
    cards and the graph — both keyed on ``chunk_id`` — stay valid.

    ⚠️ **No child may be dropped.** The late-chunk path returns ``[]`` for an empty/whitespace parent
    and falls back to isolation embeddings when the parent tokenizes to zero tokens; every child that
    does not come back late-chunked is embedded in **isolation** here, so the ``chunk_id`` set before
    and after are equal (plan Verifier C-i).

Usage:
    # Shape B: v2 -> v3 with the configured (nomic) embedder
    unset PYTHONPATH
    export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3 \
           DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5 DENSE_DIM=768 DENSE_DIM_LOW=64 \
           QUERY_INSTRUCTION="search_query: " DOCUMENT_PREFIX="search_document: "
    uv run python -u scripts/reembed_chunks.py --from-collection knowledge_base_v2 \
        --checkpoint logs/p1/step10/reembed_v3_checkpoint.json

    # Shape B, POOLED (drop late chunking — §I88's treatment; its own checkpoint, never the
    # late-chunked one, or the run resumes parents it never embedded):
    uv run python -u scripts/reembed_chunks.py --from-collection knowledge_base_v2 --pooled \
        --checkpoint logs/p1/step10/reembed_v3_pooled_checkpoint.json

    # a smoke test on N parents (still writes):
    uv run python -u scripts/reembed_chunks.py --from-collection knowledge_base_v2 --limit-parents 2

After running this, re-run RAPTOR:
    uv run python scripts/run_phase2.py --tenant global --raptor-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="Re-embed chunks into Qdrant")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--tenant", help="Re-embed all documents for this tenant (SQLite mode)")
    g.add_argument("--doc-id", help="Re-embed a specific document (SQLite mode)")
    g.add_argument("--from-collection", dest="from_collection",
                   help="Shape B: SOURCE collection to read payloads from (e.g. knowledge_base_v2)")
    p.add_argument("--collection-name", dest="collection_name",
                   help="DESTINATION collection (default: cfg.qdrant_collection)")
    p.add_argument("--batch", type=int, default=8, help="Embedding batch size (default 8, use 32 on GPU)")
    p.add_argument("--limit-parents", dest="limit_parents", type=int, default=None,
                   help="Shape B: process only the first N parents (smoke test; still writes)")
    p.add_argument("--checkpoint", default=None,
                   help="Shape B: JSON checkpoint path; a re-run resumes past completed parents")
    p.add_argument("--pooled", action="store_true",
                   help="Shape B: embed each child POOLED from its own text (drop late chunking)")
    p.add_argument("--dry-run", action="store_true", help="Shape B: count and validate, write nothing")
    args = p.parse_args()
    if not (args.tenant or args.doc_id or args.from_collection):
        p.error("one of --tenant, --doc-id or --from-collection is required")
    return args


# ── SQLite mode (unchanged) ───────────────────────────────────────────────────

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
    # The dense lanes this script computes, under EVERY name a collection may declare them:
    # the width-free ``dense_full`` and the MRL names (``dense_128``/``dense_64``). A name
    # missing from here makes this refuse a collection it could actually write.
    computed = {"dense_128", "dense_64", "dense_768", "dense_full", "dense_1024", "dense"}
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
    # `knowledge_base_v2` carries FOUR lanes on every point — `dense_64`, `dense_1024`,
    # `colbert` (128d multivector, max_sim) and the sparse `sparse` — and this mode computes only
    # the dense one. A dense-only upsert succeeds, because Qdrant permits absent named vectors, and
    # leaves the ColBERT and SPLADE stages of the funnel looking at nothing. Use Shape B
    # (`--from-collection`) instead, which recomputes the dense lanes and carries the rest over.
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


# ── Shape B mode: source collection -> destination collection ─────────────────

def _scroll_all(client, collection: str, *, with_vectors: bool, payload_keys=None) -> list:
    """Every point in ``collection``, paged. Deterministic order is imposed by the caller."""
    out: list = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection, limit=512, offset=offset,
            with_payload=payload_keys if payload_keys is not None else True,
            with_vectors=with_vectors,
        )
        out.extend(batch)
        if offset is None:
            break
    return out


def reembed_shape_b(src_collection: str, *, batch_size: int, limit_parents: int | None,
                    checkpoint_path: Path | None, dry_run: bool, pooled: bool = False) -> dict:
    """Recompute the dense lanes into the destination collection, carrying colbert/sparse over.

    ``pooled`` selects the dense construction: ``False`` (default) = late-chunked via
    ``embed_parent``; ``True`` = pooled per child via ``embed_isolated_batch`` (§I88's treatment).
    """
    import numpy as np
    from qdrant_client.models import PointStruct, SparseVector as QSparseVector

    from src.core.config import get_settings
    from src.core.database import get_qdrant
    from src.pdf_ingestion.chunker import TextChunk
    from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder
    from src.pdf_ingestion.models import ParentChunk
    from src.pdf_ingestion.store import (
        _dense_name_from, _iter_upsert_batches, _resolve_low_lane,
    )

    cfg = get_settings()
    dst = cfg.qdrant_collection
    if src_collection == dst:
        raise SystemExit(f"REFUSING: source and destination are both {dst!r}")
    client = get_qdrant(cfg)

    # The destination's lane NAMES and the low lane's WIDTH are read off the DESTINATION
    # collection, never from cfg (§I49 Finding 1; ARCHITECTURE §8 trap 5).
    dst_params = client.get_collection(dst).config.params
    dense_name = _dense_name_from(dst_params.vectors) or "dense_full"
    low_name, low_size = _resolve_low_lane(dst_params.vectors, cfg)
    mode = "pooled" if pooled else "late_chunked"
    logger.info("Shape B: {} -> {} | dense='{}' low='{}'({}d) model='{}' prefix='{}' mode='{}'",
                src_collection, dst, dense_name, low_name, low_size,
                cfg.dense_model, cfg.document_prefix, mode)

    src_points = _scroll_all(client, src_collection, with_vectors=True)
    chunks_pts = [p for p in src_points if p.payload.get("raptor_level") is None]
    raptor_pts = [p for p in src_points if p.payload.get("raptor_level") is not None]
    logger.info("source: {} points ({} chunk / {} raptor; raptor is NOT re-embedded here)",
                len(src_points), len(chunks_pts), len(raptor_pts))

    # Group children by (document_id, parent_id) — the parent is the unit of the late-chunk call.
    groups: dict[tuple[str, int], list] = {}
    for p in chunks_pts:
        key = (p.payload["document_id"], p.payload["parent_id"])
        groups.setdefault(key, []).append(p)
    order = sorted(groups.keys())
    if limit_parents is not None:
        order = order[:limit_parents]

    # Resume: skip parents already recorded complete.
    done: set[str] = set()
    if checkpoint_path and checkpoint_path.exists():
        ck = json.loads(checkpoint_path.read_text())
        # ⚠️ `mode` is part of the identity: a pooled run must not resume a late-chunked one (or vice
        # versa) — it would skip every parent and report success having written nothing.
        if ck.get("src") == src_collection and ck.get("dst") == dst and ck.get("mode") == mode:
            done = set(ck.get("done_parents", []))
            logger.info("checkpoint: resuming, {} parents already done", len(done))
        else:
            logger.info("checkpoint ignored: identity mismatch (src/dst/mode) — starting fresh")

    lce = LateChunkEmbedder(cfg)
    if not pooled:
        _ = lce._get_tokenizer()      # load once, before the loop (never race a lazy load)

    total_children = sum(len(groups[k]) for k in order)
    logger.info("Shape B: {} parents / {} children to process", len(order), total_children)

    failures: list[dict] = []
    upserted = 0
    started = time.time()
    rate_window: list[float] = []

    for i, key in enumerate(order, 1):
        doc_id, parent_id = key
        ckey = f"{doc_id}|{parent_id}"
        if ckey in done:
            continue

        pts = groups[key]
        parent_text = pts[0].payload.get("parent_text") or ""
        parent = ParentChunk(parent_id=parent_id, text=parent_text,
                             page_map={0: pts[0].payload.get("page_number") or 1})
        children = [
            TextChunk(
                chunk_id=p.payload["chunk_id"],
                document_id=doc_id,
                tenant_id=p.payload.get("tenant_id", "global"),
                chunk_index=p.payload.get("chunk_index", 0),
                text=p.payload["text"],
                char_start=p.payload.get("char_start", 0),
                char_end=p.payload.get("char_end", 0),
                token_count=p.payload.get("token_count", 0),
                page_number=p.payload.get("page_number"),
                parent_id=parent_id,
                parent_text=parent_text,
                is_content=p.payload.get("is_content", True),
            )
            for p in sorted(pts, key=lambda q: q.payload.get("chunk_index", 0))
        ]

        t0 = time.time()
        try:
            enriched = (lce.embed_isolated_batch(children) if pooled
                        else lce.embed_parent(parent, children))
        except Exception as exc:                       # noqa: BLE001 — one bad parent must not kill the run
            failures.append({"parent": ckey, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("parent {} FAILED: {} — {}", ckey, type(exc).__name__, exc)
            continue

        by_id = {e.chunk.chunk_id: e for e in enriched}
        # ⚠️ Verifier C-i: no child may be dropped. Anything not late-chunked is embedded in isolation.
        for child in children:
            if child.chunk_id not in by_id:
                by_id[child.chunk_id] = lce.embed_isolated(child)

        points = []
        for p in pts:
            cid = p.payload["chunk_id"]
            ec = by_id.get(cid)
            if ec is None:
                failures.append({"parent": ckey, "error": f"child {cid} produced no vector"})
                continue
            vec: dict = {
                low_name:   np.asarray(ec.dense_64, dtype=np.float32).tolist(),
                dense_name: np.asarray(ec.dense_1024, dtype=np.float32).tolist(),
            }
            # Carry colbert + sparse over verbatim (same models, unchanged vectors — plan §2).
            sv = p.vector or {}
            if "colbert" in sv:
                vec["colbert"] = sv["colbert"]
            if "sparse" in sv:
                sp = sv["sparse"]
                vec["sparse"] = (QSparseVector(indices=list(sp.indices), values=list(sp.values))
                                 if hasattr(sp, "indices") else sp)
            payload = dict(p.payload)
            payload["embedding_version"] = ec.model_name or cfg.dense_model
            points.append(PointStruct(id=p.id, vector=vec, payload=payload))

        if not dry_run:
            for b in _iter_upsert_batches(points):
                client.upsert(collection_name=dst, points=b)
        upserted += len(points)

        done.add(ckey)
        dt = time.time() - t0
        rate_window.append(dt)
        if len(rate_window) > 20:
            rate_window.pop(0)
        rolling = sum(rate_window) / len(rate_window)
        logger.info("[{}/{}] parent {} doc {} -> {} children  {:.2f}s  {:,} pts  rolling {:.2f}s/parent",
                    i, len(order), parent_id, doc_id[:8], len(points), dt, upserted, rolling)

        if checkpoint_path:
            checkpoint_path.write_text(json.dumps({
                "src": src_collection, "dst": dst, "mode": mode, "done_parents": sorted(done),
                "upserted": upserted, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }))

    elapsed = time.time() - started
    logger.success("Shape B done ({}): {:,} points upserted in {:.1f}s ({:.1f} pts/s), "
                   "{} parents, {} failures",
                   mode, upserted, elapsed, (upserted / elapsed) if elapsed else 0.0,
                   len(done), len(failures))
    return {"upserted": upserted, "parents": len(done), "failures": failures, "mode": mode,
            "elapsed_s": round(elapsed, 1), "src": src_collection, "dst": dst,
            "children_expected": total_children}


def main():
    args = parse_args()

    from src.core.config import get_settings

    cfg = get_settings()
    if args.collection_name:
        cfg.qdrant_collection = args.collection_name

    if args.from_collection:
        ck = Path(args.checkpoint) if args.checkpoint else None
        res = reembed_shape_b(
            args.from_collection, batch_size=args.batch, limit_parents=args.limit_parents,
            checkpoint_path=ck, dry_run=args.dry_run, pooled=args.pooled,
        )
        console.print(f"\n[bold green]Shape B ({res['mode']}):[/] {res['upserted']:,} points into "
                      f"'{res['dst']}' from '{res['src']}' ({res['parents']} parents, "
                      f"{res['elapsed_s']}s)")
        if res["failures"]:
            console.print(f"[bold red]{len(res['failures'])} FAILURES[/] — first: {res['failures'][0]}")
            sys.exit(3)
        return

    from src.pdf_ingestion.store import DocumentStore
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
