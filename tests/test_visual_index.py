"""The visual (ColPali) index must return each page ONCE, and a re-ingest must replace.

Two defects are pinned here (IMPROVEMENTS.md §B4b):

  - **read path** — the index can hold more than one vector per page (three, after three
    Phase-3 runs). ``DocumentStore.visual_search`` must collapse duplicates by
    ``page_number`` and still return the caller's requested number of DISTINCT pages.
  - **write path** — ``save_colpali_embeddings`` used to key points on a fresh
    ``page_image_id`` each run and never delete the old ones, so every re-ingest added
    another full copy. It must now delete the (document_id, page_number) it is about to
    write, so the index holds one vector per page.

No model, no network: the stub ColPali embedder and in-memory Qdrant.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from src.core.config import Settings
from src.pdf_ingestion.colpali_embedder import StubColPaliEmbedder


@pytest.fixture
def p3_settings(tmp_path):
    return Settings(
        use_stub_embedder=True,
        use_stub_llm=True,
        use_stub_colpali=True,
        use_stub_graph=True,
        qdrant_in_memory=True,
        sqlite_url=f"sqlite:///{tmp_path}/test_visual_index.db",
        page_images_dir=str(tmp_path / "page_images"),
        debug=False,
    )


def _png_bytes() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


def _ingest(p3_settings, sample_pdf) -> str:
    from src.pdf_ingestion.store import ingest_pdf
    return ingest_pdf(
        pdf_path=str(sample_pdf), tenant_id="global", source_type="base_textbook",
        is_global_baseline=True, settings=p3_settings,
    )["document_id"]


def _upsert_page(store, cfg, *, doc_id, page_number, tenant_id="global"):
    """Write one visual point directly — simulates a previous Phase-3 run's vector.

    The point id is a fresh uuid, exactly as a real ingest mints one per page image;
    that is what makes a re-ingest accumulate unless the write path deletes first.
    """
    import uuid
    point_id = str(uuid.uuid4())
    rng = np.random.default_rng(page_number)
    patches = rng.random((StubColPaliEmbedder.STUB_PATCHES, StubColPaliEmbedder.STUB_DIM))
    patches = patches / (np.linalg.norm(patches, axis=1, keepdims=True) + 1e-9)
    store._qdrant.upsert(
        collection_name=cfg.colpali_collection,
        points=[PointStruct(
            id=point_id,
            vector={"colpali": patches.astype(np.float32).tolist()},
            payload={
                "tenant_id": tenant_id, "source_type": "page_image",
                "is_global_baseline": True, "document_id": doc_id,
                "page_image_id": point_id, "page_number": page_number,
                "image_key": f"page_{page_number:04d}.png",
            },
        )],
    )


def _count_for_doc(store, cfg, doc_id) -> int:
    res = store._qdrant.count(
        collection_name=cfg.colpali_collection,
        count_filter=Filter(must=[
            FieldCondition(key="document_id", match=MatchValue(value=doc_id))
        ]),
        exact=True,
    )
    return int(res.count)


# ── Read path: dedupe by page ------------------------------------------------

def test_visual_search_collapses_duplicate_pages(p3_settings, sample_pdf):
    """Three vectors for one page must yield ONE result, not three."""
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(settings=p3_settings)
    doc_id = _ingest(p3_settings, sample_pdf)
    cfg = p3_settings

    for i in range(3):  # the 3x defect: three points, one page
        _upsert_page(store, cfg, doc_id=doc_id, page_number=5)

    q = StubColPaliEmbedder().embed_query_text("the diagram of a pendulum")
    results = store.visual_search(
        query_patches=q, tenant_id="global", limit=5, score_threshold=0.0,
    )
    pages = [r["page_number"] for r in results]
    assert pages == [5], f"expected one distinct page, got {pages}"


def test_visual_search_returns_limit_distinct_pages(p3_settings, sample_pdf):
    """With duplicates present, `limit` still means `limit` DISTINCT pages."""
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(settings=p3_settings)
    doc_id = _ingest(p3_settings, sample_pdf)
    cfg = p3_settings

    for page in (11, 12, 13):
        for i in range(3):  # each page stored three times
            _upsert_page(store, cfg, doc_id=doc_id, page_number=page)

    q = StubColPaliEmbedder().embed_query_text("a wave diagram")
    results = store.visual_search(
        query_patches=q, tenant_id="global", limit=3, score_threshold=0.0,
    )
    pages = [r["page_number"] for r in results]
    assert len(pages) == 3, f"over-fetch did not recover 3 distinct pages: {pages}"
    assert len(set(pages)) == 3, f"duplicate pages returned: {pages}"


def test_visual_search_dedupe_can_be_disabled(p3_settings, sample_pdf):
    """dedupe_by_page=False returns raw points — the escape hatch stays honest."""
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(settings=p3_settings)
    doc_id = _ingest(p3_settings, sample_pdf)
    cfg = p3_settings

    for i in range(3):
        _upsert_page(store, cfg, doc_id=doc_id, page_number=7)

    q = StubColPaliEmbedder().embed_query_text("anything")
    results = store.visual_search(
        query_patches=q, tenant_id="global", limit=3,
        score_threshold=0.0, dedupe_by_page=False,
    )
    assert len(results) == 3
    assert {r["page_number"] for r in results} == {7}


# ── Write path: replace, don't accumulate ------------------------------------

def test_save_colpali_embeddings_replaces_stale_vectors(p3_settings, sample_pdf):
    """Re-writing a page must remove the previous run's vector for that page."""
    from src.pdf_ingestion.parser import PageContent
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(settings=p3_settings)
    doc_id = _ingest(p3_settings, sample_pdf)
    cfg = p3_settings

    records = store.save_page_images(
        doc_id, [PageContent(page_number=1, text="p1", image_bytes=_png_bytes())],
        settings=p3_settings,
    )
    # A previous run left its own vector for the same (document, page).
    _upsert_page(store, cfg, doc_id=doc_id, page_number=1)
    assert _count_for_doc(store, cfg, doc_id) == 1

    patches = StubColPaliEmbedder().embed_pages([None])
    store.save_colpali_embeddings(
        records, patches, tenant_id="global", is_global_baseline=True,
        source_type="page_image",
    )

    # The stale point is gone; exactly the new one remains.
    assert _count_for_doc(store, cfg, doc_id) == 1, "re-ingest accumulated a duplicate"
    stored = store._qdrant.retrieve(
        collection_name=cfg.colpali_collection,
        ids=[records[0].colpali_point_id], with_payload=True,
    )
    assert len(stored) == 1
    assert (stored[0].payload or {}).get("page_number") == 1
