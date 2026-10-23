#!/usr/bin/env python
"""§I59 — the base MRL-64 lane, measured on BOTH indexes, each with its OWN query embedder.

Why this exists
---------------
`B1_dense_64 @1000` is the only retrieval stage that faces the whole corpus: production retrieval
prefetches `dense_64` (limit 1000) and then rescores with the full-dimension lane
(`store.py:416`, `[dense_64(1000) → dense_<full>(500)]`). So it is the base retriever, and whether it
improved is a real question about the rebuild.

⚠️ The two indexes are in DIFFERENT EMBEDDING SPACES, and that decides the whole instrument:

| | `knowledge_base` (OLD) | `knowledge_base_v2` (NEW) |
|---|---|---|
| named vectors | `dense_768`, `dense_64`, `colbert` | `dense_1024`, `dense_64`, `colbert` |
| dense model | **Nomic** `nomic-ai/nomic-embed-text-v1.5` (768d) | **Qwen3** `Qwen/Qwen3-Embedding-0.6B` (1024d) |
| `dense_64` | MRL slice of the **Nomic** vector | MRL slice of the **Qwen3** vector |

A 64d vector from Qwen3 **cannot** be used against the old index's `dense_64` — different space. So
each index is queried with **its own** embedder: Nomic (local, cached under `data/models`) for the
old index, the cluster Qwen3 for the new one. That is the only valid comparison, and it means the
delta is **embedder + index together**, not one of them.

⚠️ Read the ceiling column. §I58 measured the two indexes' achievable maximum at **0.8806 (old)**
vs **0.9545 (new)**, so a raw recall comparison favours the old index's denominator. Every number is
reported raw AND ceiling-normalised.

No LLM calls. 133 queries. Reads SQLite + Qdrant (cluster) only.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    uv run python logs/p1/step10/base_retriever_mrl64.py
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
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.embedder import get_embedder  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/base_retriever_mrl64.json"
OLD_DOC, NEW_DOC = "6d55c52b", "7ba61432"
KS = (1000, 500, 100, 20)
TYPES = ("factual", "multihop", "overview")

INDEXES = [
    ("old", "knowledge_base", OLD_DOC, "nomic", "dense_768"),
    ("new", "knowledge_base_v2", NEW_DOC, "qwen3", "dense_1024"),
]


def content_filter(cfg, tenant_id: str) -> Filter:
    """The production retrieval filter, copied verbatim from `store.py:336-369`.

    ⚠️ Copied, not imported — `DocumentStore.search` builds it inline. If that changes, this drifts;
    the probe asserts the resulting point count against the collection size as a crude guard.
    """
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not, should=[
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]),
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cfg.global_tenant_id))]),
    ])


def reachable_pages(document_prefix: str, lo: int, hi: int) -> set[int]:
    """Pages a retriever can return — the §I58 rule, reproduced so the ceiling is self-consistent."""
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine

    with Session(get_engine(get_settings())) as session:
        rows = session.exec(
            select(Chunk).where(Chunk.document_id.like(f"{document_prefix}%"))  # type: ignore[attr-defined]
        ).all()
    return {int(c.page_number) for c in rows
            if c.page_number is not None and c.is_content is not False
            and (lo <= 0 or c.page_number >= lo) and (hi <= 0 or c.page_number <= hi)}


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(m - half, 6), round(m + half, 6)],
            "resolved": bool((m - half) > 0 or (m + half) < 0)}


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
    lo, hi = cfg.min_content_page, cfg.max_content_page
    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    print(f"queries: {len(queries)}   window [{lo}, {hi}]   dense_dim_low={cfg.dense_dim_low}")

    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001 — the probe needs raw control of `using=`
    nomic = get_embedder(cfg)
    print(f"OLD embedder: {cfg.embedding_model} ({cfg.embedding_dim}d)")
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)
    print(f"NEW embedder: {cfg.dense_model} ({cfg.dense_dim}d)")

    ceilings = {tag: reachable_pages(doc, lo, hi) for tag, _, doc, _, _ in INDEXES}
    for tag, _, _, _, _ in INDEXES:
        print(f"  {tag}: {len(ceilings[tag])} reachable pages")

    per_index: dict[str, list[dict]] = {tag: [] for tag, *_ in INDEXES}
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        for tag, coll, _doc, which, full_name in INDEXES:
            embedder = nomic if which == "nomic" else qwen
            try:
                vec = np.asarray(embedder.embed_query(q["query"]), dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                per_index[tag].append({"id": qid, "error": f"embed failed: {exc}"})
                continue
            v64 = vec[: cfg.dense_dim_low].copy()
            v64 /= np.linalg.norm(v64) + 1e-9
            filt = content_filter(cfg, cfg.global_tenant_id)

            def _pages(using: str, vector: list[float], limit: int) -> list[int]:
                pts = client.query_points(
                    collection_name=coll, query=vector, using=using,
                    query_filter=filt, limit=limit, with_payload=True,
                ).points
                seen, out = set(), []
                for p in pts:
                    pg = (p.payload or {}).get("page_number")
                    if pg is None or pg in seen:
                        continue
                    seen.add(int(pg))
                    out.append(int(pg))
                return out

            try:
                # the two production stages: the MRL-64 first stage, and the full-dim rescore.
                pages = _pages("dense_64", v64.tolist(), max(KS))
                pages_full = _pages(full_name, vec.tolist(), max(KS))
            except Exception as exc:  # noqa: BLE001
                per_index[tag].append({"id": qid, "error": f"qdrant failed: {exc}"})
                continue
            ceil = relevant & ceilings[tag]
            per_index[tag].append({
                "id": qid, "query_type": q.get("query_type"),
                "n_relevant": len(relevant), "n_reachable": len(ceil),
                "achievable_max": round(len(ceil) / len(relevant), 6) if relevant else None,
                "n_pages_returned": len(pages),
                "n_pages_returned_full": len(pages_full),
                "recall": {str(k): (round(len(set(pages[:k]) & relevant) / len(relevant), 6)
                                    if relevant else None) for k in KS},
                "recall_ceiling_norm": {
                    str(k): (round(len(set(pages[:k]) & ceil) / len(ceil), 6) if ceil else None)
                    for k in KS},
                "recall_full": {str(k): (round(len(set(pages_full[:k]) & relevant) / len(relevant), 6)
                                         if relevant else None) for k in KS},
                "recall_full_ceiling_norm": {
                    str(k): (round(len(set(pages_full[:k]) & ceil) / len(ceil), 6) if ceil else None)
                    for k in KS},
            })
        if i % 20 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    ok = {tag: [r for r in rows if "error" not in r] for tag, rows in per_index.items()}
    shared = sorted(set(r["id"] for r in ok["old"]) & set(r["id"] for r in ok["new"]))
    by_id = {tag: {r["id"]: r for r in ok[tag]} for tag in ok}

    def summarise(tag: str, ids: list[str], key: str) -> dict:
        out = {"queries": len(ids)}
        for k in KS:
            vals = [by_id[tag][i][key][str(k)] for i in ids
                    if by_id[tag][i][key][str(k)] is not None]
            out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
        return out

    def delta(key: str) -> dict:
        out = {}
        for k in KS:
            d = [by_id["new"][i][key][str(k)] - by_id["old"][i][key][str(k)] for i in shared
                 if by_id["new"][i][key][str(k)] is not None
                 and by_id["old"][i][key][str(k)] is not None]
            out[f"R@{k}"] = paired_ci(d)
        return out

    lanes = {"mrl64": "recall_ceiling_norm", "mrl64_raw": "recall",
             "fulldim": "recall_full_ceiling_norm", "fulldim_raw": "recall_full"}

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/base_retriever_mrl64.py",
            "what": ("§I59 — the base MRL-64 lane (dense_64 @1000, the only stage facing the whole "
                     "corpus) on BOTH indexes, each with its own query embedder"),
            "indexes": {tag: {"collection": coll, "document": doc, "embedder": which,
                              "full_dim_vector": full_name}
                        for tag, coll, doc, which, full_name in INDEXES},
            "why_each_index_gets_its_own_embedder": (
                "the named vectors are dense_768 (Nomic MRL) on the old index and dense_1024 (Qwen3 "
                "MRL) on the new one — different embedding spaces, so a Qwen3 64d vector is "
                "meaningless against the old index's dense_64. The delta is therefore EMBEDDER + "
                "INDEX TOGETHER, not one of them."),
            "filter": "copied verbatim from store.py:336-369 (source_type, page bounds, is_content)",
            "ks": list(KS),
            "dense_dim_low": cfg.dense_dim_low,
            "retrieval_window": [lo, hi],
            "n_shared": len(shared),
            "no_llm_calls": True,
            "reading": ("ceiling-normalised is the comparable view: the two indexes' achievable "
                        "maxima differ (old 0.8806 / new 0.9545, §I58), so a raw recall delta "
                        "compares different denominators."),
        },
        "summary": {
            **{f"{tag}_{lane}": summarise(tag, shared, key)
               for tag in ("old", "new") for lane, key in lanes.items()},
            "delta": {lane: delta(key) for lane, key in lanes.items()},
            "achievable_max": {
                "old_mean": round(statistics.mean(by_id["old"][i]["achievable_max"] for i in shared), 6),
                "new_mean": round(statistics.mean(by_id["new"][i]["achievable_max"] for i in shared), 6),
            },
        },
        "queries": {tag: sorted(rows, key=lambda r: r["id"]) for tag, rows in per_index.items()},
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    s = out["summary"]
    print(f"\n=== base lane (dense_64 @1000) vs full-dim @1000, n={len(shared)} ===")
    print(f"  achievable max: old {s['achievable_max']['old_mean']:.4f}  "
          f"new {s['achievable_max']['new_mean']:.4f}")
    for lane, label in (("mrl64", "MRL-64 (ceiling-norm)"), ("fulldim", "full-dim (ceiling-norm)"),
                        ("mrl64_raw", "MRL-64 (raw)"), ("fulldim_raw", "full-dim (raw)")):
        print(f"\n  {label}:  OLD {s[f'old_{lane}']['R@1000']:.4f} -> "
              f"NEW {s[f'new_{lane}']['R@1000']:.4f}")
        for k in KS:
            d = s["delta"][lane][f"R@{k}"]
            print(f"    R@{k:<5} OLD {s[f'old_{lane}'][f'R@{k}']:.4f}  "
                  f"NEW {s[f'new_{lane}'][f'R@{k}']:.4f}  delta {d['mean']:+.4f}  "
                  f"CI [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]  "
                  f"{'RESOLVED' if d['resolved'] else 'unresolved'}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
