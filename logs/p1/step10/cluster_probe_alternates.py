"""Alternates probe — read-only, stdlib only. Rules OUT the competing hypothesis
that sparse/rerank merely MOVED (different port or path) rather than being down.

If the same host:port answers dense + colbert in 0.1 s, the client and network
are fine, so a timeout on the SAME server is server-side. This checks a few
other candidate locations so "moved" can be excluded, not assumed.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

TIMEOUT = 8.0  # short: we only want reachability, not a full answer

CHECKS = [
    ("8123 root",        "GET", "http://10.0.10.70:8123/", None),
    ("8123 /health",     "GET", "http://10.0.10.70:8123/health", None),
    ("8123 /docs",       "GET", "http://10.0.10.70:8123/docs", None),
    ("8000 sparse",      "POST", "http://10.0.10.70:8000/embed-text/v1/sparse-embeddings",
     {"model": "prithivida/Splade_PP_en_v1", "input": ["x"]}),
    ("8000 rerank",      "POST", "http://10.0.10.70:8000/rerank/v1/rank",
     {"model": "BAAI/bge-reranker-v2-m3", "query": "x", "documents": ["y"], "top_k": 1}),
    ("8123 sparse re",   "POST", "http://10.0.10.70:8123/embed-text/v1/sparse-embeddings",
     {"model": "Qdrant/bm25", "input": ["x"]}),
]


def hit(method, url, payload):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            r.read()
            return {"status": r.status, "latency_s": round(time.monotonic() - t0, 2), "error": None}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "latency_s": round(time.monotonic() - t0, 2),
                "error": f"HTTPError {e.code}"}
    except Exception as e:
        return {"status": None, "latency_s": round(time.monotonic() - t0, 2),
                "error": f"{type(e).__name__}: {e}"}


for name, method, url, payload in CHECKS:
    r = hit(method, url, payload)
    print(f"  {name:16s} status={r['status']} {r['latency_s']}s err={r['error']}")
