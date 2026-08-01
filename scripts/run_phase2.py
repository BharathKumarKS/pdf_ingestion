#!/usr/bin/env python3
"""
CLI: generate Phase 2 artifacts (cards + RAPTOR) for an ingested document.

Usage:
    # Run on a specific document
    uv run python scripts/run_phase2.py --doc-id <uuid>

    # Run on ALL documents for a tenant
    uv run python scripts/run_phase2.py --tenant global
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="Generate Phase 2 artifacts (cards + RAPTOR)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--doc-id", help="Document UUID to process")
    g.add_argument("--tenant", help="Process ALL documents for this tenant")
    return p.parse_args()


def run_for_doc(doc_id: str) -> dict:
    from src.pdf_ingestion.store import generate_phase2_artifacts
    return generate_phase2_artifacts(doc_id)


def main():
    args = parse_args()

    from src.core.config import get_settings
    from src.core.database import get_engine
    from src.pdf_ingestion.store import DocumentStore

    cfg   = get_settings()
    store = DocumentStore(cfg)

    if args.doc_id:
        doc_ids = [args.doc_id]
    else:
        docs = store.list_documents(tenant_id=args.tenant)
        doc_ids = [d.id for d in docs]
        if not doc_ids:
            console.print(f"[yellow]No documents found for tenant '{args.tenant}'[/yellow]")
            sys.exit(0)

    table = Table(title="Phase 2 Results", show_lines=True)
    table.add_column("Document ID", style="cyan", no_wrap=True)
    table.add_column("Filename")
    table.add_column("Cards", justify="right")
    table.add_column("RAPTOR nodes", justify="right")
    table.add_column("Levels")

    for doc_id in doc_ids:
        console.print(f"\n[bold]Processing[/bold] {doc_id}…")
        try:
            result = run_for_doc(doc_id)
            table.add_row(
                result["document_id"][:8] + "…",
                result["filename"],
                str(result["cards_generated"]),
                str(result["raptor_nodes"]),
                str(result["raptor_levels"]),
            )
        except Exception as exc:
            console.print(f"[red]  Failed: {exc}[/red]")
            table.add_row(doc_id[:8] + "…", "—", "—", "—", str(exc)[:40])

    console.print(table)


if __name__ == "__main__":
    main()
