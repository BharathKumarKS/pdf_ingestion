#!/usr/bin/env python
"""Read-only §I2 baseline probe for §G3 (entity resolution) — 2026-10-20.

Answers, without mutating anything:
  1. what is in the graph, and for which document
  2. §I2's headline number: the share of chunks that match >= 2 DISTINCT concepts
  3. how much near-duplicate concept material exists (the G3 candidate pool)

Nothing here writes. Run:
    unset PYTHONPATH && uv run python logs/p1/step10/probe_g3_baseline.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

from neo4j import GraphDatabase

_HOST = os.environ.get("MEMGRAPH_HOST", "localhost")
_PORT = os.environ.get("MEMGRAPH_PORT", "7687")
URI = f"bolt://{_HOST}:{_PORT}"


def norm(n: str) -> str:
    """Normalise a concept name to a merge key.

    Module level, and deliberately IDENTICAL to probe_g3_lever.norm — the two probes
    must agree on what counts as the same concept or they measure different things.
    Deliberately conservative, and NOT substring-based: 809 substring pairs exist in
    this graph and most are genuinely distinct concepts ("air" vs "air density").
    """
    n = n.strip().lower()
    n = re.sub(r"\([^)]*\)", "", n)          # drop parentheticals
    n = re.sub(r"^(the|a|an)\s+", "", n)     # leading articles
    # keep unicode letters/digits (physics uses Greek symbols heavily); drop only
    # punctuation. A naive [^a-z0-9 ] collapses every symbol to "".
    n = re.sub(r"[^\w ]+", " ", n, flags=re.UNICODE)
    n = n.replace("_", " ")
    n = re.sub(r"\s+", " ", n).strip()
    if n.endswith("ies"):
        n = n[:-3] + "y"
    elif n.endswith("s") and not n.endswith("ss"):
        n = n[:-1]
    return n
USER = os.environ.get("MEMGRAPH_USER", "memgraph")
PWD = os.environ.get("MEMGRAPH_PASSWORD", "")

DOC = sys.argv[1] if len(sys.argv) > 1 else None


def main() -> int:
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    out: dict = {}
    with driver.session() as s:
        # --- 1. inventory -------------------------------------------------
        # Memgraph has no `db.labels()` / `db.relationshipTypes()` (that is Neo4j's
        # procedure set). Enumerate from the data instead.
        labels = {}
        for lbl in ["Document", "Chunk", "Concept", "Page"]:
            labels[lbl] = s.run(f"MATCH (n:`{lbl}`) RETURN count(n) AS c").single()["c"]
        other = s.run(
            "MATCH (n) WHERE NOT n:Document AND NOT n:Chunk AND NOT n:Concept "
            "AND NOT n:Page RETURN DISTINCT labels(n) AS l"
        )
        labels["_other_label_sets"] = [r["l"] for r in other]
        rels = {}
        for rt in [r["t"] for r in s.run("MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")]:
            rels[rt] = s.run(f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS c").single()["c"]
        docs = [
            dict(r) for r in s.run(
                "MATCH (d:Document) RETURN d.id AS document_id, "
                "d.title AS title, d.subject AS subject, d.tenant_id AS tenant_id"
            )
        ]
        out["inventory"] = {"labels": labels, "relationships": rels, "documents": docs}

        # resolve the document under test
        doc = DOC or (docs[0]["document_id"] if len(docs) == 1 else None)
        if doc is None:
            print(json.dumps(out, indent=2))
            print("\nAMBIGUOUS: pass a document_id as argv[1]", file=sys.stderr)
            return 2
        out["document_under_test"] = doc

        # --- 2. §I2: concepts per chunk ----------------------------------
        # distinct concepts each chunk mentions, for this document
        per_chunk = [
            r["k"] for r in s.run(
                """
                MATCH (c:Chunk)-[:MENTIONS]->(k:Concept)
                WHERE c.document_id = $doc
                RETURN c.id AS chunk_id, count(DISTINCT k) AS k
                """,
                doc=doc,
            )
        ]
        n_chunks = len(per_chunk)
        hist = Counter(per_chunk)
        ge2 = sum(v for k, v in hist.items() if k >= 2)
        ge3 = sum(v for k, v in hist.items() if k >= 3)
        out["i2_concepts_per_chunk"] = {
            "chunks_with_any_concept": n_chunks,
            "histogram": {str(k): hist[k] for k in sorted(hist)},
            "chunks_ge_2_distinct_concepts": ge2,
            "share_ge_2": round(ge2 / n_chunks, 4) if n_chunks else None,
            "chunks_ge_3_distinct_concepts": ge3,
            "share_ge_3": round(ge3 / n_chunks, 4) if n_chunks else None,
            "mean_concepts_per_chunk": round(sum(per_chunk) / n_chunks, 4) if n_chunks else None,
        }

        # distinct concepts actually mentioned by this document's chunks
        distinct = s.run(
            """
            MATCH (c:Chunk)-[:MENTIONS]->(k:Concept)
            WHERE c.document_id = $doc
            RETURN count(DISTINCT k) AS n
            """,
            doc=doc,
        ).single()["n"]
        out["distinct_concepts_mentioned"] = distinct

        # --- 3. G3 candidate pool: near-duplicate names -------------------
        names = [r["name"] for r in s.run(
            """
            MATCH (c:Chunk)-[:MENTIONS]->(k:Concept)
            WHERE c.document_id = $doc
            RETURN DISTINCT k.name AS name
            """,
            doc=doc,
        )]

    driver.close()

    by_norm: dict[str, list[str]] = defaultdict(list)
    empty_key = 0
    for n in names:
        key = norm(n)
        if not key:
            # A name that normalises to "" (pure punctuation, or a bare parenthetical)
            # would otherwise be merged with every other such name. Skip and count it.
            empty_key += 1
            continue
        by_norm[key].append(n)
    collisions = {k: v for k, v in by_norm.items() if len(v) > 1}
    # also: normalised name that is a strict substring of another normalised name
    norms = sorted(by_norm)
    substring = {}
    for i, a in enumerate(norms):
        for b in norms[i + 1:]:
            if a and b.startswith(a + " "):
                substring.setdefault(a, []).append(b)

    out["g3_candidates"] = {
        "distinct_names": len(names),
        "names_skipped_empty_key": empty_key,
        "normalised_keys": len(by_norm),
        "collision_groups": len(collisions),
        "names_in_collision_groups": sum(len(v) for v in collisions.values()),
        "examples_collisions": dict(list(sorted(collisions.items()))[:15]),
        "substring_pairs": len(substring),
        "examples_substring": dict(list(sorted(substring.items()))[:15]),
    }

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
