"""Phase 3 — the VISUAL write for the current doc, WITHOUT the slow Docling re-parse.

Rasterizes with PyMuPDF (0.03 s/page) instead of Docling (~2 h for 968 pages), then runs the SAME
ColPali path the pipeline uses (get_colpali_embedder -> embed_pages -> save_colpali_embeddings).

Writes visual_knowledge_base for ONE document. The Memgraph graph is NOT touched (it already exists).
Checkpointed per batch, so a crash resumes.

Verifier at each stage:
  Stage A  rasterize + save page images   -> V-A1..V-A3
  Stage B  ColPali embed + upsert         -> V-B1..V-B3
  Stage C  final: read-back + old-doc guard -> V-C1..V-C3

Usage:
  python logs/p1/step10/phase3_visual_write.py --doc-id 7ba61432-... [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import fitz  # PyMuPDF
from loguru import logger
from PIL import Image

from src.core.config import get_settings
from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
from src.pdf_ingestion.store import DocumentStore

CURRENT_DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
OLD_DOC = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"
CHECKPOINT = Path("logs/p1/step10/phase3_visual_checkpoint.json")
DPI = 150
BATCH = 4

RESULTS: list = []


def check(cid, ok, detail=""):
    RESULTS.append({"id": cid, "pass": bool(ok), "detail": detail})
    logger.info("  {}  {}  {}", "PASS" if ok else "FAIL", cid, detail)
    return ok


def _retry(fn, *a, tries=4, **kw):
    """Qdrant/network calls time out intermittently on this shared cluster; retry before giving up."""
    last = None
    for i in range(tries):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("attempt {}/{} failed: {}", i + 1, tries, exc)
            time.sleep(4 * (i + 1))
    raise last


@dataclass
class _Page:
    page_number: int
    image_bytes: bytes


def _qdrant_doc_count(store, doc_id: str) -> int:
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    flt = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
    return store._qdrant.count(collection_name=store._cfg.colpali_collection, count_filter=flt, exact=True).count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", default=CURRENT_DOC)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="re-rasterize even if page images exist")
    args = ap.parse_args()

    cfg = get_settings()
    store = DocumentStore(cfg)
    doc_id = args.doc_id

    # ── Stage 0 — pre-flight ──────────────────────────────────────────────
    logger.info("=== Stage 0 — pre-flight ===")
    doc = None
    from sqlmodel import Session as S
    from src.core.database import Document
    with S(store._engine) as s:
        doc = s.get(Document, doc_id)
    check("V-0.1 doc_exists", doc is not None, f"doc={doc_id}")
    if not doc:
        return 2
    pdf_path = doc.source_path
    check("V-0.2 pdf_exists", bool(pdf_path) and Path(pdf_path).exists(), str(pdf_path))
    old_before = _qdrant_doc_count(store, OLD_DOC)
    check("V-0.3 old_doc_vectors_recorded", old_before > 0, f"old doc {OLD_DOC}: {old_before} points")
    logger.info("target doc {} status={} pages={} | old doc points={}", doc_id, doc.colpali_status, doc.page_count, old_before)

    pdf = fitz.open(pdf_path)
    n_pages = pdf.page_count
    check("V-0.4 page_count", n_pages == doc.page_count, f"pdf={n_pages} doc={doc.page_count}")
    if args.limit:
        n_pages = min(n_pages, args.limit)

    # ── Stage A — rasterize + save page images ────────────────────────────
    logger.info("=== Stage A — rasterize {} pages @ {} dpi ===", n_pages, DPI)
    existing = store.get_page_images(doc_id)
    if existing and not args.force:
        logger.info("page images already exist ({}) — reusing", len(existing))
        records = existing
        check("V-A1.1 reused_existing", True, f"{len(records)} records")
    else:
        t = time.time()
        pages = []
        for i in range(n_pages):
            pix = pdf[i].get_pixmap(dpi=DPI)
            pages.append(_Page(page_number=i + 1, image_bytes=pix.tobytes("png")))
        raster_s = time.time() - t
        logger.info("rasterized {} pages in {:.1f}s ({:.3f}s/page)", len(pages), raster_s, raster_s / len(pages))
        if args.dry_run:
            check("V-A0 dry_run_rasterize_only", len(pages) == n_pages, f"{len(pages)} pages, no write")
            return 0
        records = store.save_page_images(document_id=doc_id, pages=pages, settings=cfg)
        check("V-A1.1 saved_count", len(records) == len(pages), f"saved={len(records)} pages={len(pages)}")
    check("V-A2 all_have_image_key", all(r.image_key for r in records), "")
    check("V-A3 all_active", all(getattr(r, "is_active", True) for r in records), "")

    # ── Stage B — ColPali embed + upsert (checkpointed) ───────────────────
    logger.info("=== Stage B — ColPali embed {} pages in batches of {} ===", len(records), BATCH)
    colpali = get_colpali_embedder(cfg)
    ck = json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {}
    done_batches = set(ck.get(doc_id, []))
    if done_batches:
        logger.info("resuming: {} batches already done", len(done_batches))

    t0 = time.time()
    n_written = 0
    n_batches = (len(records) + BATCH - 1) // BATCH
    for bi, i in enumerate(range(0, len(records), BATCH)):
        if bi in done_batches:
            continue
        batch = records[i : i + BATCH]
        pil = []
        for r in batch:
            key = r.image_key
            from src.pdf_ingestion.image_store import get_image_store
            data = get_image_store(cfg).get(key)
            pil.append(Image.open(io.BytesIO(data)))
        mats = _retry(colpali.embed_pages, pil)
        n_written += _retry(store.save_colpali_embeddings,
                            page_image_records=batch, patch_matrices=mats, tenant_id=doc.tenant_id,
                            is_global_baseline=doc.is_global_baseline, source_type=doc.source_type)
        done_batches.add(bi)
        ck[doc_id] = sorted(done_batches)
        CHECKPOINT.write_text(json.dumps(ck))
        if bi % 20 == 0:
            el = time.time() - t0
            done_now = len([b for b in done_batches if b >= 0])
            logger.info("  batch {}/{}  written={}  elapsed={:.0f}s", bi + 1, n_batches, n_written, el)

    check("V-B1 all_batches_done", len(done_batches) == n_batches, f"{len(done_batches)}/{n_batches}")
    qcount = _qdrant_doc_count(store, doc_id)
    check("V-B2 qdrant_points_for_doc", qcount == len(records), f"qdrant={qcount} expected={len(records)}")
    if records:
        from src.pdf_ingestion.image_store import get_image_store
        sample = Image.open(io.BytesIO(get_image_store(cfg).get(records[0].image_key)))
        m = colpali.embed_pages([sample])[0]
        check("V-B3 patch_shape", tuple(m.shape)[1] == cfg.colpali_patch_dim, f"shape={tuple(m.shape)} dim={cfg.colpali_patch_dim}")

    # ── Stage C — final read-back ─────────────────────────────────────────
    logger.info("=== Stage C — final read-back ===")
    store.update_colpali_status(doc_id, "ready")
    hits = store.visual_search(
        query_patches=colpali.embed_query_text("a diagram of a diffraction pattern"),
        tenant_id=doc.tenant_id, limit=10, score_threshold=0.0,
    )
    mine = [h for h in hits if h.get("document_id") == doc_id]
    check("V-C1 search_returns_current_doc", len(mine) > 0, f"{len(mine)}/{len(hits)} hits from {doc_id}")
    old_after = _qdrant_doc_count(store, OLD_DOC)
    check("V-C2 old_doc_untouched", old_after == old_before, f"before={old_before} after={old_after}")
    total = store.count_visual_vectors([cfg.global_tenant_id])
    check("V-C3 total_vectors", total >= len(records), f"total={total}")

    n_pass = sum(1 for r in RESULTS if r["pass"])
    logger.info("=== {} / {} checks PASS ===", n_pass, len(RESULTS))
    Path("logs/p1/step10/phase3_visual_result.json").write_text(json.dumps(
        {"doc_id": doc_id, "n_pages": len(records), "written": n_written, "wall_s": round(time.time() - t0, 1),
         "checks": RESULTS}, indent=1))
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
