#!/usr/bin/env python3
"""Phase A3 verifier — count the graph in Memgraph. Do NOT trust the run's own stats.

Why this exists: `graph_builder.build_graph`'s `failed` counter can never increment
(`_extract_concepts` catches every exception and returns an empty concept list), so a dead
LLM produces an EMPTY graph that the script reports as "0 failed". The only honest check is
to count nodes and edges in Memgraph and compare against SQLite.

Checks (all must pass):
  1. the graph now holds 2 documents (old + new);
  2. doc 7ba61432 has 3,796 Chunk nodes == SQLite chunks for that document;
  3. doc 7ba61432 has > 0 Concept nodes and > 0 edges;
  4. concept density >= half the old document's (the mass-silent-failure signature);
  5. the old document is UNTOUCHED (its counts equal the A2 before-snapshot).

Exit 0 = PASS, 1 = FAIL.
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
BEFORE = REPO / "logs/p1/step10/graph_before.json"
OUT = REPO / "logs/p1/step10/graph_after.json"

# The old document's density is the yardstick. Below half of it is the signature of mass
# silent extraction failure, not of a different book.
DENSITY_FLOOR_FRACTION = 0.5


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
    driver.close()

    con = sqlite3.connect(REPO / "data/synapse.db")
    sqlite_chunks = {
        r[0]: r[1]
        for r in con.execute("select document_id, count(*) from chunks group by document_id")
    }
    con.close()

    before = json.loads(BEFORE.read_text()) if BEFORE.exists() else {}

    print("=" * 84)
    print("A3 VERIFIER — Memgraph after the build")
    print("=" * 84)
    for did, d in sorted(docs.items()):
        tag = "NEW" if did == DOC_NEW else ("OLD" if did == DOC_OLD else "??")
        print(f"  [{tag}] {did[:12]}…  chunks={d['chunks']:>5}  pages={d['pages']:>4}  "
              f"concepts={d['concepts']:>5}  {d['title'][:38]}")
    print(f"  totals: {totals}")
    print(f"  SQLite chunks: {sqlite_chunks}")

    # 1. two documents
    if totals["documents"] != 2:
        failures.append(f"expected 2 documents after the build, found {totals['documents']}")
    if DOC_NEW not in docs:
        failures.append(f"{DOC_NEW[:12]}… has no Document node — the build did not write")
        print()
        print("A3 VERDICT: FAIL")
        for f in failures:
            print(f"  !! {f}")
        return 1

    new = docs[DOC_NEW]
    old = docs.get(DOC_OLD, {})

    # 2. chunk count == SQLite
    expected = sqlite_chunks.get(DOC_NEW, 0)
    if new["chunks"] != expected:
        failures.append(
            f"{DOC_NEW[:12]}… has {new['chunks']} Chunk nodes but SQLite holds {expected} chunks "
            "— partial write"
        )

    # 3. concepts and edges exist
    if new["concepts"] <= 0:
        failures.append(f"{DOC_NEW[:12]}… has ZERO concepts — an empty graph reported as success")
    if totals["edges"] <= 0:
        failures.append("the graph has no edges at all")

    # 4. density in family with the old document
    old_density = (old.get("concepts", 0) / old["chunks"]) if old.get("chunks") else None
    new_density = (new["concepts"] / new["chunks"]) if new["chunks"] else 0.0
    print()
    if old_density:
        floor = old_density * DENSITY_FLOOR_FRACTION
        print(f"  concept density: old={old_density:.3f}/chunk  new={new_density:.3f}/chunk  "
              f"(floor {floor:.3f})")
        if new_density < floor:
            failures.append(
                f"concept density {new_density:.3f}/chunk is below half the old document's "
                f"{old_density:.3f} — mass silent extraction failure"
            )
    else:
        print(f"  concept density: new={new_density:.3f}/chunk  (no old doc to compare)")

    # 5. the old document is untouched
    b = before.get("memgraph", {}).get("per_document", {}).get(DOC_OLD)
    if b:
        for key in ("chunks", "pages", "concepts"):
            if old.get(key) != b[key]:
                failures.append(
                    f"the OLD document's {key} changed during the build: {b[key]} -> {old.get(key)}"
                )
        print(f"  old document untouched: chunks={old.get('chunks')} pages={old.get('pages')} "
              f"concepts={old.get('concepts')} (before: chunks={b['chunks']} pages={b['pages']} "
              f"concepts={b['concepts']})")

    OUT.write_text(json.dumps(
        {"memgraph": {"per_document": docs, "totals": totals},
         "sqlite_chunks": sqlite_chunks,
         "density": {"old": old_density, "new": new_density},
         "verdict": "FAIL" if failures else "PASS"}, indent=2))
    print(f"  wrote {OUT.relative_to(REPO)}")

    print()
    print("=" * 84)
    if failures:
        print("A3 VERDICT: FAIL — do not proceed to A4")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 84)
        return 1
    print("A3 VERDICT: PASS — the new document's graph is complete and the old one is untouched")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
