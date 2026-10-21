#!/usr/bin/env python3
"""Read-only hit-proof for the late-chunk resume cache (IMPROVEMENTS.md §I19 / §I19a).

**What it does.** Mirrors `ChunkingPipeline.process_pdf` (lines 95-104) — parent chunking,
semantic children, then the late-chunk embedding stage with the resume cache attached — and
**stops before `save_document`**. Nothing is written to Qdrant or SQLite, and if the cache
hits, nothing is sent to the embedding cluster either: the semantic chunker uses chonkie's
local static model (no round-trip), so the embedder is the only network dependency.

**Why it exists.** Attempt 5 logged `Late-chunk cache: 341 hits / 0 misses` and then rejected
all 341 entries, re-embedding the whole 36.1-minute phase (§I19a). The counter increments on
*load*, before `rebuild()` validates the entry, so the summary line reads as success. This
probe counts what actually happened: `embed_parent` invocations.

**The decisive form.** Point the dense lane at a dead port. A full hit needs no cluster at all,
so a success against an unreachable endpoint is the proof; a failure means the cache did not hit.

    SV_EMBED_URL=http://127.0.0.1:9/dead \\
        python logs/p1/step8-run/probe_cache_hit.py

Exit 0 iff every parent came from the cache: `hits == parents`, `misses == 0`, `writes == 0`,
`embed_parent` calls == 0, and no "does not match" rejections. Use `--cache-root` with a scratch
directory to run a cold/warm pair without touching the live cache.

Note it does **not** construct `ChunkingPipeline`, because that builds a `DocumentStore` and
connects to Qdrant (and `_ensure_collection` issues payload-index writes). The cache is built
here with the same two calls `ChunkingPipeline._make_cache` makes, and the resulting directory
is asserted against the key the Step 8 run logged.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only late-chunk cache hit-proof")
    ap.add_argument("--pdf", default="data/base_textbooks/feynman-lectures-on-physics-volume1.pdf")
    ap.add_argument("--expect-parents", type=int, default=341)
    ap.add_argument("--expect-children", type=int, default=3796)
    ap.add_argument("--expect-key", default="2ec020b785942cf2",
                    help="the fingerprint Step 8 logged; pass '' to skip the assertion")
    ap.add_argument("--cache-root", default=None,
                    help="override embed_cache_dir (a scratch dir gives a cold/warm pair)")
    ap.add_argument("--json", default=None, help="write the result JSON here as well")
    args = ap.parse_args()

    from src.core.config import get_settings

    cfg = get_settings()
    if args.cache_root:
        cfg.embed_cache_dir = args.cache_root

    from src.pdf_ingestion.chunker import SemanticChunker
    from src.pdf_ingestion.embed_cache import EmbeddingCache, fingerprint
    from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder
    from src.pdf_ingestion.parent_chunker import ParentChunker

    path = Path(args.pdf)
    if not path.exists():
        print(f"FAIL: PDF not found: {path}")
        return 2

    # Capture the rejections the run would have logged, so the probe can report them as a number.
    warnings: list[str] = []
    logger.add(lambda msg: warnings.append(str(msg)), level="WARNING")

    print("=" * 70)
    print("late-chunk cache hit-proof (read-only — no Qdrant, no SQLite)")
    print(f"  pdf           : {path}")
    print(f"  dense lane    : {cfg.sv_embed_url or '<unset>'}")
    print(f"  cache root    : {cfg.embed_cache_dir}")
    print(f"  fingerprint in: parent_max_tokens={cfg.parent_max_tokens} "
          f"semantic_threshold={cfg.semantic_threshold} min_chunk_tokens={cfg.min_chunk_tokens} "
          f"chunk_size={cfg.chunk_size} chunk_overlap={cfg.chunk_overlap} "
          f"dense_model={cfg.dense_model} late_chunk_enabled={cfg.late_chunk_enabled}")
    print("=" * 70)

    t0 = time.perf_counter()
    doc, parents = ParentChunker(settings=cfg).convert(path)
    t_parse = time.perf_counter() - t0
    print(f"parents  : {len(parents)}  ({t_parse / 60:.1f} min)")

    doc_id = str(uuid.uuid4())  # affects chunk_id only; the cache keys on text + char span
    children = SemanticChunker(settings=cfg).chunk_parents(doc_id, "global", parents)
    print(f"children : {len(children)}")

    key = fingerprint(path, cfg)
    cache = EmbeddingCache(cfg.embed_cache_dir, key)
    print(f"key      : {key}  (dir exists: {cache.directory.exists()})")
    if args.expect_key:
        key_ok = key == args.expect_key
        print(f"key match: {key_ok}  (expected {args.expect_key})")
    else:
        key_ok = True

    embedder = LateChunkEmbedder(settings=cfg)
    calls = {"embed_parent": 0}
    original = embedder.embed_parent

    def counting_embed_parent(parent, children):
        calls["embed_parent"] += 1
        return original(parent, children)

    embedder.embed_parent = counting_embed_parent  # instance attr shadows the method

    t1 = time.perf_counter()
    enriched = embedder.embed_children(parents, children, cache=cache)
    t_embed = time.perf_counter() - t1

    rejected = sum(1 for w in warnings if "does not match" in w)
    other_warnings = [w for w in warnings if "does not match" not in w]

    result = {
        "pdf": str(path),
        "dense_lane": cfg.sv_embed_url,
        "cache_root": str(cfg.embed_cache_dir),
        "key": key,
        "key_expected": args.expect_key,
        "key_match": key_ok,
        "parents": len(parents),
        "children": len(children),
        "enriched": len(enriched),
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
        "cache_writes": cache.writes,
        "embed_parent_calls": calls["embed_parent"],
        "rejected_mismatch": rejected,
        "other_warnings": other_warnings[:10],
        "parse_seconds": round(t_parse, 1),
        "embed_seconds": round(t_embed, 1),
    }

    print("-" * 70)
    for k in ("parents", "children", "enriched", "cache_hits", "cache_misses", "cache_writes",
              "embed_parent_calls", "rejected_mismatch"):
        print(f"  {k:20s} {result[k]}")
    print(f"  embed stage          {t_embed:.1f} s")
    if other_warnings:
        print(f"  other warnings       {len(other_warnings)}: {other_warnings[:3]}")

    ok = (
        len(parents) == args.expect_parents
        and len(children) == args.expect_children
        and len(enriched) == args.expect_children
        and cache.hits == args.expect_parents
        and cache.misses == 0
        and cache.writes == 0
        and calls["embed_parent"] == 0
        and rejected == 0
        and key_ok
    )
    result["verdict"] = "HIT" if ok else "NO HIT"
    print("-" * 70)
    print(f"VERDICT: {result['verdict']}  "
          f"(every parent from cache: {cache.hits}/{len(parents)}, "
          f"embeddings issued: {calls['embed_parent']}, rejected: {rejected})")
    print(json.dumps(result, indent=2))

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2))
        print(f"wrote {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
