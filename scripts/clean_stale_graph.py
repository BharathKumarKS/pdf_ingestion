#!/usr/bin/env python3
"""
Remove knowledge-graph documents that no longer exist in the vector store.

WHY THIS EXISTS
Every re-ingest mints a NEW document_id. `run_phase3.py` builds the graph for the
new document but never removes the previous one, so Memgraph accumulates a full
retired copy per ingest (stage 1 on Feynman Vol 1 held 5,048 stale chunks from one
retired ingest on top of 5,051 live ones — 50.3% of all chunk ids dangled).

This corrupts the multihop lane, because `GraphBuilder.graph_search` filters on
`c.tenant_id IN [$tenant_id, 'global']` and NOT on `document_id`: retired chunks are
returned as graph hits and then fail to resolve against Qdrant. Worse, `Concept`
nodes are merged BY NAME, so stale MENTIONS/RELATES_TO edges also contaminate the
live document's traversal.

SOURCE OF TRUTH
Qdrant is authoritative: a Document is stale iff its id has no points in
`knowledge_base`. We never infer staleness from timestamps.

WHAT IT DELETES, per stale document
    1. its Chunk nodes            (DETACH DELETE)
    2. its Page nodes             (DETACH DELETE)
    3. the Document node          (DETACH DELETE)
    4. Concept nodes that the stale chunks mentioned and that nothing mentions
       afterwards — i.e. concepts orphaned *by this cleanup*. Concepts still
       referenced by surviving chunks are never touched.
Relies on DETACH DELETE to clear PART_OF / ON_PAGE / MENTIONS / RELATES_TO /
PREREQUISITE_OF edges automatically.

NOTE ON CYPHER: Memgraph does not implement the `(k)<-[:MENTIONS]-()` atom pattern
("Not yet implemented"), so orphan detection is done in two phases and by name.

Usage:
    uv run python scripts/clean_stale_graph.py --dry-run     # report only (default)
    uv run python scripts/clean_stale_graph.py --yes         # apply
    uv run python scripts/clean_stale_graph.py --keep-doc <id> --yes
    uv run python scripts/clean_stale_graph.py --tenant global --yes
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from loguru import logger
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

console = Console()

# Batch size when paging Qdrant for live document ids.
SCROLL_BATCH = 1000


def _live_document_ids(cfg) -> set[str]:
    """Document ids that still have vectors in the collection — the source of truth."""
    from qdrant_client import QdrantClient

    kwargs: dict = {"timeout": 60}
    if cfg.qdrant_url:
        kwargs.update(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
    elif cfg.qdrant_host:
        kwargs.update(host=cfg.qdrant_host, port=cfg.qdrant_port)
    else:
        kwargs.update(path=cfg.qdrant_local_path)

    client = QdrantClient(**kwargs)
    ids: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            cfg.qdrant_collection,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=["document_id"],
            with_vectors=False,
        )
        for p in points:
            doc_id = (p.payload or {}).get("document_id")
            if doc_id:
                ids.add(str(doc_id))
        if offset is None:
            break
    client.close()
    return ids


def _graph_documents(driver) -> list[dict]:
    with driver.session() as s:
        return s.run(
            "MATCH (d:Document) RETURN d.id AS id, d.title AS title, "
            "d.tenant_id AS tenant ORDER BY title"
        ).data()


def _count(driver, label: str, doc_id: str) -> int:
    with driver.session() as s:
        return s.run(
            f"MATCH (n:{label} {{document_id: $id}}) RETURN count(n) AS c", id=doc_id
        ).single()["c"]


def _concept_names_for_chunks(driver, label: str, doc_ids: list[str]) -> set[str]:
    """Concept names reachable from the given document's chunks."""
    if not doc_ids:
        return set()
    with driver.session() as s:
        return {
            r["n"]
            for r in s.run(
                f"MATCH (c:{label})-[:MENTIONS]->(k:Concept) "
                "WHERE c.document_id IN $ids RETURN DISTINCT k.name AS n",
                ids=doc_ids,
            ).data()
        }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Delete knowledge-graph documents with no vectors in Qdrant"
    )
    p.add_argument("--dry-run", action="store_true", help="Report only; delete nothing")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p.add_argument(
        "--keep-doc",
        action="append",
        default=[],
        metavar="DOC_ID",
        help="Document id to keep even though it has no vectors (repeatable)",
    )
    p.add_argument("--tenant", default=None, help="Only consider documents in this tenant")
    p.add_argument("--qdrant-host", default=None, metavar="HOST",
                   help="Override QDRANT_HOST (e.g. 10.0.10.65 for the cluster index)")
    p.add_argument("--qdrant-port", type=int, default=None, help="Override QDRANT_PORT")
    p.add_argument("--qdrant-url", default=None, help="Override QDRANT_URL (Qdrant Cloud)")
    p.add_argument("--force", action="store_true",
                   help="Allow deletion when stale outnumber live (usually the WRONG Qdrant)")
    args = p.parse_args()

    from src.core.config import get_settings

    cfg = get_settings()

    # Point the liveness check at the SAME index the graph was built from. Getting
    # this wrong is destructive: a mismatched Qdrant makes every real document look
    # stale, and the run wipes the graph.
    if args.qdrant_url:
        cfg.qdrant_url = args.qdrant_url
    if args.qdrant_host:
        cfg.qdrant_host = args.qdrant_host
        cfg.qdrant_url = ""  # explicit host override beats an env-provided cloud URL
        if args.qdrant_port:
            cfg.qdrant_port = args.qdrant_port
    console.print("[bold]Synapse — stale graph cleanup[/bold]")
    console.print(f"  Qdrant : {cfg.qdrant_url or cfg.qdrant_host or cfg.qdrant_local_path}")
    console.print(f"  Memgraph: {cfg.memgraph_host}:{cfg.memgraph_port}")

    live = _live_document_ids(cfg)
    logger.info("Qdrant holds {} live document id(s)", len(live))

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )

    docs = _graph_documents(driver)
    if args.tenant:
        docs = [d for d in docs if d.get("tenant") == args.tenant]

    keep = set(args.keep_doc)
    stale = [d for d in docs if d["id"] not in live and d["id"] not in keep]

    table = Table(title="Graph documents")
    table.add_column("document_id")
    table.add_column("title")
    table.add_column("tenant")
    table.add_column("chunks", justify="right")
    table.add_column("verdict")
    for d in docs:
        n = _count(driver, "Chunk", d["id"])
        if d["id"] in live:
            verdict = "[green]keep (has vectors)[/green]"
        elif d["id"] in keep:
            verdict = "[cyan]keep (--keep-doc)[/cyan]"
        else:
            verdict = "[red]STALE — delete[/red]"
        table.add_row(str(d["id"]), str(d.get("title") or ""), str(d.get("tenant") or ""), str(n), verdict)
    console.print(table)

    if not stale:
        console.print("[green]Nothing to do — graph matches the vector store.[/green]")
        driver.close()
        return

    stale_ids = [d["id"] for d in stale]

    # SAFETY GUARD. The precise signature of "pointed at the wrong Qdrant" is ZERO
    # overlap between the graph's document ids and Qdrant's live ids — i.e. not one
    # document in the graph has vectors. A count comparison (stale > live) is too
    # naive: a graph with a single live document legitimately has more stale ones.
    # Seen in practice: the laptop's Mode A index held 5fcc9006 while the graph held
    # 5d57a020/b2d9fb56/6d55c52b — no overlap at all, and proceeding would have
    # deleted the live document along with the stale ones.
    graph_ids = {d["id"] for d in docs}
    no_overlap = bool(docs) and not (graph_ids & live)
    if no_overlap and not args.force and not args.dry_run:
        console.print(
            f"\n[bold red]REFUSING TO PROCEED.[/bold red] "
            f"None of the {len(graph_ids)} document(s) in the graph have vectors in "
            f"Qdrant.\n"
            f"  Live ids in Qdrant : {sorted(live) or '(none)'}\n"
            f"  Graph documents    : {sorted(graph_ids)}\n"
            "Not one graph document is backed by the index, which means this run is "
            "pointed at a DIFFERENT Qdrant than the one the graph was built from — "
            "proceeding would delete every live chunk.\n"
            "  → Check with:  --qdrant-host/--qdrant-url, or --dry-run to inspect.\n"
            "  → Override deliberately with --force only if you are certain."
        )
        driver.close()
        sys.exit(2)

    total_chunks = sum(_count(driver, "Chunk", i) for i in stale_ids)
    total_pages = sum(_count(driver, "Page", i) for i in stale_ids)
    # concepts touched by the stale docs, so we can scope orphan removal precisely
    touched = _concept_names_for_chunks(driver, "Chunk", stale_ids)

    if no_overlap:
        console.print(
            "\n[bold red]WARNING: no graph document has vectors in Qdrant.[/bold red] "
            "That usually means this run points at a Qdrant that did not build this "
            "graph — deletion will be REFUSED unless --force is passed."
        )

    console.print(
        f"\n[bold red]Will delete[/bold red]: {len(stale_ids)} document(s), "
        f"{total_chunks} chunks, {total_pages} pages, "
        f"and any of {len(touched)} touched concepts left unreferenced."
    )

    if args.dry_run:
        console.print("[yellow]--dry-run: nothing was deleted.[/yellow]")
        driver.close()
        return

    if not args.yes and not Confirm.ask("Proceed with deletion?", default=False):
        console.print("Aborted.")
        driver.close()
        return

    if stale_ids:
        with driver.session() as s:
            s.run(
                "MATCH (c:Chunk) WHERE c.document_id IN $ids DETACH DELETE c", ids=stale_ids
            )
            s.run(
                "MATCH (p:Page) WHERE p.document_id IN $ids DETACH DELETE p", ids=stale_ids
            )
            s.run("MATCH (d:Document) WHERE d.id IN $ids DETACH DELETE d", ids=stale_ids)
        logger.info("Deleted {} stale document(s) and their chunks/pages", len(stale_ids))

    # Phase 2: concepts the stale chunks mentioned that nothing mentions now.
    # (Memgraph cannot express `(k)<-[:MENTIONS]-()`, so this is done by name.)
    with driver.session() as s:
        surviving = {
            r["n"]
            for r in s.run(
                "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) RETURN DISTINCT k.name AS n"
            ).data()
        }
    orphans = touched - surviving
    if orphans:
        with driver.session() as s:
            s.run("MATCH (k:Concept) WHERE k.name IN $names DETACH DELETE k", names=sorted(orphans))
        logger.info("Deleted {} orphaned concept(s)", len(orphans))
    else:
        logger.info("No orphaned concepts to delete")

    console.print(
        f"[green]Done.[/green] Removed {len(stale_ids)} document(s), "
        f"{total_chunks} chunks, {total_pages} pages, {len(orphans)} orphaned concepts."
    )
    driver.close()


if __name__ == "__main__":
    main()
