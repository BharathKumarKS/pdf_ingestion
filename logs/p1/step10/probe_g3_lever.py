#!/usr/bin/env python
"""§G3 lever probe — how much does entity resolution actually buy? 2026-10-20.

Why this exists
---------------
The §G plan's G3 verifier 3 says "the share of chunks matching >= 2 distinct concepts
rises ... currently most chunks tie at 1" (§I2). That number is QUERY-SIDE: read
`GraphBuilder.graph_search` (src/pdf_ingestion/graph_builder.py:449-459), a chunk is
ranked by `matched_concepts` = how many of the QUERY's `top_k=8` concepts it mentions.
A chunk's TOTAL concept count is a different quantity, and it is already high (96.9%
mention >= 2), so that reading of the verifier has only 3.1 points of headroom.

This probe measures the thing G3 actually moves, with no LLM and no query embeddings:

  For a near-duplicate group {orbit, Orbit, planetary orbit}, a query that resolves to
  ANY member today retrieves only the chunks mentioning that exact spelling. Merging the
  group unions the chunk sets. The delta is the chunks G3 recovers — i.e. the size of the
  lever §I2 claims is "the bigger lever than ranking".

Also reports the hub list before/after, which is the course's own Lab 1 exercise
("measure how merging them changes the hub list").

Read-only. Run:
    unset PYTHONPATH && uv run python logs/p1/step10/probe_g3_lever.py <document_id>
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

from neo4j import GraphDatabase

_HOST = os.environ.get("MEMGRAPH_HOST", "localhost")
_PORT = os.environ.get("MEMGRAPH_PORT", "7687")
URI = f"bolt://{_HOST}:{_PORT}"
USER = os.environ.get("MEMGRAPH_USER", "memgraph")
PWD = os.environ.get("MEMGRAPH_PASSWORD", "")


def norm(n: str) -> str:
    """Normalise a concept name to a merge key.

    Deliberately conservative, and NOT substring-based — see the report: 809 substring
    pairs exist and most are genuinely distinct concepts ("air" vs "air density").
    """
    n = n.strip().lower()
    n = re.sub(r"\([^)]*\)", "", n)          # drop parentheticals
    n = re.sub(r"^(the|a|an)\s+", "", n)     # leading articles
    # keep unicode word chars: a naive [^a-z0-9 ] collapses every Greek symbol to ""
    n = re.sub(r"[^\w ]+", " ", n, flags=re.UNICODE).replace("_", " ")
    n = re.sub(r"\s+", " ", n).strip()
    if n.endswith("ies"):
        n = n[:-3] + "y"
    elif n.endswith("s") and not n.endswith("ss"):
        n = n[:-1]
    return n


def main() -> int:
    doc = sys.argv[1] if len(sys.argv) > 1 else None
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    with driver.session() as s:
        if doc is None:
            # `.single()` raises when there is more than one Document node; resolve
            # explicitly so an ambiguous graph fails with a clear message instead.
            ids = [r["id"] for r in s.run("MATCH (d:Document) RETURN d.id AS id")]
            if len(ids) != 1:
                print(
                    f"AMBIGUOUS: {len(ids)} Document nodes; pass a document_id as argv[1]",
                    file=sys.stderr,
                )
                return 2
            doc = ids[0]
        # one row per concept name -> the chunks that mention it
        rows = s.run(
            """
            MATCH (c:Chunk)-[:MENTIONS]->(k:Concept)
            WHERE c.document_id = $doc
            RETURN k.name AS name, collect(DISTINCT c.id) AS chunks
            """,
            doc=doc,
        ).data()
        n_chunks_total = s.run(
            "MATCH (c:Chunk) WHERE c.document_id = $doc RETURN count(c) AS n", doc=doc
        ).single()["n"]
    driver.close()

    # build merge groups on the normalised key, keeping only groups with >1 member
    groups: dict[str, list[dict]] = defaultdict(list)
    empty_key = 0
    for r in rows:
        key = norm(r["name"])
        if not key:
            # See the baseline probe: an empty key would merge every such name together.
            empty_key += 1
            continue
        groups[key].append({"name": r["name"], "chunks": set(r["chunks"])})

    # ---- 1. the lever: chunks newly reachable when a group is merged ----------
    lever_rows = []
    union_chunks_all: set[str] = set()
    sum_best_member = 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        union: set[str] = set()
        best = 0
        for m in members:
            union |= m["chunks"]
            best = max(best, len(m["chunks"]))
        newly = len(union) - best          # chunks no single spelling reaches today
        union_chunks_all |= union
        sum_best_member += best
        lever_rows.append({
            "key": key,
            "members": [m["name"] for m in members],
            "chunks_union": len(union),
            "chunks_best_single": best,
            "chunks_newly_reachable": newly,
        })
    lever_rows.sort(key=lambda r: -r["chunks_newly_reachable"])

    # ---- 2. hub list before/after (the course's Lab 1 exercise) --------------
    def hub_list(size: int = 20):
        return [
            {"concept": r["name"], "chunks": len(r["chunks"])}
            for r in sorted(rows, key=lambda r: -len(r["chunks"]))[:size]
        ]

    merged_hubs = [
        {"key": k, "chunks": len(u), "members": len(groups[k])}
        for k, u in sorted(
            ((k, set().union(*[m["chunks"] for m in g])) for k, g in groups.items()),
            key=lambda kv: -len(kv[1]),
        )[:20]
    ]

    out = {
        "document": doc,
        "chunks_total": n_chunks_total,
        "concepts_with_chunks": len(rows),
        "names_skipped_empty_key": empty_key,
        "merge_groups": len(lever_rows),
        "concepts_in_merge_groups": sum(len(r["members"]) for r in lever_rows),
        "lever": {
            "chunks_newly_reachable_total": sum(r["chunks_newly_reachable"] for r in lever_rows),
            "groups_that_gain_nothing": sum(
                1 for r in lever_rows if r["chunks_newly_reachable"] == 0
            ),
            "top_groups_by_gain": lever_rows[:20],
        },
        "hubs_before": hub_list(20),
        "hubs_after_merge": merged_hubs,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
