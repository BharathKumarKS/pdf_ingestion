#!/usr/bin/env python3
"""
Phase A: Index derivative artifacts (cards) into the `derivative_artifacts` Qdrant collection.

Embeds definition, formula, and question cards from SQLite and upserts them with
source_page_numbers in the payload. Chunks from non-chapter pages (preface, bibliography,
index, TOC) are skipped via keyword filtering.

Usage:
  uv run python scripts/index_derivative_artifacts.py
  uv run python scripts/index_derivative_artifacts.py --tenant global
  uv run python scripts/index_derivative_artifacts.py --doc-id <uuid>   # single document
  uv run python scripts/index_derivative_artifacts.py --clear            # drop and re-index all
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

console = Console()

# Card types to include in the DA retrieval lane
DA_CARD_TYPES = ["definition", "formula", "question", "factoid"]

# Keywords that identify non-chapter content (checked in first 500 chars of chunk text)
NON_CHAPTER_KEYWORDS = [
    "table of contents",
    "## preface",
    "\npreface\n",
    "## bibliography",
    "bibliography\n",
    "## subject index",
    "## index\n",
    "## acknowledgment",
    "## references\n",
    "list of figures",
    "list of tables",
]


def _is_chapter_chunk(text: str) -> bool:
    """Return True if chunk text looks like it's from a chapter (not front/back matter)."""
    sample = text.lower()[:500]
    return not any(kw in sample for kw in NON_CHAPTER_KEYWORDS)


def _card_embed_text(card_type: str, title: str, content: str, answer: str | None) -> str:
    """Build the text to embed for each card type."""
    if card_type == "question":
        base = f"{content}"
        return f"{base}\n{answer}" if answer else base
    return f"{title}: {content}"


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Index derivative artifacts into Qdrant")
    p.add_argument("--tenant",  default=None, help="Tenant ID to index (default: all tenants)")
    p.add_argument("--doc-id",  default=None, help="Single document UUID to index")
    p.add_argument("--clear",   action="store_true", help="Delete all DA vectors and re-index")
    p.add_argument("--batch",   type=int, default=32, help="Embedding batch size")
    args = p.parse_args()

    from src.core.config import get_settings
    from src.core.database import Card, Chunk, get_engine, get_qdrant
    from src.pdf_ingestion.embedder import get_embedder
    from sqlmodel import Session, select
    from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

    cfg     = get_settings()
    engine  = get_engine(cfg)
    qdrant  = get_qdrant(cfg)          # also creates da_collection if absent
    embedder = get_embedder(cfg)

    console.print(f"\n[bold blue]Phase A — Derivative Artifact Indexing[/]")
    console.print(f"  Collection : [cyan]{cfg.da_collection}[/]")
    console.print(f"  Card types : [cyan]{DA_CARD_TYPES}[/]")
    console.print(f"  Tenant     : [cyan]{args.tenant or 'all'}[/]")

    if args.clear:
        qdrant.delete_collection(cfg.da_collection)
        from src.core.database import _ensure_da_collection
        _ensure_da_collection(qdrant, cfg)
        console.print("[yellow]  Cleared existing DA vectors.[/]")

    # ── Fetch cards from SQLite ───────────────────────────────────────────────
    with Session(engine) as session:
        stmt = (
            select(Card, Chunk)
            .join(Chunk, Card.chunk_id == Chunk.id)
            .where(Card.card_type.in_(DA_CARD_TYPES))
            .where(Card.is_active == True)
        )
        if args.doc_id:
            stmt = stmt.where(Card.document_id == args.doc_id)
        if args.tenant:
            stmt = stmt.where(Card.tenant_id == args.tenant)

        rows = session.exec(stmt).all()

    console.print(f"  Cards found: [cyan]{len(rows)}[/] (before chapter filter)")

    # ── Filter non-chapter chunks ────────────────────────────────────────────
    filtered = [(card, chunk) for card, chunk in rows if _is_chapter_chunk(chunk.text)]
    skipped  = len(rows) - len(filtered)
    console.print(f"  After filter: [green]{len(filtered)}[/] kept, [yellow]{skipped}[/] skipped (non-chapter)")

    if not filtered:
        console.print("[red]No cards to index.[/]")
        return

    # ── Embed and upsert in batches ──────────────────────────────────────────
    points: list[PointStruct] = []
    upserted = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding cards...", total=len(filtered))

        batch_texts: list[str]  = []
        batch_meta:  list[tuple] = []  # (card, chunk)

        def flush_batch() -> None:
            nonlocal upserted
            if not batch_texts:
                return
            vecs = [embedder.embed_query(t) for t in batch_texts]
            for vec, (card, chunk) in zip(vecs, batch_meta):
                page_numbers = [chunk.page_number] if chunk.page_number is not None else []
                embed_text = _card_embed_text(
                    card.card_type, card.title, card.content, card.answer
                )
                points.append(PointStruct(
                    id=card.id,
                    vector=vec,
                    payload={
                        "card_id":            card.id,
                        "chunk_id":           card.chunk_id,
                        "document_id":        card.document_id,
                        "tenant_id":          card.tenant_id,
                        "card_type":          card.card_type,
                        "title":              card.title,
                        "text":               embed_text,
                        "source_page_numbers": page_numbers,
                        "source_type":        "derivative_artifact",
                    },
                ))
            batch_texts.clear()
            batch_meta.clear()

        for card, chunk in filtered:
            embed_text = _card_embed_text(
                card.card_type, card.title, card.content, card.answer
            )
            batch_texts.append(embed_text)
            batch_meta.append((card, chunk))
            progress.advance(task)

            if len(batch_texts) >= args.batch:
                flush_batch()

        flush_batch()

    # Upsert all points to Qdrant
    batch_size = 256
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console,
    ) as progress:
        task = progress.add_task("Upserting to Qdrant...", total=len(points))
        for i in range(0, len(points), batch_size):
            qdrant.upsert(
                collection_name=cfg.da_collection,
                points=points[i : i + batch_size],
            )
            upserted += len(points[i : i + batch_size])
            progress.advance(task, len(points[i : i + batch_size]))

    # ── Summary table ────────────────────────────────────────────────────────
    by_type: dict[str, int] = {}
    for card, _ in filtered:
        by_type[card.card_type] = by_type.get(card.card_type, 0) + 1

    table = Table(title="DA Indexing Summary")
    table.add_column("Card Type")
    table.add_column("Count", justify="right")
    for ct, n in sorted(by_type.items()):
        table.add_row(ct, str(n))
    table.add_row("[bold]Total[/]", f"[bold]{upserted}[/]")
    console.print(table)
    console.print(f"\n[green]Done![/] {upserted} vectors in '{cfg.da_collection}'.")
    console.print(
        "\nNext: run the evaluation to measure Phase A lift:\n"
        "  uv run python scripts/evaluate_rag.py --retrieval-only --skip-visual --run-name phase_a"
    )


if __name__ == "__main__":
    main()
