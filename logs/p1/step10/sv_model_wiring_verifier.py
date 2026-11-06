#!/usr/bin/env python3
"""Verifier for the §I117 cluster-model wiring (`sv_colbert_model` / `sv_sparse_model`).

Checks, from the CODE (not from the change's own claim):
  V1/V2  ClusterColBERTEmbedder resolves `sv_colbert_model or colbert_model`.
  V3/V4  ClusterSpladeEmbedder resolves `sv_sparse_model or splade_model`.
  V5/V6  both config DEFAULTS are EMPTY — nothing switches by accident.
  V7/V8  the resolved model actually rides in the request payload (end-to-end, httpx stubbed).

Run:  .venv/bin/python logs/p1/step10/sv_model_wiring_verifier.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

_BASE = dict(qdrant_in_memory=True, sqlite_url="sqlite:///./data/test_synapse.db")


def _sent(inst, call, *args, sparse: bool = False) -> list[dict]:
    """Run `inst.<call>(*args)` with httpx.post stubbed; return the payloads sent."""
    import httpx
    sent: list[dict] = []

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            emb = {"indices": [1], "values": [0.5]} if sparse else [[0.1, 0.2]]
            return {"data": [{"embedding": emb, "index": 0}]}

    real = httpx.post
    httpx.post = lambda url, **kw: (sent.append(kw.get("json", {})), FakeResp())[1]
    try:
        getattr(inst, call)(*args)
    finally:
        httpx.post = real
    return sent


def verify() -> list[tuple[str, bool]]:
    from src.core.config import Settings
    from src.pdf_ingestion.colbert_embedder import ClusterColBERTEmbedder
    from src.pdf_ingestion.splade_embedder import ClusterSpladeEmbedder

    c: list[tuple[str, bool]] = []
    add = lambda n, cond: c.append((n, bool(cond)))  # noqa: E731

    cb = ClusterColBERTEmbedder(Settings(**_BASE, sv_colbert_url="http://x",
                                         colbert_model="LOCAL_C", sv_colbert_model=""))
    add("V1  ColBERT falls back to colbert_model when sv_colbert_model is EMPTY",
        cb._model == "LOCAL_C")
    cb2 = ClusterColBERTEmbedder(Settings(**_BASE, sv_colbert_url="http://x",
                                          colbert_model="LOCAL_C", sv_colbert_model="NEW_C"))
    add("V2  ColBERT prefers sv_colbert_model when SET", cb2._model == "NEW_C")

    sp = ClusterSpladeEmbedder(Settings(**_BASE, sv_sparse_url="http://x",
                                        splade_model="LOCAL_S", sv_sparse_model=""))
    add("V3  sparse falls back to splade_model when sv_sparse_model is EMPTY",
        sp._model == "LOCAL_S")
    sp2 = ClusterSpladeEmbedder(Settings(**_BASE, sv_sparse_url="http://x",
                                         splade_model="LOCAL_S", sv_sparse_model="NEW_S"))
    add("V4  sparse prefers sv_sparse_model when SET", sp2._model == "NEW_S")

    d = Settings(**_BASE)
    add("V5  sv_colbert_model DEFAULT is empty (nothing switches by accident)",
        d.sv_colbert_model == "")
    add("V6  sv_sparse_model DEFAULT is empty", d.sv_sparse_model == "")

    p = _sent(cb2, "embed_query", "q")
    add("V7  the RESOLVED ColBERT model rides in the request payload",
        p and p[0].get("model") == "NEW_C")
    q = _sent(sp2, "encode_sparse", "x", sparse=True)
    add("V8  the RESOLVED sparse model rides in the request payload",
        q and q[0].get("model") == "NEW_S")
    return c


def main() -> int:
    checks = verify()
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
    n_ok = sum(1 for _, ok in checks if ok)
    print(f"\n{n_ok}/{len(checks)} checks PASS")
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
