#!/usr/bin/env python
"""§G2 — build Leiden community summaries for one document.

Reads the concept graph from Memgraph, runs the Leiden ladder, and summarises each leaf community
from the FULL passages behind it, merging upward into parent-community summaries. Retrieved by
map-reduce for the global-sensemaking query only.

Dry-run by DEFAULT — it computes the hierarchy and the prompt sizes and makes **no** LLM calls, so
the spend is visible before it happens (V4). `--yes` actually summarises.

⚠️ The modularity gate (`logs/p1/step10/g2_leiden_gate.py`) must pass BEFORE this is run against
the live graph — §G2 is not built on communities that are salt-and-pepper.

The real run is **checkpointed and resumable** (§I53): each completed community is appended to
`data/summary_cache/<doc8>__<key>.jsonl` and a re-run skips what is done. Every LLM call is logged
with its prompt size and latency, plus a rolling rate line — the 2026-10-22 build made 597
sequential calls and logged nothing per call, so a stall and a slow-but-healthy run looked the same.

    uv run python scripts/build_community_summaries.py --doc-id <uuid>           # dry run
    uv run python scripts/build_community_summaries.py --doc-id <uuid> --yes --out out.json
    uv run python scripts/build_community_summaries.py --doc-id <uuid> --yes --no-resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from src.pdf_ingestion.community_summaries import (
    DEFAULT_MAX_PROMPT_CHARS,
    DEFAULT_RESOLUTIONS,
    LEAF_PROMPT,
    PARENT_PROMPT,
    SYSTEM_PROMPT,
    build_hierarchy,
    read_concept_chunks,
    read_concept_graph,
    read_concept_names,
    summarize_communities,
)
from src.pdf_ingestion.summary_checkpoint import SummaryCheckpoint, prompt_digest

DEFAULT_OUT_DIR = Path("logs/p1/step10")
DEFAULT_CACHE_DIR = Path("data/summary_cache")

# The prompts whose identity is part of the checkpoint key. A change to any of them means the
# summaries are of a different question and the checkpoint must not be reused.
PROMPT_TEMPLATES = {"system": SYSTEM_PROMPT, "leaf": LEAF_PROMPT, "parent": PARENT_PROMPT}


def _full_chunk_texts(cfg, chunk_ids: list[str]) -> list[str]:
    """FULL chunk text from SQLite — never the graph's 500-char `Chunk.chunk_text` stub (V6)."""
    if not chunk_ids:
        return []
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine

    with Session(get_engine(cfg)) as session:
        rows = session.exec(select(Chunk).where(Chunk.id.in_(chunk_ids))).all()  # type: ignore[attr-defined]
    by_id = {c.id: c.text for c in rows}
    return [by_id[i] for i in chunk_ids if i in by_id]


