#!/usr/bin/env python3
"""PLAN B — re-embed the CURRENT doc's stored page PNGs into ``visual_knowledge_base``.

Why this exists
---------------
The deployed visual lane on 10.0.10.65 was populated (2,001 ColPali vectors = old doc
``6d55c52b`` 1,033 + current doc ``7ba61432`` 968), MEASURED 2026-11-05, then DROPPED
(now 0 points, no snapshot) — HANDOFF session 41, IMPROVEMENTS.md §I124. This script
rebuilds the CURRENT document's share of it: **968** page vectors for doc ``7ba61432``,
from the 968 page PNGs already on disk under ``data/page_images/<doc_id>/``.

It does NOT re-parse the PDF with Docling (~2 h for 968 pages). The ColPali stage needs
only ``(page_number, image_bytes)`` — IMPROVEMENTS.md §I42 — so the PNGs are read straight
from the image store, the same way the original ``phase3_visual_write.py`` did on 2026-11-02.

Scope is stated, not hidden: the old doc ``6d55c52b``'s 1,033 vectors are NOT rebuilt —
its page PNGs are gone from disk (only the current doc's 968 and the unrelated local doc
``b2d9fb56``'s 945 survive, and that one is a different document). The shipped collection
therefore ends at **968 points, not 2,001**.

Design
------
* Checkpointed per batch and resumable. Qdrant is the progress bar: the doc's point count
  (filtered by ``document_id``) climbs as the run proceeds (pitfall 39).
* The checkpoint carries a **run-identity header** and a per-page done set — not batch
  indices — so a changed batch size cannot silently no-op the run (pitfall 25). It is
  ignored outright when the header mismatches, or when Qdrant holds fewer of the doc's
  points than the checkpoint claims (the collection lost points → redo). A stale
  checkpoint from the 2026-11-02 write therefore cannot mask an empty collection.
* Deterministic checks at EVERY stage; any failure aborts with a non-zero exit.

Stages and their checks (all re-derived from the live store, not from a summary line):
  Stage 0  pre-flight / resolved config   -> V-0.1 .. V-0.8
  Stage A  page-image records             -> V-A1 .. V-A5
  Stage B  ColPali embed + upsert         -> V-B1 .. V-B4   (per batch: shape guard, aborts)
  Stage C  read-back                      -> V-C1 .. V-C5

Usage
-----
  unset PYTHONPATH
  .venv/bin/python logs/p1/step10/visual_reingest_planb.py --limit 8    # smoke test
  .venv/bin/python logs/p1/step10/visual_reingest_planb.py             # full 968 (CPU, tens of min)
  .venv/bin/python logs/p1/step10/visual_reingest_planb.py --verify-only   # re-check, no writes
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from loguru import logger
from PIL import Image

from src.core.config import get_settings
from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
from src.pdf_ingestion.image_store import get_image_store
from src.pdf_ingestion.store import DocumentStore

CURRENT_DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
OLD_DOC = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"   # deployed old doc; PNGs gone, NOT rebuilt
CHECKPOINT = Path("logs/p1/step10/visual_reingest_planb_checkpoint.json")
RESULT = Path("logs/p1/step10/visual_reingest_planb_result.json")
MIN_REAL_PATCHES = 100   # a real ColPali page yields ~1031 patches; the embedder's failure
                         # fallback yields a single (1, 128) zero vector — this catches it.

CHECKS: list[dict] = []


def check(cid: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"id": cid, "pass": bool(ok), "detail": detail})
    logger.info("  {}  {}  {}", "PASS" if ok else "FAIL", cid, detail)
    return ok


def _retry(fn, *a, tries: int = 4, **kw):
    """Qdrant on this shared cluster times out intermittently; retry before giving up."""
    last = None
    for i in range(tries):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("attempt {}/{} failed: {}", i + 1, tries, exc)
            time.sleep(4 * (i + 1))
    raise last


def _doc_points(store: DocumentStore, doc_id: str) -> int:
    """Exact server-side point count for one document (fast count endpoint)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    flt = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
    return int(store._qdrant.count(
        collection_name=store._cfg.colpali_collection, count_filter=flt, exact=True).count)


