#!/usr/bin/env python
"""§I60 — the MRL dimension × prefetch-limit sweep, read-only. What would 128d buy, and does a
bigger limit help?

Why this exists
---------------
§I59 measured the base lane at **64d, limit 1000** and found the truncation penalty 8.7× worse for
Qwen3 than for Nomic (0.1115 vs 0.0128 of ceiling-normalised R@1000). Two obvious responses, both
raised by the owner:

  * **widen the MRL prefix** (64d → 128d) so the first stage keeps more of the vector;
  * **raise the prefetch limit** (1000 → higher).

Both are answerable **without touching the cluster**. `dense_64` was verified to be an *exact* MRL
slice of the full-dimension vector (cosine 1.0000 on 200 sampled points, both indexes, §I59), so
`dense_<d>` is `full[:d]` re-normalised — which means any dimension can be reconstructed **client
side** from the stored full vector. A brute-force cosine over the whole collection returns *exactly*
the ranking a `dense_<d>` Qdrant lane would, for any d and any k. So this sweeps the whole design
space read-only: **no new named vector, no re-embed, no write.**

⚠️ **This is EXACT brute-force search, and that is the point — but it means the numbers are NOT
Qdrant's numbers.** The reconstruction of the vector space is exact (`dense_64` is a verified MRL
slice, so `full[:d]` re-normalised *is* `dense_<d>`), but Qdrant answers through an **HNSW index**,
which is *approximate*. So this sweep measures **vector-space quality by dimension with the ANN
confound removed** — and the gap between it and §I59's Qdrant numbers is the **HNSW approximation
loss**, reported as `ann_gap_vs_I59` rather than treated as a validation failure. Both are findings;
they answer different questions.

⚠️ Two things to read before the curve:
  1. **`ann_gap_vs_I59`** — how much recall the HNSW index costs at d=64, k=1000.
  2. **The k column where recall saturates.** "Raise the limit" only buys something if recall is still
     rising at k=1000; if it is flat from 500, the limit is not the lever.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    uv run python logs/p1/step10/mrl_dimension_sweep.py
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.embedder import get_embedder  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/mrl_dimension_sweep.json"

OLD_DOC, NEW_DOC = "6d55c52b", "7ba61432"
DIMS = (64, 128, 256, 512, 1024)
KS = (20, 100, 500, 1000, 2000, 5000)
INDEXES = [
    ("old", "knowledge_base", OLD_DOC, "nomic", 768),
    ("new", "knowledge_base_v2", NEW_DOC, "qwen3", 1024),
]


def scroll_all(client, collection: str, cfg) -> tuple[np.ndarray, list[dict]]:
    """Every in-window chunk's full-dimension vector + the payload the production filter needs.

    The filter is applied **client side** here (page window, `is_content`, non-RAPTOR, tenant), which
    is equivalent to `store.py:336-369` and keeps this a pure read.
    """
    vectors: list[list[float]] = []
    payloads: list[dict] = []
    offset = None
    while True:
        pts, offset = client.scroll(
            collection_name=collection, limit=1000, offset=offset,
            with_vectors=True, with_payload=True,
        )
        for p in pts:
            pay = p.payload or {}
            if pay.get("source_type") == "raptor_summary":
                continue
            pg = pay.get("page_number")
            if pg is None or pay.get("is_content") is False:
                continue
            if cfg.min_content_page > 0 and pg < cfg.min_content_page:
                continue
            if cfg.max_content_page > 0 and pg > cfg.max_content_page:
                continue
            if pay.get("tenant_id") not in (cfg.global_tenant_id, "global", None):
                continue
            vec = p.vector
            if isinstance(vec, dict):
                # named vectors: take the full-dimension one
                cand = [v for k, v in vec.items() if k.startswith("dense_") and len(v) > 64]
                if not cand:
                    continue
                vec = max(cand, key=len)
            vectors.append(vec)
            payloads.append({"page_number": int(pg)})
        if offset is None:
            break
    m = np.asarray(vectors, dtype=np.float32)
    m /= (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)
    return m, payloads


def rank_pages(sims: np.ndarray, pages: np.ndarray, k: int) -> list[int]:
    """Distinct pages in rank order — a page scores once, at its best chunk's rank."""
    idx = np.argsort(-sims)[:k]
    seen, out = set(), []
    for i in idx:
        pg = int(pages[i])
        if pg in seen:
            continue
        seen.add(pg)
        out.append(pg)
    return out


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None, "resolved": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 6), "ci95": [round(m - half, 6), round(m + half, 6)],
            "resolved": bool((m - half) > 0 or (m + half) > 0)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0)
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
    if args.limit:
        queries = queries[: args.limit]

    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    nomic = get_embedder(cfg)
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)

    matrices: dict[str, np.ndarray] = {}
    pages_arr: dict[str, np.ndarray] = {}
    for tag, coll, _doc, _which, _dim in INDEXES:
        m, pay = scroll_all(client, coll, cfg)
        matrices[tag] = m
        pages_arr[tag] = np.asarray([p["page_number"] for p in pay], dtype=np.int64)
        print(f"{tag} ({coll}): {m.shape[0]} in-window chunks x {m.shape[1]}d")

    # ceilings (§I58 rule, client side)
    ceilings = {}
    for tag, _coll, doc, _w, _d in INDEXES:
        from sqlmodel import Session, select

        from src.core.database import Chunk, get_engine
        with Session(get_engine(cfg)) as session:
            rows = session.exec(
                select(Chunk).where(Chunk.document_id.like(f"{doc}%"))  # type: ignore[attr-defined]
            ).all()
        ceilings[tag] = {int(c.page_number) for c in rows
                         if c.page_number is not None and c.is_content is not False
                         and cfg.min_content_page <= c.page_number <= cfg.max_content_page}

    results: dict[str, list[dict]] = {tag: [] for tag, *_ in INDEXES}
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        for tag, _coll, _doc, which, full_dim in INDEXES:
            embedder = nomic if which == "nomic" else qwen
            try:
                vec = np.asarray(embedder.embed_query(q["query"]), dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                results[tag].append({"id": qid, "error": f"embed: {exc}"})
                continue
            m = matrices[tag]
            pages = pages_arr[tag]
            ceil = relevant & ceilings[tag]
            row = {"id": qid, "query_type": q.get("query_type"),
                   "n_relevant": len(relevant), "n_reachable": len(ceil), "dims": {}}
            for d in DIMS:
                if d > vec.shape[0] or d > m.shape[1]:
                    continue
                qv = vec[:d].copy()
                qv /= np.linalg.norm(qv) + 1e-12
                sims = m[:, :d] @ qv
                rk = rank_pages(sims, pages, max(KS))
                row["dims"][str(d)] = {
                    **{f"r{k}": (round(len(set(rk[:k]) & relevant) / len(relevant), 6)
                                 if relevant else None) for k in KS},
                    **{f"c{k}": (round(len(set(rk[:k]) & ceil) / len(ceil), 6) if ceil else None)
                       for k in KS},
                    "n_pages_in_pool": len(rk),
                }
            results[tag].append(row)
        if i % 20 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    def agg(tag: str, dim: int, key: str) -> dict:
        rows = [r for r in results[tag] if "dims" in r and str(dim) in r["dims"]]
        out = {}
        for k in KS:
            vals = [r["dims"][str(dim)][f"{key}{k}"] for r in rows
                    if r["dims"][str(dim)][f"{key}{k}"] is not None]
            out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
        return {"queries": len(rows), **out}

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/mrl_dimension_sweep.py",
            "what": ("§I60 — MRL dimension x prefetch-limit sweep, reconstructed CLIENT SIDE from "
                     "the stored full-dimension vectors (read-only, no new named vector, no write)"),
            "why_this_is_exact": ("`dense_64` is an exact MRL slice of the full vector (cosine "
                                  "1.0000, §I59), so `full[:d]` re-normalised IS `dense_<d>`; a "
                                  "brute-force cosine over the whole collection returns exactly the "
                                  "ranking a `dense_<d>` Qdrant lane would."),
            "validation_1": ("d=64, k=1000 must reproduce §I59's Qdrant numbers — see "
                             "`validation_vs_I59`"),
            "dims": list(DIMS), "ks": list(KS),
            "no_llm_calls": True, "no_writes": True,
            "pool_sizes": {tag: int(matrices[tag].shape[0]) for tag in matrices},
            "full_dims": {tag: int(matrices[tag].shape[1]) for tag in matrices},
        },
        "new_index": {str(d): {"raw": agg("new", d, "r"), "ceiling_norm": agg("new", d, "c")}
                      for d in DIMS},
        "old_index": {str(d): {"raw": agg("old", d, "r"), "ceiling_norm": agg("old", d, "c")}
                      for d in DIMS},
        "queries": results,
    }

    # the gap between EXACT search (this sweep) and Qdrant's HNSW at d=64 — the ANN approximation loss
    I59 = {"old": {"1000": 0.9224, "500": 0.9224, "100": 0.6397, "20": 0.4220},
           "new": {"1000": 0.8151, "500": 0.7880, "100": 0.3587, "20": 0.1028}}
    val = {}
    for tag in ("old", "new"):
        val[tag] = {}
        for k in (1000, 500, 100, 20):
            mine = agg(tag, 64, "c")[f"R@{k}"]
            val[tag][f"R@{k}"] = {"exact_this_sweep": mine, "qdrant_hnsw_I59": I59[tag][str(k)],
                                  "ann_gap": (round(mine - I59[tag][str(k)], 6)
                                              if mine is not None else None)}
    out["ann_gap_vs_I59"] = val

    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\n=== EXACT search (this sweep) vs Qdrant's HNSW (§I59), d=64, ceiling-normalised ===")
    for tag in ("old", "new"):
        gaps = [v["ann_gap"] for v in val[tag].values() if v["ann_gap"] is not None]
        print(f"  {tag}: mean ANN gap = {statistics.mean(gaps):+.4f} "
              f"(positive = exact search finds MORE than HNSW does)")
        for k, v in val[tag].items():
            print(f"     {k:>7}  exact {v['exact_this_sweep']:.4f}  hnsw {v['qdrant_hnsw_I59']:.4f}  "
                  f"gap {v['ann_gap']:+.4f}")

    for label, key in (("NEW", "new_index"), ("OLD", "old_index")):
        print(f"\n=== {label} index: ceiling-normalised recall by MRL dimension (EXACT search) ===")
        print(f"  {'d':>5} " + "".join(f"{('R@'+str(k)):>10}" for k in KS))
        for d in DIMS:
            a = out[key][str(d)]["ceiling_norm"]
            if a.get("queries", 0) == 0 or a.get("R@20") is None:
                print(f"  {d:>5}  (not available in this index)")
                continue
            print(f"  {d:>5} " + "".join(
                f"{(a[f'R@{k}'] if a[f'R@{k}'] is not None else float('nan')):>10.4f}" for k in KS))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
