#!/usr/bin/env python3
"""
Clear ONE document's graph out of Memgraph — the step a graph REBUILD must be preceded by.

WHY THIS EXISTS (and why `clean_stale_graph.py` cannot do it)
`scripts/clean_stale_graph.py` decides *which* documents to delete by asking Qdrant: a
document is stale iff it has no points in the collection. That is the wrong question
before a rebuild — the document being rebuilt (`7ba61432`) **is** the live collection, so
the stale-cleaner reports "Nothing to do — graph matches the vector store" and exits.

It has to be removed anyway, because `build_graph` has **no delete step** and its writes
are `MERGE … ON MATCH SET r.weight = r.weight + 1`. Rebuilding over the existing graph
would therefore
    (a) keep every concept the PREVIOUS extractor produced (the old ones are never
        removed, only added to), and
    (b) **double every `RELATES_TO` weight** — the §I43 duplication class, in the graph.
This script removes the document's graph so the rebuild starts from nothing.

WHAT IT DELETES, per `--doc-id`
    1. its Chunk nodes     (DETACH DELETE, scoped `document_id IN $ids`)
    2. its Page nodes      (DETACH DELETE, scoped `document_id IN $ids`)
    3. its Document node   (DETACH DELETE, scoped `id IN $ids`)
    4. Concept nodes that its chunks mentioned and that **no surviving chunk mentions**
       — i.e. concepts orphaned *by this clear*. A concept another document still
       mentions is never touched.
`DETACH DELETE` clears PART_OF / ON_PAGE / MENTIONS / RELATES_TO / PREREQUISITE_OF.

NOTE ON CYPHER: Memgraph 2.18.1 cannot express orphan detection in one query. All four
single-query forms were probed against the live server on 2026-10-21 and all fail:
`NOT (k)<-[:MENTIONS]-()` → *"Not yet implemented: atom expression"*;
`NOT EXISTS { MATCH … }` and `OPTIONAL MATCH … AS m WHERE m IS NULL` → parse errors.
So orphan detection is two-phase and **by name**, as in `clean_stale_graph.py`.

⚠️ This script does NOT touch Qdrant. `concept_embeddings` accumulates across ingests
and its payload carries no document id, so points whose concept the graph no longer
holds survive here. That is a registered confound (HANDOFF item 3, §G1's ablation),
not a defect of this script — clearing it is a separate decision.

SAFETY
    * dry-run is the DEFAULT; nothing is deleted without `--yes`.
    * a `--doc-id` that is not in the graph is refused (exit 2) rather than silently
      deleting nothing — a typo'd id is the one way to run this and learn nothing.
    * every delete is scoped to the ids you passed. There is no `MATCH (n) DETACH DELETE n`
      anywhere in this file.

Usage:
    uv run python scripts/clear_graph_document.py --doc-id <uuid>            # dry-run (default)
    uv run python scripts/clear_graph_document.py --doc-id <uuid> --yes      # apply
    uv run python scripts/clear_graph_document.py --all --yes                # every document
    uv run python scripts/clear_graph_document.py --doc-id <uuid> --yes \
        --memgraph-host localhost --memgraph-port 7687
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

# Labels and edge types this script reports on. Kept as data so `graph_summary` and the
# before/after tables cannot drift apart.
_NODE_LABELS = ["Document", "Chunk", "Page", "Concept"]
_EDGE_TYPES = ["PART_OF", "ON_PAGE", "MENTIONS", "RELATES_TO", "PREREQUISITE_OF"]


# ── Graph reads ───────────────────────────────────────────────────────────────

def graph_documents(driver) -> list[dict]:
    """Every Document node in the graph, as {id, title, tenant}."""
    with driver.session() as s:
        return s.run(
            "MATCH (d:Document) RETURN d.id AS id, d.title AS title, "
            "d.tenant_id AS tenant ORDER BY title"
        ).data()


def count_nodes(driver, label: str, doc_id: str) -> int:
    """Nodes of `label` carrying `document_id = doc_id` (Chunk/Page)."""
    with driver.session() as s:
        return int(
            s.run(
                f"MATCH (n:{label} {{document_id: $id}}) RETURN count(n) AS c", id=doc_id
            ).single()["c"]
        )


def concept_names_mentioned_by(driver, doc_ids: list[str]) -> set[str]:
    """Concept names reachable from these documents' chunks (the 'touched' set).

    Read BEFORE the delete: once the chunks are gone, nothing remembers which concepts
    this document contributed.
    """
    if not doc_ids:
        return set()
    with driver.session() as s:
        return {
            r["n"]
            for r in s.run(
                "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) "
                "WHERE c.document_id IN $ids RETURN DISTINCT k.name AS n",
                ids=doc_ids,
            ).data()
        }


def concept_names_mentioned_excluding(driver, doc_ids: list[str]) -> set[str]:
    """Concept names that a chunk OUTSIDE these documents still mentions (the 'surviving' set).

    Read BEFORE the delete, and it must be: after the chunks are gone nothing remembers which
    concepts this document contributed, so `touched` could not be computed either. Read this way
    rather than as "all mentions minus touched" — those are not the same set. A concept mentioned
    by BOTH a doomed chunk and a surviving one is in `touched` and must still be in `surviving`;
    subtracting `touched` would orphan it and delete a live document's concept.
    """
    with driver.session() as s:
        return {
            r["n"]
            for r in s.run(
                "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) "
                "WHERE NOT (c.document_id IN $ids) RETURN DISTINCT k.name AS n",
                ids=doc_ids,
            ).data()
        }


def graph_summary(driver) -> dict:
    """Node and edge totals for the whole graph — the before/after evidence."""
    out: dict = {}
    with driver.session() as s:
        for label in _NODE_LABELS:
            out[label] = int(s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"])
        for rel in _EDGE_TYPES:
            out[rel] = int(
                s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c").single()["c"]
            )
    return out


# ── Planning ──────────────────────────────────────────────────────────────────

@dataclass
class ClearPlan:
    """What a clear would delete, computed before anything is deleted."""

    requested: list[str]
    documents: list[dict]                  # the requested docs that ARE in the graph
    chunks: int = 0
    pages: int = 0
    touched_concepts: set[str] = field(default_factory=set)
    surviving_concepts: set[str] = field(default_factory=set)

    @property
    def found_ids(self) -> list[str]:
        return [d["id"] for d in self.documents]

    @property
    def unknown_ids(self) -> list[str]:
        """Requested ids that are not Document nodes — a typo, or the wrong Memgraph."""
        if self.requested == ["*"]:
            return []          # "*" is the wildcard, not a document id to look up
        found = set(self.found_ids)
        return [i for i in self.requested if i not in found]

    @property
    def orphans(self) -> list[str]:
        """Concepts orphaned by this clear: touched here, mentioned by nothing after."""
        return sorted(self.touched_concepts - self.surviving_concepts)


def plan_clear(driver, requested: list[str]) -> ClearPlan:
    """Read the graph and work out exactly what `requested` would remove.

    `requested` of `["*"]` means every document in the graph.
    """
    docs = graph_documents(driver)
    if requested == ["*"]:
        wanted = docs
    else:
        wanted_set = set(requested)
        wanted = [d for d in docs if d["id"] in wanted_set]

    plan = ClearPlan(requested=requested, documents=wanted)
    if not wanted:
        return plan

    ids = plan.found_ids
    plan.chunks = sum(count_nodes(driver, "Chunk", i) for i in ids)
    plan.pages = sum(count_nodes(driver, "Page", i) for i in ids)
    plan.touched_concepts = concept_names_mentioned_by(driver, ids)
    # Read the surviving set scoped to chunks OUTSIDE the doomed documents, before deleting
    # anything — that is what makes the dry-run's orphan count the real one.
    plan.surviving_concepts = concept_names_mentioned_excluding(driver, ids)
    return plan


# ── Applying ──────────────────────────────────────────────────────────────────

def apply_clear(driver, plan: ClearPlan) -> dict:
    """Delete exactly what `plan` describes. Returns the counts that were removed."""
    ids = plan.found_ids
    if not ids:
        return {"documents": 0, "chunks": 0, "pages": 0, "concepts": 0}

    with driver.session() as s:
        s.run("MATCH (c:Chunk) WHERE c.document_id IN $ids DETACH DELETE c", ids=ids)
        s.run("MATCH (p:Page) WHERE p.document_id IN $ids DETACH DELETE p", ids=ids)
        s.run("MATCH (d:Document) WHERE d.id IN $ids DETACH DELETE d", ids=ids)

    orphans = plan.orphans
    if orphans:
        with driver.session() as s:
            s.run(
                "MATCH (k:Concept) WHERE k.name IN $names DETACH DELETE k",
                names=orphans,
            )
    logger.info(
        "Cleared {} document(s), {} chunks, {} pages, {} orphaned concept(s)",
        len(ids), plan.chunks, plan.pages, len(orphans),
    )
    return {
        "documents": len(ids),
        "chunks": plan.chunks,
        "pages": plan.pages,
        "concepts": len(orphans),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None, driver=None) -> int:
    """Returns the process exit code. `driver` is injectable so the guards are testable."""
    p = argparse.ArgumentParser(
        description="Delete one document's graph (Document/Chunk/Page + orphaned Concepts)"
    )
    p.add_argument("--doc-id", action="append", default=[], metavar="DOC_ID",
                   help="Document id to clear (repeatable)")
    p.add_argument("--all", action="store_true",
                   help="Clear EVERY document in the graph (equivalent to --doc-id '*')")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Apply the deletion. Without it this is a dry run.")
    p.add_argument("--memgraph-host", default=None, metavar="HOST",
                   help="Override MEMGRAPH_HOST (e.g. a tunnelled Memgraph)")
    p.add_argument("--memgraph-port", type=int, default=None, help="Override MEMGRAPH_PORT")
    args = p.parse_args(argv)

    if args.all and args.doc_id:
        console.print("[red]--all and --doc-id are mutually exclusive.[/red]")
        return 2
    if not args.all and not args.doc_id:
        console.print("[red]Nothing to do: pass --doc-id <uuid> (repeatable) or --all.[/red]")
        return 2

    from src.core.config import get_settings

    cfg = get_settings()
    if args.memgraph_host:
        cfg.memgraph_host = args.memgraph_host
    if args.memgraph_port:
        cfg.memgraph_port = args.memgraph_port

    console.print("[bold]Synapse — clear a document's graph[/bold]")
    console.print(f"  Memgraph: {cfg.memgraph_host}:{cfg.memgraph_port}")

    if driver is None:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
            auth=(cfg.memgraph_user, cfg.memgraph_password),
        )

    requested = ["*"] if args.all else list(args.doc_id)
    before = graph_summary(driver)
    plan = plan_clear(driver, requested)

    table = Table(title="Documents to clear")
    table.add_column("document_id")
    table.add_column("title")
    table.add_column("tenant")
    table.add_column("chunks", justify="right")
    table.add_column("pages", justify="right")
    for d in plan.documents:
        table.add_row(
            str(d["id"]), str(d.get("title") or ""), str(d.get("tenant") or ""),
            str(count_nodes(driver, "Chunk", d["id"])),
            str(count_nodes(driver, "Page", d["id"])),
        )
    console.print(table)

    if plan.unknown_ids:
        # A typo'd id is the one way to run this and learn nothing. Refuse rather than
        # delete a subset — the caller's intent is unambiguous, its id is not.
        console.print(
            f"\n[bold red]REFUSING TO PROCEED.[/bold red] {len(plan.unknown_ids)} requested "
            f"document id(s) are not Document nodes in this graph:\n"
            f"  {plan.unknown_ids}\n"
            f"  Documents in the graph: {plan.found_ids or '(none)'}\n"
            "Check the id, or check you are pointed at the Memgraph the graph was built in."
        )
        driver.close()
        return 2

    console.print(
        f"\n[bold red]Will delete[/bold red]: {len(plan.found_ids)} document(s), "
        f"{plan.chunks} chunks, {plan.pages} pages, and "
        f"{len(plan.orphans)} of {len(plan.touched_concepts)} concept(s) they mention "
        f"(the other {len(plan.touched_concepts) - len(plan.orphans)} are still mentioned "
        f"by a surviving chunk)."
    )
    if len(plan.found_ids) == len(graph_documents(driver)):
        console.print(
            "[yellow]NOTE: this is EVERY document in the graph — it will be left empty.[/yellow]"
        )

    if not args.yes:
        console.print("[yellow]Dry run — nothing was deleted. Re-run with --yes to apply.[/yellow]")
        driver.close()
        return 0

    removed = apply_clear(driver, plan)
    after = graph_summary(driver)

    summary = Table(title="Graph before → after")
    summary.add_column("")
    summary.add_column("before", justify="right")
    summary.add_column("after", justify="right")
    for key in _NODE_LABELS + _EDGE_TYPES:
        summary.add_row(key, str(before[key]), str(after[key]))
    console.print(summary)

    console.print(
        f"[green]Done.[/green] Removed {removed['documents']} document(s), "
        f"{removed['chunks']} chunks, {removed['pages']} pages, "
        f"{removed['concepts']} orphaned concept(s)."
    )
    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
