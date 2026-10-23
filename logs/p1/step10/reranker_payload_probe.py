#!/usr/bin/env python
"""§I55 — does the cross-encoder reranker actually rerank? A payload-acceptance probe.

Why this exists
---------------
While building the DA-lane ablation, `ClusterCrossEncoderReranker.rerank` logged
`RERANKER DISABLED — … 500 Internal Server Error … Returning UNRANKED results` on roughly a
quarter of queries, and `reranker.py:131-141` **swallows it**: the failure is an ERROR log, the
function returns `chunks[:top_k]` in the pool's own order, and `evaluate_rag.py` still records
`reranker.enabled = true`. That is §I25's class — a failure that reads as a success.

This probe measures the rate directly rather than inferring it from logs. For every v2 query it
builds the SAME pool `search_with_das` would hand the reranker and POSTs the same payload
(`{"model", "query", "documents", "top_k"}`, `reranker.py:80-86`) straight to the endpoint,
recording the status code.

It sends no LLM calls and writes nothing.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/reranker_payload_probe.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402
import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
TYPES = ("factual", "multihop", "overview")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/reranker_payload_probe.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    raw = json.loads(Path(QUERIES).read_text(encoding="utf-8"))
    queries = [q for q in raw if not str(q.get("id", "")).startswith("_")]
    queries = [q for q in queries if q.get("answerable", True) and q.get("query_type") in TYPES]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    url = cfg.reranker_url if hasattr(cfg, "reranker_url") else (
        "http://10.0.10.70:8123/rerank/v1/rank")
    model = cfg.reranker_model

    rows: list[dict] = []
    with httpx.Client(timeout=60.0) as client:
        for i, q in enumerate(queries, 1):
            text = q["query"]
            try:
                vec = np.asarray(embedder.embed_query(text), dtype=np.float32)
            except Exception as exc:  # noqa: BLE001
                rows.append({"id": q["id"], "error": f"embed failed: {exc}"})
                continue
            # `reranker_fetch_k` is what evaluate_rag/run_retrieval hands the reranker.
            hits = store.search_with_das(vec, query_text=text, tenant_id=cfg.global_tenant_id,
                                         fetch_k=cfg.reranker_fetch_k)
            documents = [h.get("text", "") for h in hits]
            payload = {"model": model, "query": text, "documents": documents,
                       "top_k": min(cfg.reranker_top_k, len(documents))}
            total_chars = sum(len(d) for d in documents)
            try:
                resp = client.post(url, json=payload)
                status = resp.status_code
            except Exception as exc:  # noqa: BLE001
                status = type(exc).__name__
            rows.append({
                "id": q["id"], "query_type": q.get("query_type"),
                "n_docs": len(documents), "total_chars": total_chars,
                "max_doc_chars": max((len(d) for d in documents), default=0),
                "status": status,
            })
            if i % 10 == 0:
                print(f"  [{i}/{len(queries)}] {q['id']} …", flush=True)

    ok = [r for r in rows if "error" not in r]
    bad = [r for r in ok if r["status"] != 200]
    good = [r for r in ok if r["status"] == 200]
    out = {
        "meta": {
            "generated_by": "logs/p1/step10/reranker_payload_probe.py",
            "what": "§I55 — the reranker's payload-acceptance rate on the real v2 pools",
            "url": url, "model": model,
            "reranker_fetch_k": cfg.reranker_fetch_k,
            "reranker_top_k": cfg.reranker_top_k,
            "qdrant_collection": cfg.qdrant_collection,
            "n_queries": len(ok),
            "no_llm_calls": True,
        },
        "summary": {
            "rejected": len(bad), "accepted": len(good), "total": len(ok),
            "rejected_share": round(len(bad) / len(ok), 4) if ok else None,
            "total_chars": {
                "accepted": {"min": min((r["total_chars"] for r in good), default=None),
                             "median": statistics.median([r["total_chars"] for r in good])
                             if good else None,
                             "max": max((r["total_chars"] for r in good), default=None)},
                "rejected": {"min": min((r["total_chars"] for r in bad), default=None),
                             "median": statistics.median([r["total_chars"] for r in bad])
                             if bad else None,
                             "max": max((r["total_chars"] for r in bad), default=None)},
            },
            "n_docs": {
                "accepted": {"min": min((r["n_docs"] for r in good), default=None),
                             "median": statistics.median([r["n_docs"] for r in good])
                             if good else None,
                             "max": max((r["n_docs"] for r in good), default=None)},
                "rejected": {"min": min((r["n_docs"] for r in bad), default=None),
                             "median": statistics.median([r["n_docs"] for r in bad])
                             if bad else None,
                             "max": max((r["n_docs"] for r in bad), default=None)},
            },
            "by_type": {
                t: {"n": sum(1 for r in ok if r["query_type"] == t),
                    "rejected": sum(1 for r in ok if r["query_type"] == t and r["status"] != 200)}
                for t in TYPES
            },
        },
        "queries": sorted(rows, key=lambda r: r["id"]),
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    s = out["summary"]
    print(f"\n=== §I55 reranker payload acceptance (n={s['total']}) ===")
    print(f"  REJECTED {s['rejected']}/{s['total']} ({s['rejected_share']:.1%}) of queries")
    print(f"  accepted: total_chars median {s['total_chars']['accepted']['median']}, "
          f"n_docs median {s['n_docs']['accepted']['median']}")
    print(f"  rejected: total_chars median {s['total_chars']['rejected']['median']}, "
          f"n_docs median {s['n_docs']['rejected']['median']}")
    print(f"  by type: {s['by_type']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
