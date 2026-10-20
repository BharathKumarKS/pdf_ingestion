#!/usr/bin/env python3
"""Phase B / B2 — sustained card-throughput probe, sweeping CARD_GEN_WORKERS.

Why this exists (§I18, §I26). The card workload's concurrency knee was **never measured for
cards**. Phase B's plan compared against 4.21 calls/s, but that knee belongs to the *VLM judge*
(`Qwen/Qwen3-VL-8B-Instruct`, one page image, ~0.8 s/call) — a different model, prompt shape and
response length. A knee belongs to one model + one prompt on one server; it does not transfer.
Running at 16 effective calls (CARD_GEN_WORKERS=2) measured **~97 s/chunk against 7.6-10.9 s at 8
effective**, i.e. doubling concurrency cut aggregate throughput ~4.4x — congestion collapse, not a
slow endpoint.

And the ramp cannot be measured on the real run: `generate_cards_for_chunks` writes nothing until
every chunk is done, so a restart to change the worker count discards the entire card run. Hence a
standalone probe, run **before** the launch, per §I18's rule that probes must be *sustained* rather
than bursts and must sweep the knob rather than one value.

What it measures, per cell (one worker count):
  * chunks completed and cards produced in a fixed wall-clock budget;
  * **aggregate** chunks/min and card-calls/min (the number the ramp decision turns on);
  * per-chunk wall time p50 / p90 / max — a p90 far above p50 is queueing, i.e. the collapse;
  * the rate over the **last 60 s** of the cell, so a fast start that decays is visible;
  * error / retry / deadline counts from `src/core/llm.py` (§I24's accounting);
  * the cost of one checkpoint write, so the checkpoint's overhead is not attributed to the
    cluster when the real run is timed.

Read-only against SQLite, and it does **not** write cards: no `save_cards`, no Qdrant, no DB
mutation. It does spend real cluster LLM calls — that is the point of a throughput probe.

    uv run python logs/p1/step10/probe_card_throughput.py --workers 1,2,4 --minutes 3

Exit 0 = the sweep completed (read the table); 1 = a cell produced no cards at all.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"
POOL_SIZE = 400          # chunks available to a cell; the budget, not the pool, ends the cell
LAST_WINDOW_S = 60.0     # the "is it decaying?" window


def parse_args():
    p = argparse.ArgumentParser(description="Sustained card-throughput sweep over worker counts")
    p.add_argument("--workers", default="1,2,4",
                   help="comma-separated CARD_GEN_WORKERS values to sweep (default 1,2,4)")
    p.add_argument("--minutes", type=float, default=3.0,
                   help="wall-clock budget per cell (default 3.0). Sustained, not a burst.")
    p.add_argument("--doc-id", default=DOC_NEW)
    p.add_argument("--out", default=str(ROOT / "logs/p1/step10/phaseb_throughput_probe.json"))
    return p.parse_args()


def load_chunks(doc_id: str) -> list:
    """A deterministic, representative chunk pool: content chunks spread across the document."""
    from src.pdf_ingestion.chunker import TextChunk
    from src.pdf_ingestion.content_filter import is_content

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, document_id, tenant_id, chunk_index, text, char_start, char_end, "
        "token_count, page_number FROM chunks WHERE document_id = ? ORDER BY chunk_index",
        (doc_id,),
    ).fetchall()
    con.close()

    content = [r for r in rows if is_content(r[4])]
    if not content:
        return []

    # Evenly spaced across the document rather than the first N, so one long section does not
    # set the cell's rate. Stride = pool size.
    stride = max(1, len(content) // POOL_SIZE)
    picked = content[::stride][:POOL_SIZE]

    return [
        TextChunk(
            chunk_id=r[0], document_id=r[1], tenant_id=r[2], chunk_index=r[3], text=r[4],
            char_start=r[5], char_end=r[6], token_count=r[7], page_number=r[8],
        )
        for r in picked
    ]


def run_cell(workers: int, chunks: list, budget_s: float) -> dict:
    """One worker count, one wall-clock budget. Returns the cell's measurements."""
    from src.core.config import get_settings
    from src.core.llm import llm_call_stats, reset_llm_call_stats
    from src.pdf_ingestion.card_checkpoint import CardCheckpoint
    from src.pdf_ingestion.card_generator import CardType, get_card_generator

    base = get_settings()
    cfg = base.model_copy(update={"card_gen_workers": workers,
                                  "card_checkpoint_enabled": False})
    generator = get_card_generator(cfg)

    reset_llm_call_stats()
    print(f"\n{'=' * 92}")
    print(f"  CARD_GEN_WORKERS={workers}  ({workers * len(CardType)} effective in-flight calls)  "
          f"budget {budget_s / 60:.1f} min")
    print(f"{'=' * 92}", flush=True)

    tmpdir = tempfile.mkdtemp(prefix="card_probe_")
    cp = CardCheckpoint.open(tmpdir, "probe", [c.chunk_id for c in chunks],
                             [ct.value for ct in CardType], cfg.openai_model)

    started = time.monotonic()
    deadline = started + budget_s
    completed: list[tuple[float, float]] = []   # (finish_time, wall_seconds)
    per_chunk_started: dict = {}
    cards_total = 0
    failed_chunks = 0
    failed_types: Counter[str] = Counter()
    checkpoint_seconds: list[float] = []
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {}
        for c in chunks:
            per_chunk_started[c.chunk_id] = time.monotonic()
            futures[pool.submit(generator._generate_chunk_with_report, c)] = c

        for future in as_completed(futures):
            chunk = futures[future]
            t_finish = time.monotonic()
            wall = t_finish - per_chunk_started[chunk.chunk_id]
            try:
                cards, chunk_failed = future.result()
            except Exception as exc:
                cards, chunk_failed = [], ["<chunk raised>"]
                print(f"    !! chunk {chunk.chunk_index} raised: {exc}", flush=True)
            cards_total += len(cards)
            if chunk_failed:
                failed_chunks += 1
                failed_types.update(chunk_failed)
            completed.append((t_finish, wall))

            t0 = time.perf_counter()
            cp.record(chunk.chunk_id, chunk.chunk_index, cards, chunk_failed)
            checkpoint_seconds.append(time.perf_counter() - t0)

            if len(completed) % 20 == 0:
                rate = len(completed) / max(1e-9, t_finish - started) * 60
                print(f"    {len(completed):>4} chunks  {cards_total:>5} cards  "
                      f"{rate:>6.1f} chunks/min  last chunk {wall:>6.1f}s  "
                      f"{t_finish - started:>6.0f}s", flush=True)

            if t_finish > deadline:
                break
    finally:
        # wait=True is not politeness: in-flight calls from THIS cell would otherwise still be
        # running when the next cell starts and would contaminate its rate. The drain costs at
        # most one chunk's latency, which is the price of a measurement that means anything.
        drain_started = time.monotonic()
        pool.shutdown(wait=True, cancel_futures=True)
        drain = time.monotonic() - drain_started
        cp.close()
    if drain > 1.0:
        print(f"    (drained in-flight calls in {drain:.1f}s after the budget expired)",
              flush=True)

    elapsed = time.monotonic() - started
    # The rate is measured over the window that produced the COUNTED chunks, not including the
    # drain: in-flight calls finish after the budget expires but are not counted, so charging
    # their time to the rate would understate every cell by a different amount.
    measured = (completed[-1][0] - started) if completed else elapsed
    walls = [w for _, w in completed]
    recent = [w for t, w in completed if t > started + measured - LAST_WINDOW_S]
    recent_span = min(measured, LAST_WINDOW_S)
    stats = llm_call_stats()

    return {
        "workers": workers,
        "effective_concurrency": workers * len(CardType),
        "elapsed_s": round(measured, 1),
        "drain_s": round(drain, 1),
        "chunks_completed": len(completed),
        "cards": cards_total,
        "chunks_per_min": round(len(completed) / max(1e-9, measured) * 60, 2),
        "last60_chunks_per_min": round(len(recent) / max(1e-9, recent_span) * 60, 2),
        "card_calls_per_min": round(stats.get("calls", 0) / max(1e-9, measured) * 60, 2),
        "chunk_wall_p50_s": round(statistics.median(walls), 2) if walls else None,
        "chunk_wall_p90_s": round(_pct(walls, 90), 2) if walls else None,
        "chunk_wall_max_s": round(max(walls), 2) if walls else None,
        "failed_chunks": failed_chunks,
        "failed_card_types": dict(failed_types),
        "llm": stats,
        "checkpoint_write_mean_ms": round(statistics.mean(checkpoint_seconds) * 1000, 2)
        if checkpoint_seconds else None,
    }


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def main() -> int:
    args = parse_args()
    from src.core.config import get_settings
    from src.core.llm import _LLM_DEADLINE

    cfg = get_settings()
    workers_list = [int(w) for w in args.workers.split(",") if w.strip()]

    if cfg.use_stub_llm:
        print("!! USE_STUB_LLM is on — this probe measures a real endpoint's throughput.")
        print("   Unset it (or run outside the test env) before probing.")
        return 1

    chunks = load_chunks(args.doc_id)
    if not chunks:
        print("!! no content chunks to probe — is the document ingested?")
        return 1

    toks = sorted(c.token_count or 0 for c in chunks)
    print("=" * 92)
    print("Phase B / B2 — sustained card-throughput sweep")
    print("=" * 92)
    print(f"  document   : {args.doc_id}")
    print(f"  chunk pool : {len(chunks)} content chunks (evenly spaced, deterministic)")
    print(f"  tokens     : p50 {toks[len(toks) // 2]}  p90 {_pct([float(t) for t in toks], 90):.0f}  "
          f"max {toks[-1]}")
    print(f"  llm        : {cfg.llm_backend}  {cfg.openai_api_base}  {cfg.openai_model}")
    print(f"  deadline   : {cfg.ollama_timeout}s per read, "
          f"{_LLM_DEADLINE:.0f}s per request (§I24)")
    print(f"  note       : read-only against SQLite; no cards are saved, no DB row changes")

    cells = []
    for w in workers_list:
        cells.append(run_cell(w, chunks, args.minutes * 60))

    print("\n" + "=" * 92)
    print("  RESULT — sustained throughput by CARD_GEN_WORKERS")
    print("=" * 92)
    header = (f"  {'workers':>7} {'in-flight':>9} {'chunks':>7} {'chunks/min':>10} "
              f"{'last60/min':>10} {'p50 s':>7} {'p90 s':>7} {'max s':>7} "
              f"{'errs':>5} {'calls/min':>9}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for c in cells:
        print(f"  {c['workers']:>7} {c['effective_concurrency']:>9} {c['chunks_completed']:>7} "
              f"{c['chunks_per_min']:>10.2f} {c['last60_chunks_per_min']:>10.2f} "
              f"{c['chunk_wall_p50_s']:>7.1f} {c['chunk_wall_p90_s']:>7.1f} "
              f"{c['chunk_wall_max_s']:>7.1f} {c['failed_chunks']:>5} "
              f"{c['card_calls_per_min']:>9.1f}")

    best = max(cells, key=lambda c: c["chunks_per_min"])
    print(f"\n  fastest cell : CARD_GEN_WORKERS={best['workers']} "
          f"({best['chunks_per_min']:.2f} chunks/min)")
    if best["chunks_per_min"] > 0:
        print(f"  ETA for 3,791 chunks at that rate: "
              f"{3791 / best['chunks_per_min'] / 60:.1f} h")
    for c in cells:
        if c["failed_chunks"]:
            print(f"  ⚠ workers={c['workers']}: {c['failed_chunks']} chunk(s) with a failed card "
                  f"type — {c['failed_card_types']}")
    cw = [c["checkpoint_write_mean_ms"] for c in cells if c["checkpoint_write_mean_ms"]]
    if cw:
        print(f"  checkpoint   : {statistics.mean(cw):.2f} ms mean per chunk write "
              f"(fsync'd) — this is the §I27 overhead added to the real run")

    Path(args.out).write_text(json.dumps({
        "document_id": args.doc_id, "budget_minutes": args.minutes,
        "chunk_pool": len(chunks), "cells": cells,
    }, indent=2))
    try:
        shown = Path(args.out).relative_to(ROOT)
    except ValueError:
        shown = Path(args.out)
    print(f"  wrote {shown}")

    if all(c["chunks_completed"] == 0 for c in cells):
        print("\n  VERDICT: FAIL — no cell produced a single chunk; the LLM path is broken.")
        return 1
    print("\n  VERDICT: sweep complete — read the table, then decide the worker count.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