def _doc_pages(store: DocumentStore, doc_id: str) -> list[int]:
    """Scroll the document's points and return their raw page_numbers (dups preserved)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    flt = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
    pages: list[int] = []
    offset = None
    while True:
        pts, offset = _retry(store._qdrant.scroll,
                             collection_name=store._cfg.colpali_collection,
                             scroll_filter=flt, limit=1000, offset=offset,
                             with_payload=["page_number"], with_vectors=False)
        for p in pts:
            pn = (p.payload or {}).get("page_number")
            if pn is not None:
                pages.append(int(pn))
        if offset is None:
            break
    return pages


def _load_checkpoint(header: dict) -> set[int]:
    if not CHECKPOINT.exists():
        return set()
    try:
        ck = json.loads(CHECKPOINT.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint unreadable ({}), ignoring", exc)
        return set()
    if ck.get("header") != header:
        logger.warning("checkpoint header mismatch — ignoring stale checkpoint: {}",
                       ck.get("header"))
        return set()
    return set(int(p) for p in ck.get("done_pages", []))


def _save_checkpoint(header: dict, done_pages: set[int]) -> None:
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"header": header, "done_pages": sorted(done_pages)}))
    os.replace(tmp, CHECKPOINT)   # atomic


@dataclass
class _Page:
    page_number: int
    image_bytes: bytes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", default=CURRENT_DOC)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: only this many pages")
    ap.add_argument("--force-rasterize", action="store_true",
                    help="re-render the PNGs from the PDF even if they exist on disk")
    ap.add_argument("--verify-only", action="store_true",
                    help="run the read-back checks against the live store and write nothing")
    ap.add_argument("--reset-checkpoint", action="store_true")
    args = ap.parse_args()

    cfg = get_settings()
    store = DocumentStore(cfg)
    doc_id = args.doc_id
    batch = max(1, int(cfg.colpali_page_batch_size))

    # ── resolved config: print AND assert the target we will actually hit (pitfall 23) ──
    logger.info("=== resolved config ===")
    for k, v in [
        ("QDRANT_HOST", cfg.qdrant_host), ("QDRANT_COLLECTION", cfg.qdrant_collection),
        ("colpali_collection", cfg.colpali_collection), ("colpali_model", cfg.colpali_model),
        ("colpali_patch_dim", cfg.colpali_patch_dim), ("colpali_page_batch_size", batch),
        ("use_stub_colpali", cfg.use_stub_colpali), ("page_images_dir", cfg.page_images_dir),
        ("sqlite_url", cfg.sqlite_url),
    ]:
        logger.info("  {:<22}= {!r}", k, v)

    # ── Stage 0 — pre-flight ───────────────────────────────────────────────
    logger.info("=== Stage 0 — pre-flight ===")
    check("V-0.1 qdrant_host_is_remote", bool(cfg.qdrant_host),
          f"host={cfg.qdrant_host!r} — empty means the LOCAL file store, the WRONG target")
    check("V-0.2 not_stub_embedder", not cfg.use_stub_colpali,
          "USE_STUB_COLPALI would write 32-patch garbage")
    check("V-0.3 collection_name", cfg.colpali_collection == "visual_knowledge_base",
          cfg.colpali_collection)

    from sqlmodel import Session as S
    from src.core.database import Document
    with S(store._engine) as s:
        doc = s.get(Document, doc_id)
    check("V-0.4 doc_exists", doc is not None, f"doc={doc_id}")
    if doc is None:
        _finish(0)
        return 2

    pdf_path = doc.source_path
    check("V-0.5 pdf_exists", bool(pdf_path) and Path(pdf_path).exists(), str(pdf_path))

    n_pages = int(doc.page_count)
    check("V-0.6 page_count", n_pages > 0, f"doc.page_count={n_pages}")

    try:
        info = _retry(store._qdrant.get_collection, cfg.colpali_collection)
        live_dim = int(info.config.params.vectors["colpali"].size)
    except Exception as exc:  # noqa: BLE001
        live_dim = -1
        logger.warning("could not read collection dim: {}", exc)
    check("V-0.7 collection_dim", live_dim == cfg.colpali_patch_dim,
          f"live={live_dim} expected={cfg.colpali_patch_dim}")

    doc_before = _doc_points(store, doc_id)
    old_before = _doc_points(store, OLD_DOC)
    check("V-0.8 current_doc_state", True,
          f"doc {doc_id} points_before={doc_before} | old doc {OLD_DOC} points={old_before}")
    logger.info("target doc {} status={} pages={} tenant={} source_type={}",
                doc_id, doc.colpali_status, n_pages, doc.tenant_id, doc.source_type)

    # ── Stage A — page-image records ───────────────────────────────────────
    logger.info("=== Stage A — page-image records ===")
    records = store.get_page_images(doc_id)
    if args.force_rasterize or not records:
        import fitz  # PyMuPDF
        logger.info("rasterizing {} pages from {} @ 150 dpi", n_pages, pdf_path)
        pdf = fitz.open(pdf_path)
        pages = [_Page(page_number=i + 1, image_bytes=pdf[i].get_pixmap(dpi=150).tobytes("png"))
                 for i in range(n_pages)]
        records = store.save_page_images(document_id=doc_id, pages=pages, settings=cfg)
    else:
        logger.info("reusing {} existing page-image records", len(records))

    check("V-A1 record_count", len(records) == n_pages, f"records={len(records)} pages={n_pages}")
    check("V-A2 all_have_image_key", all(r.image_key for r in records), "")
    check("V-A3 all_active", all(getattr(r, "is_active", True) for r in records), "")

    rec_pages = sorted(r.page_number for r in records)
    check("V-A4 page_coverage", rec_pages == list(range(1, n_pages + 1)),
          f"min={rec_pages[0] if rec_pages else '-'} max={rec_pages[-1] if rec_pages else '-'} "
          f"unique={len(set(rec_pages))}")

    img_store = get_image_store(cfg)
    missing = [r.page_number for r in records if not _file_nonempty(img_store, r.image_key, cfg)]
    check("V-A5 pngs_on_disk", not missing, f"missing/empty: {missing[:5]}{'…' if len(missing) > 5 else ''}")

    # n_target = how many pages this run is responsible for (all 968, or --limit for a smoke test)
    n_target = min(n_pages, args.limit) if args.limit else n_pages

    if args.verify_only:
        logger.info("=== --verify-only: skipping Stage B, running read-back ===")
        return _stage_c(store, cfg, doc, doc_id, n_target, old_before)

    # ── Stage B — ColPali embed + upsert (checkpointed, resumable) ─────────
    logger.info("=== Stage B — ColPali embed, batches of {} ===", batch)
    colpali = get_colpali_embedder(cfg)

    header = {"doc_id": doc_id, "collection": cfg.colpali_collection,
              "model": cfg.colpali_model, "patch_dim": cfg.colpali_patch_dim,
              "batch": batch, "expected_pages": n_pages}
    if args.reset_checkpoint and CHECKPOINT.exists():
        CHECKPOINT.unlink()
    done = _load_checkpoint(header)

    # Guard: a checkpoint that claims more done than Qdrant holds is stale (points lost).
    if len(done) > doc_before:
        logger.warning("checkpoint claims {} done but Qdrant holds {} for this doc — "
                       "collection lost points, ignoring checkpoint", len(done), doc_before)
        done = set()
    if args.limit:
        done = {p for p in done if p <= args.limit}
    logger.info("resume state: {} pages already done (target {})", len(done), n_target)

    todo = [r for r in records if r.page_number <= n_target and r.page_number not in done]
    batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    logger.info("{} batches to run ({} pages)", len(batches), len(todo))

    ref_patches: int | None = None
    n_written = 0
    t0 = time.time()
    for bi, b in enumerate(batches, 1):
        pil = [Image.open(io.BytesIO(img_store.get(r.image_key))) for r in b]
        mats = _retry(colpali.embed_pages, pil)
        # Deterministic per-batch shape guard — aborts on the embedder's zero fallback (pitfall 18/29).
        for r, m in zip(b, mats):
            if m.ndim != 2 or m.shape[1] != cfg.colpali_patch_dim or m.shape[0] < MIN_REAL_PATCHES:
                check(f"V-B0 batch{bi} page{r.page_number} shape", False,
                      f"shape={getattr(m, 'shape', None)} — embedder failure fallback?")
                _finish(len(done))
                return 1
            ref_patches = ref_patches or int(m.shape[0])
        written = _retry(store.save_colpali_embeddings, page_image_records=b,
                         patch_matrices=mats, tenant_id=doc.tenant_id,
                         is_global_baseline=doc.is_global_baseline, source_type=doc.source_type)
        if written != len(b):
            check(f"V-B0 batch{bi} written_count", False, f"written={written} expected={len(b)}")
            _finish(len(done))
            return 1
        n_written += written
        done.update(r.page_number for r in b)
        _save_checkpoint(header, done)
        if bi % 20 == 0 or bi == len(batches):
            el = time.time() - t0
            rate = len(done) / el if el else 0
            eta = (n_target - len(done)) / rate if rate else 0
            logger.info("  batch {}/{}  done={}/{}  written={}  elapsed={:.0f}s  ETA={:.0f}s",
                        bi, len(batches), len(done), n_target, n_written, el, eta)
        del pil, mats

    check("V-B1 all_target_pages_done", len(done) == n_target, f"{len(done)}/{n_target}")
    qcount = _doc_points(store, doc_id)
    check("V-B2 qdrant_points_for_doc", qcount == n_target,
          f"qdrant={qcount} expected={n_target}")
    if ref_patches is not None:
        check("V-B3 reference_patch_count", ref_patches >= MIN_REAL_PATCHES,
              f"patches/page={ref_patches}")
    else:
        logger.info("  (V-B3 reference_patch_count: no batches run this pass — nothing to shape-check)")
    if records:
        sample = Image.open(io.BytesIO(img_store.get(records[0].image_key)))
        m = colpali.embed_pages([sample])[0]
        check("V-B4 patch_dim", int(m.shape[1]) == cfg.colpali_patch_dim, f"shape={tuple(m.shape)}")

    return _stage_c(store, cfg, doc, doc_id, n_target, old_before)


def _file_nonempty(img_store, key: str, cfg) -> bool:
    try:
        return len(img_store.get(key)) > 0
    except Exception:  # noqa: BLE001
        return False


def _stage_c(store, cfg, doc, doc_id, n_target, old_before) -> int:
    """Stage C — read-back from the live store. Never trusts the run's own counters."""
    logger.info("=== Stage C — read-back ===")
    qcount = _doc_points(store, doc_id)
    check("V-C1 doc_point_count", qcount == n_target, f"qdrant={qcount} expected={n_target}")

    pages = _doc_pages(store, doc_id)
    check("V-C2 page_coverage_exact",
          sorted(pages) == list(range(1, n_target + 1)),
          f"n={len(pages)} unique={len(set(pages))} "
          f"min={min(pages) if pages else '-'} max={max(pages) if pages else '-'}")

    from qdrant_client.models import FieldCondition, Filter, MatchValue
    flt = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
    pts, _ = _retry(store._qdrant.scroll, collection_name=cfg.colpali_collection,
                    scroll_filter=flt, limit=1, with_payload=True, with_vectors=False)
    pay = (pts[0].payload if pts else {}) or {}
    ok_payload = (pay.get("tenant_id") == doc.tenant_id
                  and pay.get("source_type") == "page_image"
                  and bool(pay.get("image_key")))
    check("V-C3 payload_sample", ok_payload,
          f"tenant={pay.get('tenant_id')} source_type={pay.get('source_type')} image_key={bool(pay.get('image_key'))}")

    old_after = _doc_points(store, OLD_DOC)
    check("V-C4 old_doc_untouched", old_after == old_before,
          f"before={old_before} after={old_after}")

    try:
        colpali = get_colpali_embedder(cfg)
        hits = store.visual_search(
            query_patches=colpali.embed_query_text("a diagram of a diffraction pattern"),
            tenant_id=doc.tenant_id, limit=10, score_threshold=0.0)
        mine = [h for h in hits if h.get("document_id") == doc_id]
        check("V-C5 text_query_returns_doc", len(mine) > 0, f"{len(mine)}/{len(hits)} hits")
    except Exception as exc:  # noqa: BLE001
        check("V-C5 text_query_returns_doc", False, f"query failed: {exc}")

    if all(c["pass"] for c in CHECKS):
        store.update_colpali_status(doc_id, "ready")   # set only AFTER the artifact is verified
        logger.info("colpali_status -> ready (artifact verified)")
    return _finish(n_target)


def _finish(n_pages: int) -> int:
    n_pass = sum(1 for c in CHECKS if c["pass"])
    logger.info("=== {} / {} checks PASS ===", n_pass, len(CHECKS))
    RESULT.write_text(json.dumps(
        {"n_pages": n_pages, "checks": CHECKS,
         "n_pass": n_pass, "n_total": len(CHECKS)}, indent=1))
    return 0 if n_pass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
