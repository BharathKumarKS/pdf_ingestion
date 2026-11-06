"""Acceptance instrument for §I88's pooled re-embed of `knowledge_base_v3`'s dense lanes.

WHY. §I88 established that nomic's late-chunk path is faithful (cos 1.000000 to an independent
span-pooling), so the 0.155 coverage loss is a METHOD choice — and the fix is to re-embed v3's dense
lanes **pooled** (`reembed_chunks.py --from-collection knowledge_base_v2 --pooled`). That write is
the treatment; this is its gate.

RUN IT TWICE:
    --stage pre    before the write  → expect cos(stored, pooled) materially < 1 and v3's coverage
                                      at §I86's late-chunked row
    --stage post   after the write   → expect cos ≈ 1 and v3's coverage AT §I87's `nomic_pooled` row

WHAT IT MEASURES (all read-only, no writes, no LLM):
  * the point count and the `chunk_id` SET (a sha256 of the sorted ids) — the write must not add,
    drop or renumber a single chunk
  * cos(stored `dense_full`, a FRESH pooled embedding of the same `text`) — the direct evidence that
    the stored lane is the pooled construction. This is the check §I88 said did not exist.
  * the §I87 coverage curve for the STORED index — coverage of a query's REACHABLE labelled pages,
    full-dim exact cosine, NO prefilter, 133 gold queries

GUARDS (each must be able to fail):
  G1  3,796 chunk points, and the `chunk_id` set sha256 matches the value recorded pre-write
  G2  133 queries scored, 0 errors
  G3  the page set is unchanged (the corpus did not move)
  G4  stage-specific:
        pre  — mean cos(stored, pooled) < 0.90 (the late-chunked index is NOT the pooled one)
        post — mean cos(stored, pooled) > 0.999 AND v3 coverage at L=500 == §I87's `nomic_pooled`
               (0.843325 ± 0.002)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import httpx  # noqa: E402
from loguru import logger  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_qdrant  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
NOMIC = "nomic-ai/nomic-embed-text-v1.5"
DOC_PREFIX = "search_document: "
QRY_PREFIX = "search_query: "
LS = (100, 500, 1000, 2000)

# The rows this gate anchors on, both measured in the register.
I86_LATECHUNKED_L500 = 0.688664      # §I86/§I87: v3 stored = late-chunked nomic
I87_POOLED_L500 = 0.843325           # §I87: `nomic_pooled`, the treatment's target
TOL = 0.002


def flt(cfg) -> Filter:
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not)


def scroll_all(client, name, cfg):
    """Every point in the window, with the payload keys and the stored dense lane."""
    pts: list = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=name, scroll_filter=flt(cfg), limit=1000, offset=offset,
            with_payload=["chunk_id", "text", "page_number", "raptor_level"],
            with_vectors=["dense_full"],
        )
        pts.extend(batch)
        if offset is None:
            break
    return pts


def pooled(texts: list[str], batch: int = 64) -> np.ndarray:
    """The endpoint's POOLED output for prefixed texts — §I63/§I87's own construction."""
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = [DOC_PREFIX + t for t in texts[i:i + batch]]
        for attempt in range(3):
            try:
                r = httpx.post(URL, json={"input": chunk, "model": NOMIC}, timeout=180)
                r.raise_for_status()
                data = r.json()
                data = data.get("data", data)
                out.extend(d["embedding"] if isinstance(d, dict) else d for d in data)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("pooled batch {} attempt {} failed: {}", i, attempt, exc)
                if attempt == 2:
                    raise
    v = np.asarray(out, dtype=np.float64)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("pre", "post"), required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--chunk-id-sha-pre", default=None,
                    help="the `chunk_id` set sha256 recorded by the --stage pre run")
    ap.add_argument("--cos-sample", type=int, default=200,
                    help="how many chunks to re-embed for the stored-vs-pooled cosine")
    args = ap.parse_args()
    out_path = Path(args.out or f"logs/p1/step10/pooled_reembed_{args.stage}.json")

    cfg = get_settings()
    if cfg.qdrant_collection != "knowledge_base_v3":
        print("ABORT: run with QDRANT_COLLECTION=knowledge_base_v3.", file=sys.stderr)
        return 3
    if cfg.dense_model != NOMIC:
        print(f"ABORT: DENSE_MODEL is {cfg.dense_model!r}, expected {NOMIC!r}.", file=sys.stderr)
        return 3

    client = get_qdrant(cfg)
    info = client.get_collection(cfg.qdrant_collection)

    t0 = time.time()
    pts = scroll_all(client, cfg.qdrant_collection, cfg)
    chunks = [p for p in pts if (p.payload or {}).get("raptor_level") is None]
    logger.info("v3: {} points total, {} chunk points in-window ({}s)",
                info.points_count, len(chunks), round(time.time() - t0, 1))

    # ── the identity the write must not change ────────────────────────────────
    ids = sorted((p.payload or {}).get("chunk_id") or "" for p in chunks)
    chunk_id_sha = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    point_ids = sorted(str(p.id) for p in chunks)
    point_id_sha = hashlib.sha256("\n".join(point_ids).encode()).hexdigest()

    stored = np.asarray([p.vector["dense_full"] for p in chunks], dtype=np.float64)
    stored /= (np.linalg.norm(stored, axis=1, keepdims=True) + 1e-12)
    pages = np.asarray([int((p.payload or {}).get("page_number") or -1) for p in chunks],
                       dtype=np.int64)
    texts = [(p.payload or {}).get("text") or "" for p in chunks]

    # ── cos(stored, a FRESH pooled embedding of the same text) ────────────────
    n_sample = min(args.cos_sample, len(chunks))
    idx = np.linspace(0, len(chunks) - 1, n_sample).astype(int)
    t1 = time.time()
    fresh = pooled([texts[i] for i in idx])
    cos = np.sum(fresh * stored[idx], axis=1)
    logger.info("cos(stored, fresh pooled) over {} sampled chunks ({}s)", n_sample,
                round(time.time() - t1, 1))
    cos_summary = {
        "n": int(n_sample), "mean": round(float(cos.mean()), 6),
        "min": round(float(cos.min()), 6), "median": round(float(np.median(cos)), 6),
        "p10": round(float(np.percentile(cos, 10)), 6),
        "n_below_0.99": int((cos < 0.99).sum()), "n_below_0.90": int((cos < 0.90).sum()),
    }

    # ── §I87's coverage curve on the STORED index ─────────────────────────────
    raw = json.loads(Path(QUERIES).read_text())
    queries = [q for q in raw if isinstance(q, dict)
               and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    r = httpx.post(URL, json={"input": [QRY_PREFIX + q["query"] for q in queries], "model": NOMIC},
                   timeout=180).json()
    r = r.get("data", r)
    Q = np.asarray([d["embedding"] if isinstance(d, dict) else d for d in r], dtype=np.float64)
    Q /= (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)

    coll_pages = {int(p) for p in pages.tolist()}
    cov = {L: [] for L in LS}
    per_query = []
    for i, q in enumerate(queries):
        reach = {int(p) for p in q["relevant_pages"]} & coll_pages
        order = np.argsort(-(stored @ Q[i]), kind="stable")
        rec = {"id": q["id"], "n_reachable": len(reach)}
        for L in LS:
            got = {int(pages[j]) for j in order[:L]}
            c = (len(got & reach) / len(reach)) if reach else None
            if c is not None:
                cov[L].append(c)
            rec[f"L{L}"] = c
        per_query.append(rec)
    agg = {str(L): round(statistics.mean(cov[L]), 6) if cov[L] else None for L in LS}

    # ── guards ────────────────────────────────────────────────────────────────
    # ⚠️ Two DIFFERENT populations, named separately (§I71/§I72's class): the collection holds 3,796
    # chunk points, but the content window admits only 3,489 of them. A guard that conflates the two
    # reads as a failure on a correct index — the first draft of this file did exactly that.
    guards = {
        "G1a_collection_points_total_3796": info.points_count == 3796,
        "G1b_chunk_points_in_window_3489": len(chunks) == 3489,
        "G2_133_queries": len(per_query) == 133,
        "G3_page_set_size_888": len(coll_pages) == 888,
    }
    if args.stage == "pre":
        guards["G4_pre_cos_below_0.90"] = cos_summary["mean"] < 0.90
        guards["G4_pre_coverage_at_I86_latechunked"] = (
            abs(agg["500"] - I86_LATECHUNKED_L500) <= TOL)
    else:
        guards["G4_post_cos_above_0.999"] = cos_summary["mean"] > 0.999
        guards["G4_post_coverage_at_I87_pooled"] = abs(agg["500"] - I87_POOLED_L500) <= TOL
        if args.chunk_id_sha_pre:
            guards["G5_chunk_id_set_unchanged"] = chunk_id_sha == args.chunk_id_sha_pre

    art = {
        "meta": {
            "stage": args.stage, "collection": cfg.qdrant_collection,
            "model": cfg.dense_model, "document_prefix": cfg.document_prefix,
            "points_total": info.points_count, "chunk_points_in_window": len(chunks),
            "n_pages": len(coll_pages), "n_queries": len(per_query),
            "cos_sample": n_sample, "no_writes": True, "no_llm": True,
            "anchors": {"I86_latechunked_L500": I86_LATECHUNKED_L500,
                        "I87_pooled_L500": I87_POOLED_L500, "tol": TOL},
        },
        "identity": {"chunk_id_set_sha256": chunk_id_sha, "point_id_set_sha256": point_id_sha},
        "cos_stored_vs_fresh_pooled": cos_summary,
        "coverage_stored": agg,
        "guards": guards,
        "per_query": per_query,
    }
    out_path.write_text(json.dumps(art, indent=2))
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(json.dumps({k: art[k] for k in ("meta", "identity", "cos_stored_vs_fresh_pooled",
                                          "coverage_stored", "guards")}, indent=2))
    print(f"\nartifact: {out_path}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
