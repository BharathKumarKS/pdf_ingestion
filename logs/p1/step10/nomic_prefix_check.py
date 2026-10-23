#!/usr/bin/env python
"""§I62 — does the CLUSTER's Nomic reproduce the local `NomicEmbedder`'s vector space?

Why this matters. The planned cross-embedder experiment re-embeds the NEW index's chunks with
Nomic, to separate "Qwen3 ranks worse" from "the re-chunk ranks worse". That is only valid if the
vectors land in the SAME space as the old index's `dense_768`.

`embedder.NomicEmbedder` applies Nomic's task prefixes (`search_document: ` / `search_query: `) —
they are documented as required for v1.5. The cluster's `/embed-text/v1/embeddings` endpoint is a
generic passthrough and may not. If it does not, the re-embed is in a different space and every
number from the experiment would be meaningless.

So: embed the same real chunk text three ways and compare directions.
  * local  `NomicEmbedder.embed_documents` (prefix applied by the code)
  * cluster, raw text
  * cluster, text prefixed with `search_document: `

Run:
    unset PYTHONPATH && export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    uv run python logs/p1/step10/nomic_prefix_check.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.embedder import get_embedder  # noqa: E402

DB = REPO / "data/synapse.db"
URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
MODEL = "nomic-ai/nomic-embed-text-v1.5"
DOC_PREFIX = "search_document: "


def cluster_embed(texts: list[str]) -> np.ndarray:
    body = json.dumps({"model": MODEL, "input": texts}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    items = sorted(d["data"], key=lambda x: x.get("index", 0))
    m = np.asarray([it["embedding"] for it in items], dtype=np.float64)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)


def main() -> int:
    import sqlite3

    cfg = get_settings()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    texts = [r[0] for r in con.execute(
        "SELECT text FROM chunks WHERE document_id LIKE '7ba61432%' AND is_content IS NOT 0 "
        "AND page_number BETWEEN 30 AND 936 LIMIT 5")]
    if not texts:
        print("ABORT: no chunks found", file=sys.stderr)
        return 3

    local = get_embedder(cfg)
    print(f"local embedder: {type(local).__name__}")
    # `embed_documents` is the path the ingest uses — it owns the prefix convention.
    loc = np.asarray(local.embed_documents(texts), dtype=np.float64)
    loc /= (np.linalg.norm(loc, axis=1, keepdims=True) + 1e-12)

    raw = cluster_embed(texts)
    pre = cluster_embed([DOC_PREFIX + t for t in texts])

    def cos(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.sum(a * b, axis=1)

    print(f"\n  {'chunk':>5}  {'cos(local, cluster_raw)':>24}  {'cos(local, cluster_prefixed)':>28}")
    for i in range(len(texts)):
        print(f"  {i:>5}  {cos(loc[i:i+1], raw[i:i+1])[0]:>24.6f}  "
              f"{cos(loc[i:i+1], pre[i:i+1])[0]:>28.6f}")
    c_raw = float(np.mean(cos(loc, raw)))
    c_pre = float(np.mean(cos(loc, pre)))
    print(f"\n  mean cos(local, cluster_raw)      = {c_raw:.6f}")
    print(f"  mean cos(local, cluster_prefixed) = {c_pre:.6f}")

    verdict = ("cluster applies the prefix itself (or it does not matter)"
               if c_raw > 0.999 else
               "cluster does NOT apply the prefix — the caller MUST add 'search_document: '"
               if c_pre > 0.999 else
               "NEITHER matches the local embedder — the spaces are different; do not use this path")
    print(f"\n  VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
