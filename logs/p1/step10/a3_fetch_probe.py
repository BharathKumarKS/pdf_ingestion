#!/usr/bin/env python
"""A3 probe — the `get_chunks_with_embeddings` over-fetch, measured before vs after (§I28).

What is being measured
----------------------
`DocumentStore.get_chunks_with_embeddings` (src/pdf_ingestion/store.py) issues
    self._qdrant.retrieve(collection_name=..., ids=[...], with_vectors=True)
`with_vectors=True` returns **every named vector on every point** — `dense_1024`,
`dense_64` AND the `colbert` token matrices — while the caller reads only the dense lane
and discards the rest. §I28 measured the cost on the 3,796-point collection: a 3 min 06 s
stall before the first card line, RSS 36 MB -> 1,992 MB.

The fix asks for the one lane it uses (`with_vectors=[dense_1024]`), falling back to
`True` only on a legacy collection with no named dense slot.

This probe does NOT re-run the pipeline (the plan forbids it: hours, and the card run is
in flight). It exercises the *call* on the same ids, in the same process, and measures:

  1. the kwargs actually issued at the Qdrant client boundary (a spy), printed verbatim;
  2. wall time and RSS, before vs after;
  3. the CONTRACT — the dense matrix is unchanged and still row-aligned with `chunks`
     order (the caller zips them; this is the one thing the change can break).

Modes (three invocations, because `ru_maxrss` peak is monotonic per process):
    --arm before   fresh process -> exact peak RSS for the old call
    --arm after    fresh process -> exact peak RSS for the new call (+ spy kwargs)
    --arm both     one process   -> wall time head-to-head + the contract check

Results merge into the JSON artifact, so the three runs build one file.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/a3_fetch_probe.py --arm before
    uv run python logs/p1/step10/a3_fetch_probe.py --arm after
    uv run python logs/p1/step10/a3_fetch_probe.py --arm both
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402
import psutil  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import Chunk  # noqa: E402
from src.pdf_ingestion.store import DocumentStore, _dense_name_from  # noqa: E402

DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
OUT = Path("logs/p1/step10/a3_fetch_probe.json")
PROC = psutil.Process()


def rss_mb() -> float:
    return PROC.memory_info().rss / 1024 / 1024


def peak_mb() -> float:
    """ru_maxrss is BYTES on macOS, KILOBYTES on Linux."""
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v / 1024 / 1024 if sys.platform == "darwin" else v / 1024


def chunk_ids(store: DocumentStore) -> list[str]:
    """The same ordered id list the real call site builds (`order_by(Chunk.chunk_index)`)."""
    with Session(store._engine) as s:  # noqa: SLF001
        return [
            c.qdrant_point_id
            for c in s.exec(
                select(Chunk)
                .where(Chunk.document_id == DOC)
                .where(Chunk.is_active == True)  # noqa: E712
                .order_by(Chunk.chunk_index)
            ).all()
        ]


def extract_dense(vec, dense_name: str) -> np.ndarray:
    """The caller's own extraction (store.py `_extract_dense`), duplicated deliberately so
    the probe measures the CONTRACT rather than calling the code under test to check itself."""
    if isinstance(vec, dict):
        vec = vec.get(dense_name) or vec.get("dense", [])
    return np.array(vec, dtype=np.float32)


def merge(section: str, payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data[section] = payload
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def arm_before(store: DocumentStore, ids: list[str]):
    dense_name = _dense_name_from(store._collection_vectors()) or "dense_1024"
    rss0, peak0 = rss_mb(), peak_mb()
    t0 = time.perf_counter()
    results = store._qdrant.retrieve(  # noqa: SLF001
        collection_name=store._cfg.qdrant_collection, ids=ids, with_vectors=True
    )
    wall = time.perf_counter() - t0
    peak_during = peak_mb()
    by_id = {str(r.id): extract_dense(r.vector, dense_name) for r in results}
    matrix = np.array([by_id[i] for i in ids], dtype=np.float32)
    names = sorted({k for r in results if isinstance(r.vector, dict) for k in r.vector})
    return {
        "kwargs": {"collection_name": store._cfg.qdrant_collection,
                   "n_ids": len(ids), "with_vectors": True},
        "wall_seconds": round(wall, 2),
        "rss_start_mb": round(rss0, 1),
        "rss_peak_mb": round(peak_during, 1),
        "rss_growth_mb": round(peak_during - rss0, 1),
        "ru_maxrss_peak_mb": round(peak0 if peak0 > peak_during else peak_during, 1),
        "points_returned": len(results),
        "vector_names_returned": names,
        "dense_dim": int(matrix.shape[1]) if matrix.size else None,
        "dense_matrix_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
    }, matrix


def arm_after(store: DocumentStore, doc: str, capture: dict):
    """Run the REAL method, spying on the retrieve call at the client boundary."""
    real = store._qdrant.retrieve  # noqa: SLF001

    def spy(*a, **kw):
        capture["kwargs"] = {k: v for k, v in kw.items()}
        capture["positional"] = list(a)
        t = time.perf_counter()
        out = real(*a, **kw)
        capture["wall_seconds"] = round(time.perf_counter() - t, 2)
        capture["points_returned"] = len(out)
        capture["vector_names_returned"] = sorted(
            {k for r in out if isinstance(r.vector, dict) for k in r.vector}
        )
        return out

    rss0, peak0 = rss_mb(), peak_mb()
    store._qdrant.retrieve = spy  # noqa: SLF001
    t0 = time.perf_counter()
    try:
        chunks, embeddings = store.get_chunks_with_embeddings(doc)
    finally:
        store._qdrant.retrieve = real  # noqa: SLF001
    wall = time.perf_counter() - t0
    peak_during = peak_mb()
    return {
        "method_wall_seconds": round(wall, 2),
        "rss_start_mb": round(rss0, 1),
        "rss_peak_mb": round(peak_during, 1),
        "rss_growth_mb": round(peak_during - rss0, 1),
        "ru_maxrss_peak_mb": round(max(peak0, peak_during), 1),
        "n_chunks": len(chunks),
        "embeddings_shape": list(embeddings.shape),
        "spy": capture,
        "dense_matrix_sha256": hashlib.sha256(
            np.ascontiguousarray(embeddings).tobytes()
        ).hexdigest(),
    }, chunks, embeddings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["before", "after", "both"], required=True)
    args = ap.parse_args()

    cfg = get_settings()
    store = DocumentStore(cfg)
    ids = chunk_ids(store)
    meta = {
        "document": DOC,
        "collection": cfg.qdrant_collection,
        "n_ids": len(ids),
        "id_list_sha256": hashlib.sha256("".join(ids).encode()).hexdigest(),
        "id_list_first5": ids[:5],
        "dense_name": _dense_name_from(store._collection_vectors()),
        "collection_vectors": str(store._collection_vectors()),
    }
    print(f"collection={cfg.qdrant_collection} ids={len(ids)} dense_name={meta['dense_name']}")

    if args.arm == "before":
        res, _ = arm_before(store, ids)
        print(json.dumps(res, indent=2))
        merge("before_fresh_process", {**meta, **res})
        return 0

    if args.arm == "after":
        cap: dict = {}
        res, _, _ = arm_after(store, DOC, cap)
        print(json.dumps(res, indent=2))
        merge("after_fresh_process", {**meta, **res})
        return 0

    # ---- both: head-to-head in ONE process + the contract check -----------------
    before_res, before_matrix = arm_before(store, ids)
    cap = {}
    after_res, chunks, embeddings = arm_after(store, DOC, cap)

    # CONTRACT 1: same rows, same order, same values — the OLD call's dense lane vs the
    # NEW call's dense lane, both extracted with the caller's own rule.
    contract = {
        "same_shape": list(before_matrix.shape) == list(embeddings.shape),
        "arrays_equal": bool(np.array_equal(before_matrix, embeddings)),
        "max_abs_diff": float(np.max(np.abs(before_matrix - embeddings))) if before_matrix.size else None,
        "chunk_order_matches_ids": [c.qdrant_point_id for c in chunks] == ids,
        "n_chunks": len(chunks),
        "embeddings_shape": list(embeddings.shape),
        "rows_all_zero": bool(np.all(embeddings == 0)),
    }

    # CONTRACT 2: the call really changed — a bool True over all names is the defect.
    spy_kw = cap.get("kwargs", {})
    call_changed = {
        "with_vectors_issued": repr(spy_kw.get("with_vectors")),
        "is_bool_true": spy_kw.get("with_vectors") is True,
        "vector_names_returned": cap.get("vector_names_returned"),
        "assert_not_all_names": spy_kw.get("with_vectors") is not True,
    }

    speedup = (before_res["wall_seconds"] / after_res["method_wall_seconds"]
               if after_res["method_wall_seconds"] else None)
    out = {
        **meta,
        "before": before_res,
        "after": after_res,
        "contract": contract,
        "call_changed": call_changed,
        "wall_speedup_x": round(speedup, 2) if speedup else None,
        "same_process_note": (
            "READ THIS BEFORE COMPARING RSS. The `*_fresh_process` sections are the RSS "
            "evidence: each arm ran in its own process, so ru_maxrss is that arm's true peak. "
            "In THIS in-process head-to-head the before arm runs FIRST and CPython does not "
            "return its memory to the OS, so `after.rss_start_mb` is already high and "
            "`after.rss_peak_mb` can be at or near the before arm's peak — do not read this "
            "section's RSS as the after arm's footprint. An independent reviewer made exactly "
            "that misattribution on 2026-10-20 and returned REFUTED against numbers that are "
            "in a different section. WALL TIME in this section IS comparable (same process, "
            "same ids, back to back)."
        ),
    }
    print(json.dumps({k: out[k] for k in
                      ("before", "after", "contract", "call_changed", "wall_speedup_x")},
                     indent=2))
    merge("both_one_process", out)
    ok = (contract["arrays_equal"] and contract["chunk_order_matches_ids"]
          and contract["same_shape"] and call_changed["assert_not_all_names"])
    print(f"\nCONTRACT OK: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
