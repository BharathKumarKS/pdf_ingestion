#!/usr/bin/env python3
"""A4 after-verifier — the graph must now hold ONLY the re-ingested document.

Counts in Memgraph, not from clean_stale_graph.py's own summary line (the recurring
failure mode in this codebase is a phase that reports success while writing nothing).

Checks (all must pass):
  1. the graph holds exactly 1 document, and it is 7ba61432;
  2. the OLD document (6d55c52b) is gone — 0 Document/Chunk/Page nodes for it;
  3. 7ba61432 has 3,796 Chunk nodes == SQLite chunks for that document;
  4. 7ba61432 has > 0 Concept nodes and the graph has > 0 edges;
  5. concept density >= the 0.774 floor (half the old document's 1.547/chunk).

Writes logs/p1/step10/graph_after_cleanup.json. Exit 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"
DOC_OLD = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"
OUT = REPO / "logs/p1/step10/graph_after_cleanup.json"

DENSITY_FLOOR = 0.774  # half the old document's 7,815/5,051 = 1.547 per chunk


def _one(session, query: str, **params) -> int:
    rec = session.run(query, **params).single()
    if rec is None:
        raise RuntimeError(f"query returned no row: {query}")
    return int(rec["c"])


def main() -> int:
    from neo4j import GraphDatabase

    from src.core.config import get_settings

    cfg = get_settings()
    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )

    failures: list[str] = []
    docs: dict[str, dict] = {}
    with driver.session() as s:
        for rec in s.run("MATCH (d:Document) RETURN d.id AS id, d.title AS title").data():
            did = rec["id"]
            docs[did] = {
                "title": rec["title"],
                "chunks": _one(s, "MATCH (c:Chunk {document_id: $id}) RETURN count(c) AS c", id=did),
                "pages": _one(s, "MATCH (p:Page {document_id: $id}) RETURN count(p) AS c", id=did),
                "concepts": _one(
                    s,
                    "MATCH (c:Chunk {document_id: $id})-[:MENTIONS]->(k:Concept) "
                    "RETURN count(DISTINCT k) AS c",
                    id=did,
                ),
            }
        totals = {
            "documents": _one(s, "MATCH (n:Document) RETURN count(n) AS c"),
            "chunks": _one(s, "MATCH (n:Chunk) RETURN count(n) AS c"),
            "pages": _one(s, "MATCH (n:Page) RETURN count(n) AS c"),
            "concepts": _one(s, "MATCH (n:Concept) RETURN count(n) AS c"),
            "edges": _one(s, "MATCH ()-[r]->() RETURN count(r) AS c"),
        }
        old_chunks = _one(
            s, "MATCH (c:Chunk {document_id: $id}) RETURN count(c) AS c", id=DOC_OLD
        )
        old_pages = _one(
            s, "MATCH (p:Page {document_id: $id}) RETURN count(p) AS c", id=DOC_OLD
        )
    driver.close()

    con = sqlite3.connect(REPO / "data/synapse.db")
    sqlite_chunks = {
        r[0]: r[1]
        for r in con.execute("select document_id, count(*) from chunks group by document_id")
    }
    con.close()

    print("=" * 84)
    print("A4 AFTER-VERIFIER — Memgraph after retiring the old document")
    print("=" * 84)
    for did, d in sorted(docs.items()):
        tag = "NEW" if did == DOC_NEW else ("OLD" if did == DOC_OLD else "??")
        print(f"  [{tag}] {did[:12]}…  chunks={d['chunks']:>5}  pages={d['pages']:>4}  "
              f"concepts={d['concepts']:>5}  {d['title'][:38]}")
    print(f"  totals: {totals}")
    print(f"  SQLite chunks: {sqlite_chunks}")
    print(f"  old doc residue: chunks={old_chunks} pages={old_pages}")

    if totals["documents"] != 1:
        failures.append(f"expected 1 document after the cleanup, found {totals['documents']}")
    if DOC_OLD in docs:
        failures.append(f"{DOC_OLD[:12]}… still has a Document node — cleanup did not run")
    if old_chunks or old_pages:
        failures.append(
            f"{DOC_OLD[:12]}… residue: {old_chunks} chunks, {old_pages} pages still present"
        )

    new = docs.get(DOC_NEW)
    if new is None:
        failures.append(f"{DOC_NEW[:12]}… has no Document node — the cleanup removed the wrong doc")
    else:
        expected = sqlite_chunks.get(DOC_NEW, 0)
        if new["chunks"] != expected:
            failures.append(
                f"{DOC_NEW[:12]}… has {new['chunks']} Chunk nodes but SQLite holds {expected}"
            )
        if new["concepts"] <= 0:
            failures.append(f"{DOC_NEW[:12]}… has ZERO concepts")
        if totals["edges"] <= 0:
            failures.append("the graph has no edges at all")
        density = (new["concepts"] / new["chunks"]) if new["chunks"] else 0.0
        print()
        print(f"  concept density: new={density:.3f}/chunk  (floor {DENSITY_FLOOR:.3f})")
        if density < DENSITY_FLOOR:
            failures.append(f"concept density {density:.3f}/chunk is below the {DENSITY_FLOOR} floor")

    OUT.write_text(json.dumps(
        {"memgraph": {"per_document": docs, "totals": totals},
         "old_doc_residue": {"chunks": old_chunks, "pages": old_pages},
         "sqlite_chunks": sqlite_chunks,
         "verdict": "FAIL" if failures else "PASS"}, indent=2))
    print(f"  wrote {OUT.relative_to(REPO)}")

    print()
    print("=" * 84)
    if failures:
        print("A4 VERDICT: FAIL")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 84)
        return 1
    print("A4 VERDICT: PASS — only 7ba61432 remains; the old document's graph is gone")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
