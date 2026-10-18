#!/usr/bin/env python3
"""Step 8 failure diagnosis: how does the per-token endpoint scale with input size?

The run died on `embed_documents_tokens` for parent 260 of 341 — after 40 min of a phase
that had been averaging 9.3 s/parent. `cluster_embedder._post` uses
`httpx.Client(timeout=120)` and has **no retry**, so a single slow read aborts an 86-minute
run and throws away all of it (the pipeline only writes at `save_document`, which runs after
every parent is embedded).

This probe measures per-token latency and response size against the real cluster at growing
token counts, using the REAL Qwen3 tokenizer, so the practical ceiling is a number rather
than a guess.

Run:  SV_EMBED_URL=... uv run python logs/p1/step8-run/probe_token_endpoint.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.core.config import get_settings

SENTENCE = (
    "The principle of least action states that the path taken by a physical system between "
    "two states is the one for which the action integral is stationary, and this variational "
    "principle yields the Euler-Lagrange equations of motion for the system. "
)

TARGETS = [200, 500, 1000, 2000, 3000, 4000]


def main() -> int:
    cfg = get_settings()
    from transformers import AutoTokenizer
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder

    tok = AutoTokenizer.from_pretrained(cfg.dense_model, cache_dir=cfg.model_cache_dir)
    emb = get_cluster_embedder(cfg)

    print(f"endpoint: {cfg.sv_embed_url}")
    print(f"model   : {cfg.dense_model}")
    print(f"{'target':>7} {'actual':>7} {'sec':>8} {'MB':>8} {'vec/tok':>9}  ok")
    rows = []
    for target in TARGETS:
        text = SENTENCE * (target // 40 + 1)
        n = len(tok(text, add_special_tokens=False)["input_ids"])
        t0 = time.time()
        row = {"target": target, "actual_tokens": n}
        try:
            mats = emb.embed_documents_tokens([text])
            arr = mats[0]
            dt = time.time() - t0
            mb = arr.nbytes / 1e6
            row.update({"seconds": round(dt, 2), "mb": round(mb, 1),
                        "vectors": int(arr.shape[0]), "ok": True})
            print(f"{target:>7} {n:>7} {dt:>8.2f} {mb:>8.1f} {arr.shape[0]:>9}  ok")
        except Exception as exc:  # noqa: BLE001
            dt = time.time() - t0
            row.update({"seconds": round(dt, 2), "ok": False,
                        "error": f"{type(exc).__name__}: {exc}"})
            print(f"{target:>7} {n:>7} {dt:>8.2f} {'-':>8} {'-':>9}  FAIL {type(exc).__name__}")
        rows.append(row)

    dest = Path(__file__).with_name("probe_token_endpoint.json")
    dest.write_text(json.dumps({"endpoint": cfg.sv_embed_url, "rows": rows}, indent=2) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
