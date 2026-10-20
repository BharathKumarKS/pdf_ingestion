#!/usr/bin/env python3
"""Phase A2 — before-snapshot + one-chunk concept-extraction probe.

Two jobs, both cheap, both before spending ~45-90 min of cluster time:

  1. Snapshot the graph's "before" state (per-document node counts + the
     concept_embeddings point count) to logs/p1/step10/graph_before.json, so the
     change the rebuild makes is measurable rather than asserted.
  2. Call GraphBuilder._extract_concepts on ONE real chunk of the re-ingested
     document. This is the only cheap place to catch a broken LLM before a
     3,796-chunk run: call_llm returns "" on failure and _extract_concepts
     catches every exception, so a dead backend yields an EMPTY graph that
     build_graph reports as "0 failed".

Exit codes: 0 = both checks pass, 1 = a check failed (do not start the build).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"   # the Step 8 re-ingest
DOC_OLD = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"   # the previous ingest
OUT = REPO / "logs/p1/step10/graph_before.json"

failures: list[str] = []


def _one(session, query: str, **params) -> int:
    """Run a COUNT query and return the integer, failing loudly on no row."""
    rec = session.run(query, **params).single()
    if rec is None:
        raise RuntimeError(f"query returned no row: {query}")
    return int(rec["c"])


def snapshot() -> dict:
    from neo4j import GraphDatabase

    from src.core.config import get_settings

    cfg = get_settings()
    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )
    docs: dict[str, dict] = {}
    with driver.session() as s:
        for rec in s.run(
            "MATCH (d:Document) RETURN d.id AS id, d.title AS title"
        ).data():
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
        }
    driver.close()

    # concept_embeddings point count (the 768d lane the graph ranks against, §I12)
    try:
        from qdrant_client import QdrantClient
        qc = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port, timeout=30)
        concept_points = qc.get_collection(cfg.concept_collection).points_count
    except Exception as exc:  # noqa: BLE001
        concept_points = f"unavailable: {type(exc).__name__}"

    return {"memgraph": {"per_document": docs, "totals": totals},
            "concept_embeddings_points": concept_points}


def main() -> int:
    from src.core.config import get_settings
    from src.pdf_ingestion.graph_builder import GraphBuilder

    cfg = get_settings()

    # ── 1. before-snapshot ────────────────────────────────────────────────
    print("=" * 78)
    print("A2.1  before-snapshot")
    print("=" * 78)
    snap = snapshot()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2))
    print(f"  wrote {OUT.relative_to(REPO)}")
    for did, d in snap["memgraph"]["per_document"].items():
        tag = "NEW" if did == DOC_NEW else ("OLD" if did == DOC_OLD else "??")
        print(f"  [{tag}] {did[:12]}…  chunks={d['chunks']:>5}  pages={d['pages']:>4}  "
              f"concepts={d['concepts']:>5}  {d['title'][:40]}")
    print(f"  totals: {snap['memgraph']['totals']}")
    print(f"  concept_embeddings: {snap['concept_embeddings_points']} points")

    docs = snap["memgraph"]["per_document"]
    n_docs = snap["memgraph"]["totals"]["documents"]
    if n_docs != 1 or DOC_OLD not in docs:
        failures.append(
            f"expected exactly 1 document ({DOC_OLD[:12]}…) before the rebuild, found {n_docs}: "
            f"{list(docs)}"
        )
    if DOC_NEW in docs and docs[DOC_NEW]["chunks"]:
        failures.append(
            f"{DOC_NEW[:12]}… already has {docs[DOC_NEW]['chunks']} chunk nodes — a rebuild would "
            "MERGE onto them; confirm this is intended"
        )

    # ── 2. one-chunk concept probe ────────────────────────────────────────
    print()
    print("=" * 78)
    print("A2.2  one-chunk concept-extraction probe (live cluster LLM)")
    print("=" * 78)
    print(f"  llm_backend={cfg.llm_backend}  model={cfg.openai_model}  "
          f"base={cfg.openai_api_base}")

    con = sqlite3.connect(REPO / "data/synapse.db")
    row = con.execute(
        "SELECT text, page_number FROM chunks WHERE document_id=? AND is_active=1 "
        "ORDER BY chunk_index LIMIT 1 OFFSET 100",
        (DOC_NEW,),
    ).fetchone()
    con.close()
    if not row:
        failures.append(f"no chunks found in SQLite for {DOC_NEW}")
        text = None
    else:
        text, page = row
        print(f"  probing a real chunk: {len(text)} chars, page {page}")
        print(f"  text[:200]: {' '.join(text[:200].split())!r}")

    if text:
        g = GraphBuilder(cfg)
        result = g._extract_concepts(text)
        concepts = result.get("concepts", [])
        prereqs = result.get("prerequisites", [])
        names = [c.get("name") for c in concepts if isinstance(c, dict) and c.get("name")]
        print(f"  -> {len(concepts)} concepts, {len(prereqs)} prerequisites")
        for c in concepts[:6]:
            if isinstance(c, dict):
                print(f"       - {c.get('name')!r}  type={c.get('type')!r}")
        if not names:
            failures.append(
                "concept extraction returned ZERO named concepts — the build would produce an "
                "empty graph that build_graph reports as '0 failed'. Do NOT start the build."
            )

    print()
    print("=" * 78)
    if failures:
        print("A2 VERDICT: FAIL — do not start the build")
        for f in failures:
            print(f"  !! {f}")
        return 1
    print("A2 VERDICT: PASS — snapshot written, LLM extracts concepts")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