def _make_progress(every: int, every_seconds: float):
    """A per-call logger plus a rolling rate line.

    §I53's monitoring gap: the 597-call build logged nothing per call, so nothing in the log could
    distinguish "healthy and slow" from "stalled" (§I23's lesson — read the RATE, not a status code).
    """
    state = {"calls": 0, "started": time.monotonic(), "last_report": 0.0}

    def on_call(kind: str, where, prompt_chars: int, elapsed: float, empty: bool) -> None:
        state["calls"] += 1
        n = state["calls"]
        level, community = where if where else ("?", "?")
        flag = "  <== EMPTY (a failure, not a summary)" if empty else ""
        print(
            f"  call {n}: level {level} community {community} {kind} "
            f"{prompt_chars} chars {elapsed:.1f}s{flag}",
            flush=True,
        )
        now = time.monotonic()
        if n % max(1, every) == 0 or (now - state["last_report"]) >= every_seconds:
            state["last_report"] = now
            total = now - state["started"]
            rate = (n / total * 60.0) if total else 0.0
            print(
                f"  -- {n} call(s) in {total / 60.0:.1f} min = {rate:.1f} calls/min",
                flush=True,
            )

    return on_call


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="§G2 — Leiden community summaries")
    parser.add_argument("--doc-id", required=True, help="Document id in Memgraph")
    parser.add_argument("--yes", action="store_true", help="summarise; the default is a dry run")
    parser.add_argument("--out", type=Path, default=None, help="artifact path for the summaries")
    parser.add_argument("--no-resume", action="store_true",
                        help="discard the checkpoint for this run's key and re-summarise everything")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR,
                        help=f"checkpoint directory (default {DEFAULT_CACHE_DIR})")
    parser.add_argument("--progress-every", type=int, default=25,
                        help="print a rate line every N calls (default 25)")
    parser.add_argument("--progress-seconds", type=float, default=60.0,
                        help="print a rate line at least this often (default 60 s)")
    parser.add_argument("--max-chunks", type=int, default=None,
                        help="cap chunks per leaf community (cost control)")
    parser.add_argument("--max-prompt-chars", type=int, default=DEFAULT_MAX_PROMPT_CHARS,
                        help=f"prompt budget in chars; a community that does not fit is summarised "
                             f"map-reduce (default {DEFAULT_MAX_PROMPT_CHARS} = the SUMMARISER's "
                             f"131,072-token context at the measured 4.5 chars/token, less output room)")
    parser.add_argument("--seed", type=int, default=20261020,
                        help="Leiden seed — MUST match g2_leiden_gate.py's SEED (20261020) or the "
                             "communities summarised are not the communities the gate approved")
    args = parser.parse_args(argv)

    from src.core.config import get_settings
    from src.core.database import get_memgraph

    cfg = get_settings()
    driver = get_memgraph(cfg)
    if driver is None:
        print("ERROR: Memgraph driver unavailable — check MEMGRAPH_HOST/PORT", file=sys.stderr)
        return 2

    with driver.session() as session:
        g = read_concept_graph(session, args.doc_id)
        concept_chunks = read_concept_chunks(session, args.doc_id)
        n_names = len(read_concept_names(session, args.doc_id))

    if g.number_of_nodes() == 0:
        print(f"ERROR: no Concept nodes for document {args.doc_id!r} — refusing", file=sys.stderr)
        return 2

    hierarchy = build_hierarchy(g, resolutions=DEFAULT_RESOLUTIONS, seed=args.seed)
    print(
        f"concepts={g.number_of_nodes()} edges={g.number_of_edges()} "
        f"isolated_dropped={n_names - g.number_of_nodes()} "
        f"levels={[lvl.resolution for lvl in hierarchy.levels]} "
        f"q={[round(lvl.q, 4) for lvl in hierarchy.levels]} "
        f"nesting={hierarchy.nesting}",
        file=sys.stdout,
    )
    for level, lvl in enumerate(hierarchy.levels):
        if not lvl.connectivity["all_connected"]:
            print(
                f"WARNING: level {level} (res {lvl.resolution}) has disconnected communities "
                f"(V2): {lvl.connectivity['disconnected'][:3]}",
                file=sys.stderr,
            )

    # Read the FULL text even on a dry run: it is a local SQLite read, makes no LLM call, and it is
    # what lets the dry run report the prompt sizes. Only the LLM calls are gated by `dry_run`.
    get_texts = lambda ids: _full_chunk_texts(cfg, ids)             # noqa: E731

    # The checkpoint is opened for a REAL run only: a dry run must not create files. Its key carries
    # the SUMMARISER's model (cfg.openai_model) — not the graph build's extractor (§I52) — because a
    # model swap changes what a summary is.
    checkpoint = None
    if args.yes:
        checkpoint = SummaryCheckpoint.open(
            directory=args.cache_dir,
            document_id=args.doc_id,
            model=cfg.openai_model,
            seed=args.seed,
            resolutions=DEFAULT_RESOLUTIONS,
            max_prompt_chars=args.max_prompt_chars,
            prompt_digests={k: prompt_digest(v) for k, v in PROMPT_TEMPLATES.items()},
            fresh=args.no_resume,
        )
        print(f"checkpoint: {checkpoint.path} ({len(checkpoint.entries)} community(ies) on file)")

    on_call = _make_progress(args.progress_every, args.progress_seconds) if args.yes else None

    try:
        out = summarize_communities(
            hierarchy, concept_chunks, get_texts, dry_run=not args.yes,
            max_chunks_per_community=args.max_chunks,
            max_prompt_chars=args.max_prompt_chars,
            checkpoint=checkpoint,
            on_call=on_call,
        )
    finally:
        if checkpoint is not None:
            checkpoint.close()

    verb = "SUMMARISED" if args.yes else "DRY RUN"
    print(
        f"{verb}: {out['total_calls']} LLM call(s) "
        f"(by level {out['calls_by_level']}); "
        f"prompt chars by level {out['prompt_chars_by_level']}; "
        f"skipped (no source) {out['skipped_empty']}; "
        f"deferred parents {out['deferred_parents']}; "
        f"empty returns {out['empty_returns']}"
    )
    if args.yes:
        print(
            f"resume: {out['resumed_communities']} community(ies) reused from the checkpoint "
            f"(no call); {out['stale_communities']} re-summarised because the input changed; "
            f"{out['retried_communities']} re-attempted after a failed call"
        )
    print(
        f"batching: budget {args.max_prompt_chars} chars; "
        f"single calls {out['single_calls']}, map calls {out['map_calls']}, "
        f"reduce calls {out['reduce_calls']}, "
        f"communities summarised map-reduce {out['batched_communities']}, "
        f"passages truncated to fit {out['truncated_texts']}"
    )
    if not args.yes:
        print(
            f"planned leaf level: {out['planned_leaf_prompts']} prompt(s) (single+map), of which "
            f"{out['planned_leaf_batched_communities']} community(ies) need map-reduce (>=1 reduce "
            f"call each). The prompt chars above cover the LEAF level only — a parent's prompt is "
            f"built from its children's summaries, which do not exist until the run happens, so the "
            f"parent levels' spend is NOT estimable from a dry run. Parent calls will be "
            f"{out['deferred_parents']} at most (one per parent that has children)."
        )

    artifact = {
        "document": args.doc_id,
        "resolutions": [lvl.resolution for lvl in hierarchy.levels],
        "modularity": [lvl.q for lvl in hierarchy.levels],
        "nesting": hierarchy.nesting,
        "cost": {
            "total_calls": out["total_calls"],
            "calls_by_level": out["calls_by_level"],
            "prompt_chars_by_level": out["prompt_chars_by_level"],
            "skipped_empty": out["skipped_empty"],
            "deferred_parents": out["deferred_parents"],
            "empty_returns": out["empty_returns"],
            "single_calls": out["single_calls"],
            "map_calls": out["map_calls"],
            "reduce_calls": out["reduce_calls"],
            "batched_communities": out["batched_communities"],
            "truncated_texts": out["truncated_texts"],
            "prompt_chars_total": out["prompt_chars_total"],
            "planned_leaf_prompts": out["planned_leaf_prompts"],
            "leaf_prompt_calls": out["leaf_prompt_calls"],
            "planned_leaf_batched_communities": out["planned_leaf_batched_communities"],
            "resumed_communities": out["resumed_communities"],
            "stale_communities": out["stale_communities"],
            "retried_communities": out["retried_communities"],
            "checkpoint_path": out["checkpoint_path"],
            "max_prompt_chars": args.max_prompt_chars,
            "prompt_chars_cover": "leaf level only on a dry run; parents depend on generated summaries",
        },
        "summaries": {f"{lvl}-{cid}": text for (lvl, cid), text in out["summaries"].items()},
    }
    dest = args.out or DEFAULT_OUT_DIR / f"g2_summaries_{datetime.now():%Y-%m-%d_%H%M}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"artifact: {dest}")

    # The exit criterion is the COUNT, not the absence of an exception (§I25): `call_llm` returns
    # "" on failure, so a run in which every call failed otherwise exits 0 with a full ledger.
    if args.yes and out["empty_returns"]:
        print(
            f"ERROR: {out['empty_returns']} of {out['total_calls']} summarisation call(s) returned "
            f"EMPTY — those communities have no summary. The artifact is written as evidence; do "
            f"NOT treat this run as a build.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
