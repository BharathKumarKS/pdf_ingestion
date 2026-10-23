#!/usr/bin/env python
"""§I61 — does RAISING THE PREFETCH LIMIT recover the pool? A direct Qdrant limit sweep.

Why this exists
---------------
§I60's exact brute-force sweep found the pool **saturated at 1000 chunks for every MRL dimension**
(ceiling-normalised R@1000 = 1.0000 at d = 64 … 1024, both indexes). But §I59's Qdrant query at the
same limit reached only **0.8151** (new) / **0.9224** (old). The gap is the **ANN**: Qdrant answers
through a *filtered* HNSW index, and filtered ANN search walks a graph whose nodes the filter
excludes, which costs recall.

If that is the mechanism, the limit is the lever — not the dimension. This measures it directly:
query `dense_64` and the full-dimension lane at a range of limits and watch the pool recall.

⚠️ The `limit` here is in CHUNKS and the reported recall is over the deduped PAGE pool, matching
§I60's convention (NOT §I59's, whose k indexes pages). `limit` = the collection's in-window chunk
count is effectively exact search and is the control.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    uv run python logs/p1/step10/prefetch_limit_sweep.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

# The cluster serves Nomic too, and with the task prefix applied BY THE CALLER it reproduces the
# local `NomicEmbedder` exactly — verified `cosine = 1.000000` on real chunk text, versus `0.949`
# unprefixed (§I62). Using it removes the ~2 min local model load and the ~3 s/query CPU cost.
NOMIC_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
NOMIC_MODEL = "nomic-ai/nomic-embed-text-v1.5"
QUERY_PREFIX = "search_query: "


def cluster_nomic_queries(texts: list[str]) -> np.ndarray:
    """Nomic query vectors from the cluster, with the `search_query: ` prefix the model requires."""
    import urllib.request

    body = json.dumps({"model": NOMIC_MODEL,
                       "input": [QUERY_PREFIX + t for t in texts]}).encode()
    req = urllib.request.Request(NOMIC_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    items = sorted(d["data"], key=lambda x: x.get("index", 0))
    m = np.asarray([it["embedding"] for it in items], dtype=np.float32)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/prefetch_limit_sweep.json"
INDEXES = [
    ("old", "knowledge_base", "6d55c52b", "nomic", "dense_768", 4519),
    ("new", "knowledge_base_v2", "7ba61432", "qwen3", "dense_1024", 3489),
]
LIMITS = (1000, 1500, 2000, 3489)
KS = (20, 100)


def content_filter(cfg) -> Filter:
    """The production filter, copied verbatim from `store.py:336-369`."""
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not, should=[
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cfg.global_tenant_id))]),
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value="global"))]),
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--sample", type=int, default=40,
                    help="evaluate every Nth query (0 = all 133); the full run is ~24 Qdrant "
                         "round-trips per query over a tunnel")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.sample:
        # one query in N is enough to answer "does a bigger limit recover the pool" — and the
        # full run is ~24 Qdrant round-trips per query over a tunnel.
        queries = queries[:: max(1, len(queries) // args.sample)][: args.sample]

    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)
    nomic_q = cluster_nomic_queries([q["query"] for q in queries])
    print(f"queries: {len(queries)}  (cluster Nomic query vectors: {nomic_q.shape})")
    filt = content_filter(cfg)

    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine
    ceilings = {}
    for tag, _c, doc, _w, _f, _n in INDEXES:
        with Session(get_engine(cfg)) as session:
            rows = session.exec(
                select(Chunk).where(Chunk.document_id.like(f"{doc}%"))  # type: ignore[attr-defined]
            ).all()
        ceilings[tag] = {int(c.page_number) for c in rows
                         if c.page_number is not None and c.is_content is not False
                         and cfg.min_content_page <= c.page_number <= cfg.max_content_page}

    def pool(using: str, vector: list[float], limit: int, coll: str) -> list[int]:
        pts = client.query_points(collection_name=coll, query=vector, using=using,
                                  query_filter=filt, limit=limit, with_payload=True).points
        seen, out = set(), []
        for p in pts:
            pg = (p.payload or {}).get("page_number")
            if pg is None or pg in seen:
                continue
            seen.add(int(pg))
            out.append(int(pg))
        return out

    rows: list[dict] = []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        relevant = {int(p) for p in q["relevant_pages"]}
        for tag, coll, _doc, which, full_name, nwin in INDEXES:
            try:
                if which == "nomic":
                    vec = nomic_q[i - 1]                      # cluster Nomic, prefixed (§I62)
                else:
                    vec = np.asarray(qwen.embed_query(q["query"]), dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                rows.append({"id": q["id"], "index": tag, "error": f"embed: {exc}"})
                continue
            v64 = vec[:64].copy()
            v64 /= np.linalg.norm(v64) + 1e-12
            ceil = relevant & ceilings[tag]
            rec: dict = {"id": q["id"], "index": tag, "n_reachable": len(ceil), "limits": {}}
            for lane, using, vector in (("mrl64", "dense_64", v64.tolist()),
                                        ("fulldim", full_name, vec.tolist())):
                rec["limits"].setdefault(lane, {})
                for lim in LIMITS:
                    try:
                        pages = pool(using, vector, lim, coll)
                    except Exception as exc:  # noqa: BLE001
                        rec["limits"][lane][str(lim)] = {"error": str(exc)[:80]}
                        continue
                    rec["limits"][lane][str(lim)] = {
                        "n_pages": len(pages),
                        "pool_ceiling_norm": (round(len(set(pages) & ceil) / len(ceil), 6)
                                              if ceil else None),
                        **{f"r{k}": (round(len(set(pages[:k]) & relevant) / len(relevant), 6)
                                     if relevant else None) for k in KS},
                    }
            rows.append(rec)
        if i % 20 == 0:
            print(f"  [{i}/{len(queries)}] {q['id']} … {time.time() - t0:.0f}s", flush=True)

    out = {"meta": {"generated_by": "logs/p1/step10/prefetch_limit_sweep.py",
                    "what": ("§I61 — Qdrant prefetch-limit sweep: does a bigger limit recover the "
                             "pool the ANN is losing?"),
                    "limits": list(LIMITS), "indexes": [t for t, *_ in INDEXES],
                    "unit": "limit is in CHUNKS; recall is over the deduped PAGE pool (§I60 convention)",
                    "no_llm_calls": True, "no_writes": True},
           "summary": {}, "queries": rows}

    for tag, _c, _d, _w, _f, nwin in INDEXES:
        out["summary"][tag] = {}
        for lane in ("mrl64", "fulldim"):
            blk = {}
            for lim in LIMITS:
                vals = [r["limits"][lane][str(lim)]["pool_ceiling_norm"] for r in rows
                        if r.get("index") == tag and "limits" in r
                        and isinstance(r["limits"][lane].get(str(lim)), dict)
                        and r["limits"][lane][str(lim)].get("pool_ceiling_norm") is not None]
                npg = [r["limits"][lane][str(lim)]["n_pages"] for r in rows
                       if r.get("index") == tag and "limits" in r
                       and isinstance(r["limits"][lane].get(str(lim)), dict)
                       and r["limits"][lane][str(lim)].get("n_pages") is not None]
                blk[str(lim)] = {"pool_recall_ceiling_norm": round(statistics.mean(vals), 6) if vals else None,
                                 "median_pages_in_pool": statistics.median(npg) if npg else None,
                                 "queries": len(vals)}
            out["summary"][tag][lane] = blk

    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== pool recall (ceiling-normalised) vs prefetch LIMIT ===")
    print(f"  {'index':>4} {'lane':>8} " + "".join(f"{('lim'+str(l)):>11}" for l in LIMITS))
    for tag, _c, _d, _w, _f, _n in INDEXES:
        for lane in ("mrl64", "fulldim"):
            b = out["summary"][tag][lane]
            print(f"  {tag:>4} {lane:>8} " + "".join(
                f"{(b[str(l)]['pool_recall_ceiling_norm'] if b[str(l)]['pool_recall_ceiling_norm'] is not None else float('nan')):>11.4f}"
                for l in LIMITS))
    print("\n  median pages in pool:")
    for tag, _c, _d, _w, _f, _n in INDEXES:
        for lane in ("mrl64", "fulldim"):
            b = out["summary"][tag][lane]
            print(f"  {tag:>4} {lane:>8} " + "".join(
                f"{(b[str(l)]['median_pages_in_pool'] if b[str(l)]['median_pages_in_pool'] is not None else float('nan')):>11.0f}"
                for l in LIMITS))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
