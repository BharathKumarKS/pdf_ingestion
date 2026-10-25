#!/usr/bin/env python3
"""Generate the HyDE cache (plan §2) — one LLM call per factual/overview query, ONCE.

    unset PYTHONPATH
    uv run python scripts/build_hyde_cache.py                     # reuse what exists
    uv run python scripts/build_hyde_cache.py --force             # regenerate everything

The cache is what makes an arm-to-arm comparison meaningful: without it, each arm embeds a
DIFFERENT hypothetical for the same query (`evaluate_rag.py` calls the LLM per query), so the
instrument moves the number instead of the treatment. It caches the TEXT, not the vector, so one
file serves every candidate embedder.

Exits non-zero when any query failed — an incomplete cache is a measurement defect, not a warning
(§I25's class: a total loss that reads as a success).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from loguru import logger  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.hyde_cache import build, load, prompt_digest  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the HyDE hypothetical cache")
    ap.add_argument("--queries", default=str(QUERIES))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = get_settings()
    qpath = Path(args.queries)
    queries = json.loads(qpath.read_text(encoding="utf-8"))

    targets = [q for q in queries
               if isinstance(q, dict) and q.get("query_type") in ("factual", "overview")]
    print(f"model      : {cfg.openai_model}   (the phase's model, read from config — §I52)")
    print(f"queries    : {qpath}  ({len(targets)} factual/overview targets)")
    print(f"prompt dgst: {prompt_digest()}")

    cache = build(qpath, queries, cfg=cfg, force=args.force)
    print(f"\ncache      : {cache.path}")
    print(f"entries    : {len(cache)}  (reused {cache.meta['n_reused']}, "
          f"generated {cache.meta['n_generated']}, failed {cache.meta['n_failed']})")
    print(f"wall       : {cache.meta['wall_seconds']}s")

    if cache.meta["n_failed"]:
        print(f"\nFAILED ids: {[f['id'] for f in cache.meta['failures']]}", file=sys.stderr)
        return 2

    # Re-read through the validating loader — a file the loader refuses is not a built cache.
    check = load(qpath, cfg=cfg)
    logger.info("verified: {} entries load and validate", len(check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
