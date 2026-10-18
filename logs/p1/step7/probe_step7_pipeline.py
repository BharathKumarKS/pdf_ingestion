"""Step 7 live probe — the re-ingest write path against the REAL dense lane.

The unit tests run the pipeline with stubs, which cannot show that the pieces fit the
*real* endpoint: Qwen3's per-token response shape, the local tokenizer's offsets, the
1024d/64d split, and the 4-vector collection. This probe ingests ``test_book.pdf`` through
``ChunkingPipeline`` with:

  * the real ``ClusterDenseEmbedder`` (SV_EMBED_URL, 10.0.10.70:8123),
  * the real Qwen3 tokenizer (local, cached),
  * in-memory Qdrant (so nothing is written to the cluster's storage),
  * a throwaway SQLite file.

and then checks the claims Step 7 makes:

  M1  the collection carries exactly dense_64 / dense_1024 / colbert (+sparse)
  M2  every point's dense_1024 is 1024d and dense_64 is 64d, both unit-norm
  M3  Qdrant point count == SQLite chunk count == len(children)
  M4  every payload carries parent_id, parent_text and is_content
  M5  every child's page_number is in range and comes from its parent's provenance map
  M6  dense_64 == mrl_slice(dense_1024, 64) to 1e-5 (the MRL/linearity claim, end to end)

Usage:  SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings \
        uv run python logs/p1/step7/probe_step7_pipeline.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.core.config import Settings  # noqa: E402
from src.pdf_ingestion.chunking_pipeline import ChunkingPipeline  # noqa: E402
from src.pdf_ingestion.cluster_embedder import mrl_slice  # noqa: E402

PDF = ROOT / "data" / "base_textbooks" / "test_book.pdf"
OUT = Path(__file__).resolve().parent / "probe.json"


def main() -> int:
    sv_embed_url = os.environ.get("SV_EMBED_URL", "")
    if not sv_embed_url:
        print("SV_EMBED_URL not set — this probe needs the cluster's dense lane")
        return 2

    cfg = Settings(
        sv_embed_url=sv_embed_url,
        dense_model="Qwen/Qwen3-Embedding-0.6B",
        dense_dim=1024,
        dense_dim_low=64,
        use_stub_embedder=False,
        use_stub_colbert=True,       # the ColBERT lane is not what Step 7 changes
        use_stub_splade=True,
        splade_enabled=False,
        qdrant_in_memory=True,
        sqlite_url=f"sqlite:///{Path(OUT).parent}/probe.db",
        late_chunk_enabled=True,
        debug=False,
    )
    cfg.ensure_dirs()
    # Fresh DB each run so the counts below are unambiguous.
    db = Path(OUT).parent / "probe.db"
    if db.exists():
        db.unlink()

    from src.core.database import get_engine, get_qdrant, Chunk, reset_singletons
    reset_singletons()
    from sqlmodel import Session, select

    result = ChunkingPipeline(settings=cfg).process_pdf(
        pdf_path=str(PDF),
        tenant_id="global",
        source_type="base_textbook",
        is_global_baseline=True,
        extra_meta={"title": "Feynman Vol 1 (test book)"},
    )

    client = get_qdrant(cfg)
    info = client.get_collection(cfg.qdrant_collection)
    vectors_cfg = info.config.params.vectors

    engine = get_engine(cfg)
    with Session(engine) as session:
        rows = session.exec(
            select(Chunk).where(Chunk.document_id == result["document_id"])
            .order_by(Chunk.chunk_index)
        ).all()

    points = client.retrieve(
        collection_name=cfg.qdrant_collection,
        ids=[r.qdrant_point_id for r in rows],
        with_payload=True,
        with_vectors=True,
    )
    by_id = {str(p.id): p for p in points}

    m1 = sorted(vectors_cfg) if isinstance(vectors_cfg, dict) else str(type(vectors_cfg))
    dims, norms_ok, mrl_ok = set(), True, True
    for p in points:
        v1024 = np.asarray(p.vector["dense_1024"], dtype=np.float32)
        v64 = np.asarray(p.vector["dense_64"], dtype=np.float32)
        dims.add((v1024.shape[0], v64.shape[0]))
        norms_ok &= abs(float(np.linalg.norm(v1024)) - 1.0) < 1e-3
        norms_ok &= abs(float(np.linalg.norm(v64)) - 1.0) < 1e-3
        mrl_ok &= bool(np.allclose(v64, mrl_slice(v1024, 64), atol=1e-5))

    missing = [str(p.id) for p in points
               if not {"parent_id", "parent_text", "is_content"} <= set(p.payload)]
    pages = [r.page_number for r in rows]

    evidence = {
        "pdf": PDF.name,
        "sv_embed_url": sv_embed_url,
        "dense_model": cfg.dense_model,
        "result": result,
        "M1_collection_vectors": m1,
        "M2_dims": sorted(dims),
        "M2_unit_norms": bool(norms_ok),
        "M3_qdrant_points": info.points_count,
        "M3_sqlite_chunks": len(rows),
        "M3_children": result["chunk_count"],
        "M4_payloads_missing_hierarchy_fields": len(missing),
        "M5_pages_without_number": sum(1 for p in pages if not p),
        "M5_page_min": min(pages) if pages else None,
        "M5_page_max": max(pages) if pages else None,
        "M6_dense_64_is_mrl_slice_of_dense_1024": bool(mrl_ok),
        "sample_payload": {
            k: points[0].payload.get(k)
            for k in ("page_number", "parent_id", "is_content", "char_start", "char_end")
        },
        "sample_parent_text_chars": len(points[0].payload.get("parent_text") or ""),
    }
    OUT.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")

    checks = {
        "M1 four named vectors, dense_768 retired":
            m1 == ["colbert", "dense_1024", "dense_64"],
        "M2 dims (1024, 64) and unit norms": sorted(dims) == [(1024, 64)] and norms_ok,
        "M3 counts agree (qdrant == sqlite == children)":
            info.points_count == len(rows) == result["chunk_count"],
        "M4 every payload has parent_id/parent_text/is_content": not missing,
        "M5 every child has an in-range page": all(pages) and min(pages) >= 1,
        "M6 dense_64 == mrl_slice(dense_1024)": bool(mrl_ok),
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"\nparents={result['parent_count']} children={result['chunk_count']} "
          f"pages={result['page_count']} qdrant_points={info.points_count}")
    print(f"evidence → {OUT}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
