#!/usr/bin/env python3
"""
Reset Qdrant collections and SQLite before re-ingesting with a new schema.

Run this before re-ingesting when the embedding model or collection schema changes.
Deletes:  knowledge_base, derivative_artifacts, concept_embeddings Qdrant collections
          Document, Chunk, Card, RaptorNode rows in SQLite
Keeps:    visual_knowledge_base (ColPali — schema unchanged)
          PageImage rows in SQLite

Usage:
    uv run python scripts/reset_for_reingest.py
    uv run python scripts/reset_for_reingest.py --dry-run   # show what would be deleted
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from loguru import logger
from rich.console import Console
from rich.prompt import Confirm

console = Console()


def main() -> None:
    p = argparse.ArgumentParser(description="Reset collections and DB before re-ingest")
    p.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = p.parse_args()

    from src.core.config import get_settings
    cfg = get_settings()

    collections_to_delete = [
        cfg.qdrant_collection,    # knowledge_base
        cfg.da_collection,        # derivative_artifacts
        cfg.concept_collection,   # concept_embeddings
    ]
    keep_collections = [cfg.colpali_collection]  # visual_knowledge_base

    console.print("\n[bold red]Reset for Re-ingest[/]")
    console.print(f"\n[bold]Qdrant collections to DELETE:[/]")
    for col in collections_to_delete:
        console.print(f"  [red]✗[/] {col}")
    console.print(f"\n[bold]Qdrant collections to KEEP:[/]")
    for col in keep_collections:
        console.print(f"  [green]✓[/] {col}")
    console.print(f"\n[bold]SQLite tables to CLEAR:[/]")
    for tbl in ["raptor_nodes", "cards", "chunks", "documents"]:
        console.print(f"  [red]✗[/] {tbl}")
    console.print(f"[bold]SQLite tables to KEEP:[/]")
    console.print(f"  [green]✓[/] page_images")

    if args.dry_run:
        console.print("\n[yellow]Dry run — nothing deleted.[/]")
        return

    if not args.yes:
        confirmed = Confirm.ask(
            "\n[bold yellow]This will delete all ingested text data. Continue?[/]"
        )
        if not confirmed:
            console.print("Aborted.")
            return

    # ── Drop Qdrant collections ───────────────────────────────────────────────
    from qdrant_client import QdrantClient

    if cfg.qdrant_url:
        kwargs = {"url": cfg.qdrant_url}
        if cfg.qdrant_api_key:
            kwargs["api_key"] = cfg.qdrant_api_key
        client = QdrantClient(**kwargs)
    elif cfg.qdrant_host:
        client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)
    else:
        client = QdrantClient(path=cfg.qdrant_local_path)

    existing = {c.name for c in client.get_collections().collections}
    for col in collections_to_delete:
        if col in existing:
            client.delete_collection(col)
            console.print(f"[red]Deleted Qdrant collection:[/] {col}")
        else:
            console.print(f"[dim]Skipped (not found):[/] {col}")

    # ── Clear SQLite tables ───────────────────────────────────────────────────
    from sqlmodel import Session, delete as sql_delete
    from src.core.database import Card, Chunk, Document, RaptorNode, get_engine

    engine = get_engine(cfg)
    with Session(engine) as session:
        for model, name in [
            (RaptorNode, "raptor_nodes"),
            (Card,       "cards"),
            (Chunk,      "chunks"),
            (Document,   "documents"),
        ]:
            n = session.exec(sql_delete(model)).rowcount
            console.print(f"[red]Cleared SQLite table:[/] {name} ({n} rows)")
        session.commit()

    console.print("\n[bold green]Reset complete. Ready to re-ingest.[/]")


if __name__ == "__main__":
    main()
