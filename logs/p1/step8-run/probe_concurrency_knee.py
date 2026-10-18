#!/usr/bin/env python3
"""Step 8 fix: where is the per-token endpoint's concurrency knee?

Why this exists. The ingest's dominant cost is `LateChunkEmbedder.embed_children`, which is a
STRICT SERIAL loop over parents — one per-token POST at a time. A serial latency probe
(`probe_token_endpoint.py`) shows the per-request cost is roughly

    seconds ≈ 5.2 + tokens / 53

i.e. a **~5 s fixed overhead per request** on top of the transfer. With 341 parents that is
~30 minutes of pure per-request overhead, and it is why the late-chunk phase took 60 of the
run's 86 minutes. Concurrency is therefore worth real money here — but the same cluster
visibly degrades under sustained load (10.8 s/parent in the first 50 parents of the run vs
16.5 s in the last 50), so the worker count has to be measured, not guessed.

This mirrors the repo's own established practice: the Session 3 judge ramp probe found
4.21 calls/s optimal and 16/32 collapsing to ~1.2/s from queueing. Never assume the knee.

Run:  SV_EMBED_URL=... uv run python logs/p1/step8-run/probe_concurrency_knee.py
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.core.config import get_settings

SENTENCE = (
    "The principle of least action states that the path taken by a physical system between "
    "two states is the one for which the action integral is stationary, and this variational "
    "principle yields the Euler-Lagrange equations of motion for the system. "
)
TARGET_TOKENS = 1500
LEVELS = [1, 2, 4, 8, 16]


def main() -> int:
    cfg = get_settings()
    import httpx
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(cfg.dense_model, cache_dir=cfg.model_cache_dir)
    text = SENTENCE * (TARGET_TOKENS // 40 + 1)
    n_tok = len(tok(text, add_special_tokens=False)["input_ids"])

    print(f"endpoint : {cfg.sv_embed_url}")
    print(f"payload  : {n_tok} tokens per request\n")
    print(f"{'workers':>8} {'wall s':>8} {'req/s':>7} {'tok/s':>8} {'s/req':>7}  errors")
    rows = []
    for workers in LEVELS:
        t0 = time.time()
        errors = 0

        def one(_i: int) -> bool:
            try:
                with httpx.Client(timeout=600) as c:
                    r = c.post(cfg.sv_embed_url, json={
                        "model": cfg.dense_model, "input": [text],
                        "return_token_embeddings": True,
                    })
                    r.raise_for_status()
                    return len(r.json()["data"]) == 1
            except Exception:  # noqa: BLE001
                return False

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, range(workers)))
        wall = time.time() - t0
        errors = sum(1 for ok in results if not ok)
        rows.append({
            "workers": workers, "wall_s": round(wall, 2),
            "requests_per_s": round(workers / wall, 2),
            "tokens_per_s": round(workers * n_tok / wall, 0),
            "s_per_request": round(wall / workers, 2),
            "errors": errors,
        })
        r = rows[-1]
        print(f"{workers:>8} {wall:>8.2f} {r['requests_per_s']:>7.2f} "
              f"{r['tokens_per_s']:>8.0f} {r['s_per_request']:>7.2f}  {errors}")

    # The knee = the worker count with the highest aggregate throughput.
    best = max(rows, key=lambda r: r["tokens_per_s"])
    print(f"\nknee: {best['workers']} workers at {best['tokens_per_s']:.0f} tok/s "
          f"(serial = {rows[0]['tokens_per_s']:.0f} tok/s, "
          f"{best['tokens_per_s'] / max(rows[0]['tokens_per_s'], 1):.1f}x)")

    dest = Path(__file__).with_name("probe_concurrency_knee.json")
    dest.write_text(json.dumps(
        {"endpoint": cfg.sv_embed_url, "payload_tokens": n_tok,
         "rows": rows, "knee_workers": best["workers"]}, indent=2) + "\n")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
