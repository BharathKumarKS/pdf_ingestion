#!/usr/bin/env python
"""S3 verifier — the Shape B re-embed's four assertions (plan §3 Stage C, Verifier C).

Read-only against both collections. Run AFTER scripts/reembed_chunks.py --from-collection.

  V1  the chunk_id set before == after, BYTE-IDENTICAL sorted list (the assertion the whole shape
      rests on) — read off the source collection and the destination collection, not off a log.
  V2  every enabled lane present on every destination CHUNK point, at the right width — asserted
      PER POINT (§I33: a count-based gate holds a dead lane green), not by a point count.
  V3  A-vs-A: one parent embedded twice (two fresh embedders) is BIT-IDENTICAL — the harness is
      deterministic, so a difference between arms cannot be an artifact of the run.
  V4  KNOWN-VECTOR SPOT CHECK (the strongest): one chunk's late-chunked vector, recomputed with the
      OLD model (Qwen3), reproduces the SOURCE collection's stored dense_1024 — which proves the
      late-chunk path used here is the shipped one, not a re-implementation.

Run:
    unset PYTHONPATH
    export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3 \
           DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5 DENSE_DIM=768 DENSE_DIM_LOW=64 \
           QUERY_INSTRUCTION="search_query: " DOCUMENT_PREFIX="search_document: "
    uv run python -u logs/p1/step10/reembed_v3_verify.py --src knowledge_base_v2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from qdrant_client import QdrantClient  # noqa: E402

from src.core.config import Settings, get_settings  # noqa: E402
from src.pdf_ingestion.chunker import TextChunk  # noqa: E402
from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder  # noqa: E402
from src.pdf_ingestion.models import ParentChunk  # noqa: E402


def scroll_all(client, collection, *, with_vectors):
    out, offset = [], None
    while True:
        b, offset = client.scroll(collection_name=collection, limit=512, offset=offset,
                                  with_payload=True, with_vectors=with_vectors)
        out.extend(b)
        if offset is None:
            return out


def _chunks(points):
    return [p for p in points if p.payload.get("raptor_level") is None]


def _child(p):
    return TextChunk(
        chunk_id=p.payload["chunk_id"], document_id=p.payload["document_id"],
        tenant_id=p.payload.get("tenant_id", "global"), chunk_index=p.payload.get("chunk_index", 0),
        text=p.payload["text"], char_start=p.payload.get("char_start", 0),
        char_end=p.payload.get("char_end", 0), token_count=p.payload.get("token_count", 0),
        page_number=p.payload.get("page_number"), parent_id=p.payload["parent_id"],
        parent_text=p.payload.get("parent_text"), is_content=p.payload.get("is_content", True),
    )


def _parent(p):
    return ParentChunk(parent_id=p.payload["parent_id"], text=p.payload.get("parent_text") or "",
                       page_map={0: p.payload.get("page_number") or 1})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="knowledge_base_v2")
    ap.add_argument("--dst", default=None, help="default: cfg.qdrant_collection")
    args = ap.parse_args()

    cfg = get_settings()
    dst = args.dst or cfg.qdrant_collection
    client = QdrantClient(host=cfg.qdrant_host, port=getattr(cfg, "qdrant_port", 6333) or 6333)

    src_pts = scroll_all(client, args.src, with_vectors=True)
    dst_pts = scroll_all(client, dst, with_vectors=True)
    src_chunks, dst_chunks = _chunks(src_pts), _chunks(dst_pts)
    src_raptor = len(src_pts) - len(src_chunks)

    results: list[tuple[str, bool, str]] = []

    # ── V1: chunk_id set, byte-identical sorted list ─────────────────────────
    src_ids = sorted(p.payload["chunk_id"] for p in src_chunks)
    dst_ids = sorted(p.payload["chunk_id"] for p in dst_chunks)
    same = src_ids == dst_ids
    results.append(("V1 chunk_id set before == after", same,
                    f"{len(src_ids)} src / {len(dst_ids)} dst; "
                    f"missing={len(set(src_ids)-set(dst_ids))} extra={len(set(dst_ids)-set(src_ids))}"))

    # ── V2: every lane on every destination chunk point, at the right width ──
    want = {"dense_full": cfg.dense_dim, "dense_64": cfg.dense_dim_low}
    bad: list[str] = []
    for p in dst_chunks:
        v = p.vector or {}
        for name, size in want.items():
            if name not in v:
                bad.append(f"{p.id}:{name} absent")
            elif len(v[name]) != size:
                bad.append(f"{p.id}:{name}={len(v[name])}d want {size}d")
        if cfg.colbert_enabled and "colbert" not in v:
            bad.append(f"{p.id}:colbert absent")
        if cfg.splade_enabled and "sparse" not in v:
            bad.append(f"{p.id}:sparse absent")
    results.append(("V2 every lane on every chunk point", not bad,
                    f"{len(dst_chunks)} points checked; " + (f"{len(bad)} bad, first: {bad[0]}" if bad else "0 bad")))

    # ── V5 (implied by V1, asserted explicitly): point id preserved ──────────
    src_by_id = {str(p.id): p.payload["chunk_id"] for p in src_chunks}
    id_ok = all(str(p.id) in src_by_id and src_by_id[str(p.id)] == p.payload["chunk_id"] for p in dst_chunks)
    results.append(("V5 point id preserved (id == source id)", id_ok,
                    "every destination point id exists in the source with the same chunk_id"
                    if id_ok else "an id does not match the source"))

    # ── V3: A-vs-A, one parent embedded twice ────────────────────────────────
    # ⚠️ Use the parent with the MOST children: a one-child A-vs-A is a weak sample (it exercises
    # one span, not the span→token mapping across many).
    _by_parent: dict = {}
    for p in src_chunks:
        _by_parent.setdefault((p.payload["document_id"], p.payload["parent_id"]), []).append(p)
    _pk = max(_by_parent, key=lambda k: len(_by_parent[k]))
    grp = _by_parent[_pk]
    sample = grp[0]
    kids = [_child(p) for p in grp]
    par = _parent(sample)
    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder as _CE
    a = LateChunkEmbedder(cfg, embedder=_CE(settings=cfg)).embed_parent(par, kids)
    b = LateChunkEmbedder(cfg, embedder=_CE(settings=cfg)).embed_parent(par, kids)
    a_by = {e.chunk.chunk_id: e for e in a}
    b_by = {e.chunk.chunk_id: e for e in b}
    identical = set(a_by) == set(b_by) and all(
        np.array_equal(a_by[k].dense_1024, b_by[k].dense_1024) and
        np.array_equal(a_by[k].dense_64, b_by[k].dense_64) for k in a_by)
    results.append(("V3 A-vs-A bit-identical (fresh embedders)", identical,
                    f"{len(a_by)} children compared, array_equal" if identical else "vectors differ"))

    # ── V4: known-vector spot check with the OLD model (Qwen3) ───────────────
    old = Settings(
        dense_model="Qwen/Qwen3-Embedding-0.6B", dense_dim=1024, dense_dim_low=64,
        query_instruction="Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: ",
        document_prefix="", use_stub_embedder=False,
    )
    spot = grp[0]
    # ⚠️ Build the OLD embedder EXPLICITLY. `get_cluster_embedder` is a memoised singleton, so
    # `LateChunkEmbedder(old)` would silently reuse the nomic (768d) instance built for V3 and
    # return 768d vectors against a 1024d expectation — the check would fail for the wrong reason.
    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder
    got = LateChunkEmbedder(old, embedder=ClusterDenseEmbedder(settings=old)).embed_parent(
        _parent(spot), [_child(spot)])[0]
    stored = np.asarray(src_by_id_vec(spot), dtype=np.float32)
    cos = float(np.dot(got.dense_1024, stored) / (np.linalg.norm(got.dense_1024) * np.linalg.norm(stored) + 1e-12))
    results.append(("V4 known-vector spot check (Qwen3 reproduces source)", cos >= 0.999,
                    f"cos={cos:.6f} vs the source's stored dense_1024 ({len(stored)}d)"))

    # ── report ───────────────────────────────────────────────────────────────
    print(f"\nsource '{args.src}': {len(src_pts)} points ({len(src_chunks)} chunk / {src_raptor} raptor)")
    print(f"dest   '{dst}': {len(dst_pts)} points ({len(dst_chunks)} chunk / {len(dst_pts)-len(dst_chunks)} raptor)")
    ok = True
    for name, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
        ok = ok and passed
    print(f"\n{'ALL PASS' if ok else 'FAILED'}")
    return 0 if ok else 2


def src_by_id_vec(spot):
    """The source point's stored dense_1024 — its vector dict may key it dense_1024 or dense_full."""
    v = spot.vector or {}
    for name in ("dense_1024", "dense_full", "dense_768"):
        if name in v:
            return v[name]
    raise KeyError(f"no dense lane on source point {spot.id}: {list(v)}")


if __name__ == "__main__":
    sys.exit(main())
