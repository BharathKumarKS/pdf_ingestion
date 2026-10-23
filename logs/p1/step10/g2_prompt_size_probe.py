#!/usr/bin/env python
"""§G2 pre-flight — the LEAF PROMPT SIZE distribution, before the spend.

Why this exists
---------------
`summarize_communities` joins the FULL text of every chunk behind a leaf community into one prompt
(V6). That is the right thing to summarise from, but it makes the prompt size an uncontrolled
variable: nothing caps how many chunks a leaf community can hold, so one community with a hundred
concepts could produce a prompt far past the model's context — and a server-side truncation is
silent (the summary comes back, built on the first N tokens of the passage set).

`--max-chunks` exists as the cost control but its value has to be chosen from a measurement, not a
guess. This probe measures it: the same leaf loop the builder runs, with no LLM call, reporting the
per-leaf prompt-char distribution so a cap can be set deliberately.

    unset PYTHONPATH && uv run python logs/p1/step10/g2_prompt_size_probe.py \
        --doc-id 7ba61432-c5e0-416d-aecf-25a232523481 --out logs/p1/step10/g2_prompt_sizes.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_memgraph  # noqa: E402
from src.pdf_ingestion.community_summaries import (  # noqa: E402
    LEAF_PROMPT,
    build_hierarchy,
    read_concept_chunks,
    read_concept_graph,
)

# Rough char/token ratio for the served tokenizer's English text; used only to express the measured
# chars in the units a context limit is stated in. Labelled as an approximation in the artifact.
CHARS_PER_TOKEN = 4.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    cfg = get_settings()
    driver = get_memgraph(cfg)
    if driver is None:
        print("ERROR: Memgraph driver unavailable", file=sys.stderr)
        return 2

    with driver.session() as session:
        g = read_concept_graph(session, args.doc_id)
        concept_chunks = read_concept_chunks(session, args.doc_id)

    hierarchy = build_hierarchy(g, seed=args.seed)
    leaves = hierarchy.levels[0]

    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine

    rows: list[dict] = []
    missing_chunk_ids = 0
    with Session(get_engine(cfg)) as session:
        for cid, members in enumerate(leaves.communities):
            ids = sorted({c for concept in members for c in concept_chunks.get(concept, [])})
            texts = []
            if ids:
                found = session.exec(select(Chunk).where(Chunk.id.in_(ids))).all()  # type: ignore[attr-defined]
                by_id = {c.id: c.text for c in found}
                missing_chunk_ids += len(ids) - len(by_id)
                texts = [by_id[i] for i in ids if i in by_id]
            body = "\n\n---\n\n".join(texts)
            rows.append({
                "community": cid,
                "concepts": len(members),
                "chunks": len(ids),
                "chunks_found": len(texts),
                "body_chars": len(body),
                "prompt_chars": len(LEAF_PROMPT.format(body=body)) if body.strip() else 0,
            })

    live = [r for r in rows if r["prompt_chars"] > 0]
    sizes = sorted(r["prompt_chars"] for r in live)

    def pct(p: float) -> int:
        if not sizes:
            return 0
        return sizes[min(len(sizes) - 1, int(round(p / 100 * (len(sizes) - 1))))]

    summary = {
        "document": args.doc_id,
        "seed": args.seed,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "leaf_communities": len(leaves.communities),
        "leaves_with_source": len(live),
        "leaves_without_source": len(rows) - len(live),
        "chunk_ids_not_in_sqlite": missing_chunk_ids,
        "prompt_chars": {
            "total": sum(sizes),
            "min": sizes[0] if sizes else 0,
            "p50": pct(50),
            "p90": pct(90),
            "p95": pct(95),
            "p99": pct(99),
            "max": sizes[-1] if sizes else 0,
            "mean": round(statistics.fmean(sizes), 1) if sizes else 0,
        },
        "approx_tokens_chars_per_token": CHARS_PER_TOKEN,
        "approx_tokens_max_prompt": round((sizes[-1] if sizes else 0) / CHARS_PER_TOKEN),
        "top10_largest_leaves": sorted(live, key=lambda r: -r["prompt_chars"])[:10],
        "over_budget": {
            str(b): {
                "leaves": sum(1 for s in sizes if s > b),
                "share_of_leaves": round(sum(1 for s in sizes if s > b) / len(sizes), 4) if sizes else 0,
                "chars_in_them": sum(s for s in sizes if s > b),
                "share_of_all_chars": round(sum(s for s in sizes if s > b) / sum(sizes), 4) if sizes else 0,
            }
            for b in (10000, 20000, 40000, 60000, 90000, 120000)
        },
        "leaves": sorted(rows, key=lambda r: -r["prompt_chars"]),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
