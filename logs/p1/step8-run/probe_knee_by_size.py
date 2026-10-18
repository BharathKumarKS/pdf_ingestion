#!/usr/bin/env python3
"""Step 8 attempt 3: the ramp probe, done properly — workers x PAYLOAD SIZE.

Why this replaces `probe_concurrency_knee.py` (IMPROVEMENTS.md §I18). That probe fired a FIXED
1,749-token payload, found throughput still rising at 16 workers, and that is how 8 was chosen.
But the real corpus is not uniform: attempt 1 measured parent sizes with **median 1,190, mean
1,387, max 4,762 tokens**. A per-token response is ~160x the pooled payload, so a 4,762-token
parent returns ~19 MB. The old probe therefore never exercised the regime the run actually
uses — and attempt 2, at 8 workers against the real distribution, lost the endpoint after
7 minutes. A probe validates a REGIME; a fixed payload size is a regime assumption nobody
stated. This one sweeps both axes.

Two things it reports that the old probe did not:
  * throughput per (workers, size) cell, so the knee can be read per payload size;
  * a SERVICE-HEALTH check between cells, so a collapse is attributed to the cell that caused it
    rather than discovered 40 minutes later.

Run:  SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings \
        uv run python logs/p1/step8-run/probe_knee_by_size.py
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

# The real corpus's distribution (attempt 1, 341 parents): median 1,190 / mean 1,387 / max 4,762.
SIZES = [1190, 3000, 4762]
WORKER_LEVELS = [1, 2, 4, 8]

# A short burst per cell, not sustained load: the point is the SHAPE, and sustained hammering is
# what we are trying to avoid. Requests per cell == the worker count (one wave).
REQUEST_TIMEOUT = 600.0


def _health(url: str, model: str) -> tuple[bool, float]:
    """One cheap pooled call — is the service still accepting and answering?"""
    import httpx

    t0 = time.time()
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(url, json={"model": model, "input": ["ping"]})
            r.raise_for_status()
        return True, time.time() - t0
    except Exception:  # noqa: BLE001
        return False, time.time() - t0


def main() -> int:
    cfg = get_settings()
    import httpx
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(cfg.dense_model, cache_dir=cfg.model_cache_dir)
    url = cfg.sv_embed_url
    model = cfg.dense_model

    texts = {}
    for target in SIZES:
        text = SENTENCE * (target // 40 + 1)
        texts[target] = (text, len(tok(text, add_special_tokens=False)["input_ids"]))

    print(f"endpoint: {url}")
    print(f"model   : {model}")
    ok, dt = _health(url, model)
    print(f"health before: {'ok' if ok else 'DOWN'} in {dt:.2f}s\n")

    rows: list[dict] = []
    aborted_at: str | None = None

    for target in SIZES:
        text, n_tok = texts[target]
        print(f"--- payload ~{target} tokens (actual {n_tok}) ---")
        print(f"{'workers':>8} {'wall s':>8} {'req/s':>7} {'tok/s':>8} {'s/req':>8}  errors")

        for workers in WORKER_LEVELS:
            def one(_i: int) -> tuple[bool, str]:
                try:
                    with httpx.Client(timeout=REQUEST_TIMEOUT) as c:
                        r = c.post(url, json={"model": model, "input": [text],
                                              "return_token_embeddings": True})
                        r.raise_for_status()
                        return len(r.json()["data"]) == 1, ""
                except Exception as exc:  # noqa: BLE001
                    return False, type(exc).__name__

            t0 = time.time()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(one, range(workers)))
            wall = time.time() - t0
            errors = [msg for ok_i, msg in results if not ok_i]
            row = {
                "payload_tokens": n_tok, "workers": workers, "wall_s": round(wall, 2),
                "tokens_per_s": round(workers * n_tok / wall, 0),
                "s_per_request": round(wall / workers, 2),
                "errors": len(errors), "error_kinds": sorted(set(errors)),
            }
            rows.append(row)
            print(f"{workers:>8} {wall:>8.2f} {workers / wall:>7.2f} "
                  f"{row['tokens_per_s']:>8.0f} {row['s_per_request']:>8.2f}  "
                  f"{len(errors)} {' '.join(sorted(set(errors)))[:30]}")

            # Attribute a collapse to the cell that caused it, and stop escalating.
            ok, dt = _health(url, model)
            if not ok:
                aborted_at = f"payload {n_tok}, {workers} workers"
                print(f"    !! SERVICE DOWN after this cell ({aborted_at}) — stopping")
                break
        print()
        if aborted_at:
            break

    # Best SAFE cell per payload size (no errors, service survived).
    best: dict[int, dict] = {}
    for r in rows:
        if r["errors"]:
            continue
        cur = best.get(r["payload_tokens"])
        if cur is None or r["tokens_per_s"] > cur["tokens_per_s"]:
            best[r["payload_tokens"]] = r

    print("=== safe best per payload size ===")
    for n_tok in sorted(best):
        b = best[n_tok]
        print(f"  {n_tok:>5} tokens -> {b['workers']} workers at {b['tokens_per_s']:.0f} tok/s")

    # The setting must be safe at the LARGEST size, since a run hits all sizes.
    if best:
        largest = max(best)
        safe_workers = max(r["workers"] for r in rows
                           if not r["errors"] and r["workers"] <= best[largest]["workers"])
        print(f"\nRECOMMENDED late_chunk_workers = {safe_workers} "
              f"(safe at the largest payload, {largest} tokens)")

    out = {"endpoint": url, "rows": rows, "aborted_at": aborted_at,
           "best_per_size": {str(k): v for k, v in best.items()}}
    dest = Path(__file__).with_name("probe_knee_by_size.json")
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nwrote {dest}")
    return 0 if not aborted_at else 1


if __name__ == "__main__":
    raise SystemExit(main())
