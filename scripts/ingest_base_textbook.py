#!/usr/bin/env python3
"""
Admin script: ingest the base textbook into the global knowledge base.

Usage:
    uv run python scripts/ingest_base_textbook.py --pdf data/base_textbooks/textbook.pdf

The base textbook is stored with:
    tenant_id       = "global"
    source_type     = "base_textbook"
    is_global_baseline = True

This script is NOT exposed to end users. Run it once before launching the app.
Re-run it with --reindex to bump the version and ingest an updated edition.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest base textbook into global KB")
    parser.add_argument("--pdf",      required=True, help="Path to the base textbook PDF")
    parser.add_argument("--title",    default=None,  help="Textbook title")
    parser.add_argument("--subject",  default=None,  help="Subject / domain")
    parser.add_argument("--grade",    default=None,  help="Target grade level")
    parser.add_argument("--reindex",  action="store_true", help="Force re-ingestion even if already stored")
    return parser.parse_args()


def main():
    args = parse_args()
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        console.print(f"[red]PDF not found: {pdf_path}[/red]")
        sys.exit(1)

    from src.core.config import get_settings
    from src.core.database import get_engine, get_qdrant
    from src.pdf_ingestion.store import DocumentStore, ingest_pdf

    cfg = get_settings()
    cfg.ensure_dirs()

    # Check if already ingested (skip unless --reindex)
    if not args.reindex:
        store = DocumentStore(cfg)
        existing = store.list_documents(tenant_id=cfg.global_tenant_id)
        if any(d.filename == pdf_path.name for d in existing):
            console.print(
                Panel(
                    f"[yellow]'{pdf_path.name}' already ingested. Use --reindex to force.[/yellow]",
                    title="Skipped",
                )
            )
            return

    console.print(
        Panel(
            f"[bold cyan]Ingesting base textbook[/bold cyan]\n"
            f"File    : {pdf_path}\n"
            f"Title   : {args.title or 'auto-detect'}\n"
            f"Subject : {args.subject or 'unset'}\n"
            f"Grade   : {args.grade or 'unset'}",
            title="Synapse — Base Textbook Ingestion",
        )
    )

    result = ingest_pdf(
        pdf_path=str(pdf_path),
        tenant_id=cfg.global_tenant_id,
        source_type="base_textbook",
        is_global_baseline=True,
        extra_meta={
            "title":       args.title,
            "subject":     args.subject,
            "grade_level": args.grade,
        },
        settings=cfg,
    )

    console.print(
        Panel(
            f"[green]✓ Ingestion complete[/green]\n"
            f"Document ID : {result['document_id']}\n"
            f"Pages       : {result['page_count']}\n"
            f"Chunks      : {result['chunk_count']}\n"
            f"Tenant      : {result['tenant_id']}",
            title="Success",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
