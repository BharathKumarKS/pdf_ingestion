#!/usr/bin/env python3
"""Phase B / B1 — one-chunk card probe. Read-only, 8 LLM calls, seconds.

Why this exists (§I23's lesson): `generate_cards_for_chunks` catches per-chunk exceptions, counts
them into a local `failed` variable, and **logs it without failing the process**. So a broken LLM
produces zero cards reported as a completed run — the same shape as the graph build that swallowed
44 real timeouts and printed "0 failed".

This probe spends 8 calls on ONE real content chunk and asserts the pipeline actually works, before
a fresh session commits hours of cluster time to 3,791 chunks.

Checks:
  1. the generator returns cards at all (0 cards -> STOP);
  2. coverage: >= 6 of the 8 CardType values produced a card;
  3. `question` and `factoid` — the two MULTI-card parsers — each return >= 1 card. These are the
     ones that silently degrade to empty when their parser drifts;
  4. every returned card has non-empty content;
  5. prints the cards so they can be read (the course's "read the artifacts" rule, done early).

Also times the call, which is the first sustained-throughput datapoint for the B2 ramp decision.

    uv run python logs/p1/step10/probe_phaseb_card_one_chunk.py

Exit 0 = PASS, 1 = STOP.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "logs/p1/step10/phaseb_card_probe.json"
DB = ROOT / "data/synapse.db"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"

MIN_TYPE_COVERAGE = 6


def main() -> int:
    from src.core.config import get_settings
    from src.pdf_ingestion.card_generator import CardType, get_card_generator
    from src.pdf_ingestion.chunker import TextChunk
    from src.pdf_ingestion.content_filter import is_content

    cfg = get_settings()

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, document_id, tenant_id, chunk_index, text, char_start, char_end, "
        "token_count, page_number FROM chunks WHERE document_id = ? ORDER BY chunk_index",
        (DOC_NEW,),
    ).fetchall()
    con.close()

    content = [r for r in rows if is_content(r[4])]
    if not content:
        print("!! no content chunks — nothing to probe")
        return 1

    # Deterministic pick: the content chunk nearest the median token count, so the probe is
    # representative rather than "the first chunk", which is often short or a section heading.
    toks = sorted(r[7] or 0 for r in content)
    target = toks[len(toks) // 2]
    row = min(content, key=lambda r: abs((r[7] or 0) - target))

    chunk = TextChunk(
        chunk_id=row[0], document_id=row[1], tenant_id=row[2], chunk_index=row[3],
        text=row[4], char_start=row[5], char_end=row[6], token_count=row[7],
        page_number=row[8],
    )

    print("=" * 92)
    print("Phase B / B1 — one-chunk card probe")
    print("=" * 92)
    print(f"  chunk      : index={chunk.chunk_index}  page={chunk.page_number}  "
          f"tokens={chunk.token_count}  chars={len(chunk.text)}")
    print(f"  workers    : card_gen_workers={cfg.card_gen_workers} "
          f"(effective concurrency {cfg.card_gen_workers * len(CardType)} across chunks)")
    print(f"  llm        : backend={cfg.llm_backend}  base={cfg.openai_api_base}  "
          f"model={cfg.openai_model}")
    print(f"  chunk text : {chunk.text[:180]!r}…")

    generator = get_card_generator(cfg)
    t0 = time.perf_counter()
    cards = generator.generate_cards_for_chunk(chunk)
    elapsed = time.perf_counter() - t0

    by_type = Counter(c.card_type for c in cards)
    print(f"\n  returned {len(cards)} cards in {elapsed:.1f}s "
          f"({len(CardType) / elapsed:.2f} types/s for this chunk)")
    print(f"\n  {'card_type':14} {'n':>3}   first title")
    for ct in CardType:
        n = by_type.get(ct.value, 0)
        title = next((c.title or "" for c in cards if c.card_type == ct.value), "")
        print(f"  {ct.value:14} {n:>3}   {title[:52]}")

    failures: list[str] = []
    if not cards:
        failures.append("ZERO cards returned — the card pipeline is broken; do not start the run")
    covered = sum(1 for ct in CardType if by_type.get(ct.value, 0) > 0)
    if cards and covered < MIN_TYPE_COVERAGE:
        failures.append(f"only {covered}/8 card types produced output (floor {MIN_TYPE_COVERAGE})")
    for multi in (CardType.QUESTION, CardType.FACTOID):
        if cards and by_type.get(multi.value, 0) == 0:
            failures.append(f"'{multi.value}' (a multi-card parser) returned nothing")
    empty = [c.card_type for c in cards if not (c.content or "").strip()]
    if empty:
        failures.append(f"{len(empty)} cards have empty content: {Counter(empty)}")

    print("\n  ── the cards themselves (read them; the course's own rule) ──")
    for c in cards[:6]:
        body = " ".join((c.content or "").split())
        print(f"\n  [{c.card_type}] {c.title or '(no title)'}")
        print(f"    {body[:300]}{'…' if len(body) > 300 else ''}")

    OUT.write_text(json.dumps({
        "chunk_index": chunk.chunk_index, "page": chunk.page_number,
        "tokens": chunk.token_count, "elapsed_s": round(elapsed, 2),
        "cards_returned": len(cards),
        "by_type": dict(by_type), "types_covered": covered,
        "failures": failures,
        "sample": [{"type": c.card_type, "title": c.title,
                    "content": (c.content or "")[:600]} for c in cards[:10]],
    }, indent=2))
    print(f"\n  wrote {OUT.relative_to(ROOT)}")

    print()
    print("=" * 92)
    if failures:
        print("B1 VERDICT: FAIL — do not start Phase B")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 92)
        return 1
    print(f"B1 VERDICT: PASS — {len(cards)} cards, {covered}/8 types, "
          f"multi-card parsers alive")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    sys.exit(main())
