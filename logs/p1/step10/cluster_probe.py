"""Cluster lane probe — read-only. Answers ONE question: which of the four
10.0.10.70:8123 lanes answer right now, and how fast.

Session 35's blocker: sparse + rerank POSTs timed out (>=30 s) while dense and
ColBERT answered. This re-probes the same four endpoints. NO store write, NO
project import (stdlib only) so it cannot be affected by a broken venv.

Writes logs/p1/step10/cluster_probe.json (overwrites; pass --out to redirect).
Exits 0 always (the JSON is the record); prints a one-line summary.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

BASE = "http://10.0.10.70:8123"
TIMEOUT = 35.0  # >= the 30 s that session 35 saw fail, so "slow" != "down"

LANES = [
    ("dense",   f"{BASE}/embed-text/v1/embeddings",
     {"model": "nomic-ai/nomic-embed-text-v1.5", "input": ["Newton's first law"]}),
    ("colbert", f"{BASE}/embed-text/v1/multivector-embeddings",
     {"model": "colbert-ir/colbertv2.0", "input": ["Newton's first law"]}),
    ("sparse",  f"{BASE}/embed-text/v1/sparse-embeddings",
     {"model": "prithivida/Splade_PP_en_v1", "input": ["Newton's first law"]}),
    ("rerank",  f"{BASE}/rerank/v1/rank",
     {"model": "BAAI/bge-reranker-v2-m3", "query": "Newton's first law",
      "documents": ["the law of inertia", "a recipe for bread"], "top_k": 2}),
]


def probe(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            dt = time.monotonic() - t0
            try:
                parsed = json.loads(raw)
                keys = list(parsed.keys()) if isinstance(parsed, dict) else f"list[{len(parsed)}]"
            except Exception:
                keys = "<unparseable>"
            return {"status": r.status, "latency_s": round(dt, 2),
                    "bytes": len(raw), "shape": keys, "error": None}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "latency_s": round(time.monotonic() - t0, 2),
                "bytes": 0, "shape": None, "error": f"HTTPError {e.code}"}
    except Exception as e:  # timeout, connrefused, etc.
        return {"status": None, "latency_s": round(time.monotonic() - t0, 2),
                "bytes": 0, "shape": None, "error": f"{type(e).__name__}: {e}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/cluster_probe.json")
    args = ap.parse_args()

    out = {"probed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "base": BASE, "timeout_s": TIMEOUT, "lanes": {}}
    for name, url, payload in LANES:
        out["lanes"][name] = {"url": url, **probe(url, payload)}

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    for name, r in out["lanes"].items():
        ok = "OK " if r["status"] == 200 else "DOWN"
        print(f"  {ok} {name:8s} status={r['status']} {r['latency_s']}s "
              f"shape={r['shape']} err={r['error']}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
