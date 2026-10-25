#!/usr/bin/env python
"""C0 — time the late-chunk pass on ~20 real PARENTS, before committing to Shape B.

Why this exists
---------------
Shape B (re-embed the existing chunks, ids preserved, cards + graph reused) is the plan's
recommendation, but its cost is **derived, not measured**: `late_chunk_embedder.py`'s docstring
carries "~48 min and ~13.6 GB of JSON for the whole book, one call per parent", extrapolated from
`test_book.pdf` (19 pages). C0 converts that into a number measured on THIS corpus, on THIS cluster,
before the owner commits to the shape. The plan's gate: if the extrapolated pass exceeds the budget,
stop and re-decide.

⚠️ The unit is PARENTS, not chunks. The late-chunk path issues ONE cluster call per parent,
returning PER-TOKEN vectors, and mean-pools the tokens inside each child's span. Sampling chunks
would understate the pass by roughly the fan-out (341 parents -> 3,796 children, ~11 children each)
and would mis-gate the whole decision.

⚠️ This probe also exercises an alignment contract that was probed for **Qwen3**, not for gemma.
`LateChunkEmbedder._content_tokens` accepts `n_api == n_local` or `n_api == n_local + 1` and RAISES
otherwise — so a gemma tokenizer/endpoint mismatch surfaces here as a hard failure rather than
silently shifting every span by one token. A raise is a RESULT, recorded, not a crashed run.

⚠️ READ-ONLY on the corpus: no writes to any collection, no LLM calls, no re-parse. The only
external traffic is the per-token embed POST and the tokenizer load.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/c0_late_chunk_timing.py [--parents 20]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.chunker import TextChunk  # noqa: E402
from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder  # noqa: E402
from src.pdf_ingestion.models import ParentChunk  # noqa: E402

DOC_PREFIX = "7ba61432"
CORPUS_PARENTS = 341          # measured (rechunk_from_payload_probe.json)
OUT = REPO / "logs" / "p1" / "step10" / "c0_late_chunk_timing.json"


def scroll_all(client, collection: str, doc_prefix: str) -> list[dict]:
    out: list[dict] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, limit=512, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in points:
            pl = p.payload or {}
            if str(pl.get("document_id", "")).startswith(doc_prefix):
                out.append({"id": str(p.id), **pl})
        if offset is None:
            break
    return out


def rebuild(rows: list[dict]) -> tuple[list[ParentChunk], dict[int, list[TextChunk]]]:
    """Parents and their children, from the stored payloads only (no re-parse)."""
    by_parent: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("parent_id") is None:
            continue                      # RAPTOR summary nodes carry no parent_id
        by_parent[int(r["parent_id"])].append(r)

    parents: list[ParentChunk] = []
    kids: dict[int, list[TextChunk]] = {}
    for pid, group in sorted(by_parent.items()):
        group.sort(key=lambda r: int(r["chunk_index"]))
        texts = {r.get("parent_text") for r in group}
        if len(texts) != 1:
            raise ValueError(f"parent {pid} carries {len(texts)} distinct parent_text values")
        parent_text = texts.pop()
        if parent_text is None:
            raise ValueError(f"parent {pid} has no parent_text")
        page_map = {
            int(r["char_start"]): int(r["page_number"])
            for r in group
            if r.get("page_number") is not None and r.get("char_start") is not None
        }
        parents.append(ParentChunk(parent_id=pid, text=parent_text, page_map=page_map))
        kids[pid] = [
            TextChunk(
                chunk_id=str(r["id"]),
                document_id=str(r.get("document_id", "")),
                tenant_id=str(r.get("tenant_id", "global")),
                chunk_index=int(r["chunk_index"]),
                text=str(r["text"]),
                char_start=int(r["char_start"]),
                char_end=int(r["char_end"]),
                token_count=int(r.get("token_count") or 0),
                page_number=r.get("page_number"),
                parent_id=pid,
                parent_text=parent_text,
                is_content=bool(r.get("is_content", True)),
            )
            for r in group
        ]
    return parents, kids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", type=int, default=20)
    args = ap.parse_args()

    cfg = get_settings()
    # workers=1: C0 wants a clean per-parent cost, not a throughput number. Resolved HERE so the
    # printed value is the one the embedder actually gets (printing `cfg`'s 8 next to a
    # single-worker run is a record that disagrees with the run).
    serial_cfg = cfg.model_copy(update={"late_chunk_workers": 1})
    print(f"resolved store   : host {cfg.qdrant_host!r} collection {cfg.qdrant_collection!r}")
    print(f"resolved embedder: {cfg.dense_model!r} dim={cfg.dense_dim} low={cfg.dense_dim_low}")
    print(f"late_chunk       : enabled={serial_cfg.late_chunk_enabled} "
          f"workers={serial_cfg.late_chunk_workers} (forced serial for a clean per-parent cost)")
    if not (cfg.qdrant_host and cfg.qdrant_collection.endswith("knowledge_base_v2")):
        print("ABORT: point this at the cluster's knowledge_base_v2", file=sys.stderr)
        return 2

    from qdrant_client import QdrantClient
    client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)
    rows = scroll_all(client, cfg.qdrant_collection, DOC_PREFIX)
    parents, kids = rebuild(rows)
    total_children = sum(len(v) for v in kids.values())
    print(f"\ncorpus rebuilt   : {len(parents)} parents, {total_children} children "
          f"({total_children / max(1, len(parents)):.2f} children/parent)")

    sample = parents[: args.parents]
    if len(sample) < args.parents:
        print(f"⚠️ only {len(sample)} parents available", file=sys.stderr)

    emb = LateChunkEmbedder(settings=serial_cfg)

    t_tokenizer = time.perf_counter()
    try:
        emb._get_tokenizer()
    except Exception as exc:
        print(f"\nFAIL: the tokenizer for {cfg.dense_model!r} could not be loaded: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        OUT.write_text(json.dumps({
            "stage": "C0", "status": "BLOCKED_ON_TOKENIZER", "dense_model": cfg.dense_model,
            "error": f"{type(exc).__name__}: {exc}", "unit": "parents",
        }, indent=2))
        return 3
    t_tokenizer = time.perf_counter() - t_tokenizer
    print(f"tokenizer load   : {t_tokenizer:.2f}s")

    per_parent: list[dict] = []
    failures: list[dict] = []
    for parent in sample:
        group = kids[parent.parent_id]
        t0 = time.perf_counter()
        try:
            out = emb.embed_parent(parent, group)
        except Exception as exc:
            failures.append({"parent_id": parent.parent_id, "children": len(group),
                             "error": f"{type(exc).__name__}: {exc}"})
            print(f"  parent {parent.parent_id:>4}: FAILED {type(exc).__name__}: {str(exc)[:110]}")
            continue
        dt = time.perf_counter() - t0
        n_tok = emb._offsets(parent.text)
        per_parent.append({
            "parent_id": parent.parent_id, "seconds": round(dt, 3),
            "chars": len(parent.text), "tokens": len(n_tok), "children": len(out),
            "late_chunked": sum(1 for e in out if e.late_chunked),
            "dim": int(out[0].dense_1024.shape[0]) if out else 0,
            "low_dim": int(out[0].dense_64.shape[0]) if out else 0,
        })
        print(f"  parent {parent.parent_id:>4}: {dt:6.2f}s  {len(n_tok):5d} tokens  "
              f"-> {len(out):2d} children")

    secs = [r["seconds"] for r in per_parent]
    report: dict = {
        "stage": "C0", "unit": "parents", "collection": cfg.qdrant_collection,
        "dense_model": cfg.dense_model, "dense_dim": cfg.dense_dim,
        "dense_dim_low": cfg.dense_dim_low,
        "corpus": {"parents": len(parents), "children": total_children,
                   "children_per_parent": round(total_children / max(1, len(parents)), 3)},
        "sampled_parents": len(sample), "succeeded": len(per_parent),
        "failed": failures, "tokenizer_load_seconds": round(t_tokenizer, 3),
        "per_parent": per_parent,
    }
    if secs:
        mean = statistics.fmean(secs)
        p50 = statistics.median(secs)
        p90 = sorted(secs)[min(len(secs) - 1, int(0.9 * len(secs)))]
        tokens = [r["tokens"] for r in per_parent]
        report["timing"] = {
            "mean_s": round(mean, 3), "p50_s": round(p50, 3), "p90_s": round(p90, 3),
            "min_s": round(min(secs), 3), "max_s": round(max(secs), 3),
            "total_s": round(sum(secs), 3),
            # per-token output is the memory story: n_tokens x dim x 4 bytes, per parent
            "mean_tokens_per_parent": round(statistics.fmean(tokens), 1),
            "max_tokens_per_parent": max(tokens),
            "extrapolated_341_parents_min": round(mean * CORPUS_PARENTS / 60, 2),
            "extrapolated_basis": "mean seconds/parent x 341 parents, serial (workers=1)",
        }
        # guards, each able to fail
        report["guards"] = {
            "C0-G1_all_sampled_parents_succeeded": len(per_parent) == len(sample),
            "C0-G2_alignment_held_no_token_mismatch":
                not any("Token alignment" in f["error"] for f in failures),
            "C0-G3_vectors_are_the_configured_width":
                all(r["dim"] == cfg.dense_dim and r["low_dim"] == cfg.dense_dim_low
                    for r in per_parent),
            "C0-G4_every_child_got_a_late_chunked_vector":
                all(r["late_chunked"] == r["children"] for r in per_parent),
        }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")
    if secs:
        print(f"\n--- C0 RESULT (unit: PARENTS) ---")
        print(f"  sampled            : {len(per_parent)}/{len(sample)} parents")
        print(f"  per parent         : mean {report['timing']['mean_s']}s  "
              f"p50 {report['timing']['p50_s']}s  p90 {report['timing']['p90_s']}s")
        print(f"  tokens/parent      : mean {report['timing']['mean_tokens_per_parent']}  "
              f"max {report['timing']['max_tokens_per_parent']}")
        print(f"  EXTRAPOLATED to {CORPUS_PARENTS} parents: "
              f"~{report['timing']['extrapolated_341_parents_min']} min (serial, measured basis)")
        print(f"  guards             : {report['guards']}")
    if failures:
        print(f"\n⚠️ {len(failures)} parent(s) FAILED — recorded, not silently dropped")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
