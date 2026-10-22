"""
run_phase3.py — generate ColPali visual embeddings + Memgraph concept graph.

Usage
-----
# All documents for a tenant
uv run python scripts/run_phase3.py --tenant global

# One specific document
uv run python scripts/run_phase3.py --doc-id <uuid> --pdf path/to/file.pdf

# All user uploads
uv run python scripts/run_phase3.py --tenant user_abc123
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console
from rich.table import Table

from src.core.config import get_settings
from src.pdf_ingestion.store import DocumentStore, generate_phase3_artifacts

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: ColPali + Memgraph")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tenant", help="Process all documents for this tenant_id")
    group.add_argument("--doc-id", dest="doc_id", help="Process one document by ID")
    parser.add_argument("--pdf", help="Path to the PDF file (required for visual embeddings)")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-run even if ColPali vectors or Memgraph nodes already exist",
    )
    parser.add_argument(
        "--graph-only", action="store_true", dest="graph_only",
        help="Skip ColPali entirely, only build/rebuild the Memgraph concept graph",
    )
    parser.add_argument(
        "--no-resume", action="store_true", dest="no_resume",
        help="Discard the concept-extraction checkpoint and re-extract every chunk "
             "(IMPROVEMENTS.md §I23). The default resumes, which is what makes a multi-hour "
             "build restartable; a chunk whose extraction FAILED is always re-attempted.",
    )
    args = parser.parse_args()

    cfg = get_settings()
    store = DocumentStore(settings=cfg)

    if args.doc_id:
        doc_ids_and_paths = [(args.doc_id, args.pdf)]
    else:
        docs = store.list_documents(tenant_id=args.tenant)
        if not docs:
            console.print(f"[yellow]No documents found for tenant '{args.tenant}'[/yellow]")
            return
        doc_ids_and_paths = [(d.id, None) for d in docs]

    table = Table(title="Phase 3 Results", show_lines=True)
    table.add_column("Filename", style="cyan")
    table.add_column("Visual Vectors", justify="right")
    table.add_column("Concept Nodes", justify="right")
    table.add_column("Failed chunks", justify="right")
    table.add_column("Graph Edges", justify="right")
    table.add_column("Status", justify="center")

    total_failed = 0
    for doc_id, pdf_path in doc_ids_and_paths:
        try:
            result = generate_phase3_artifacts(
                document_id=doc_id,
                pdf_path=pdf_path,
                settings=cfg,
                force=args.force,
                skip_colpali=args.graph_only,
                force_graph=args.graph_only or args.force,
                resume=not args.no_resume,
            )
            gs = result.get("graph_stats", {})
            colpali_err = result.get("colpali_error")
            graph_err   = result.get("graph_error")

            if colpali_err and graph_err:
                status_cell = f"[red]both failed[/red]"
            elif colpali_err:
                status_cell = f"[yellow]colpali failed[/yellow]"
            elif graph_err:
                status_cell = f"[yellow]graph failed[/yellow]"
            else:
                status_cell = "[green]ready[/green]"

            failed_chunks = int(gs.get("failed_chunks", 0) or 0)
            total_failed += failed_chunks
            table.add_row(
                result["filename"],
                str(result["visual_vectors"]),
                str(gs.get("concept_nodes", 0)),
                f"[red]{failed_chunks}[/red]" if failed_chunks else "0",
                str(gs.get("edges", 0)),
                status_cell,
            )
        except Exception as exc:
            table.add_row(doc_id[:12] + "…", "—", "—", "—", "—",
                          f"[red]failed: {exc}[/red]")

    console.print(table)
    if total_failed:
        console.print(
            f"\n[bold red]{total_failed} chunk(s) contributed NO concepts[/bold red] — their "
            f"extraction call failed, so the graph is missing those concepts and an exit code of "
            f"0 does NOT mean a clean build (IMPROVEMENTS.md §I23). Re-run to retry them: a chunk "
            f"whose extraction failed is deliberately not checkpointed as done.\n"
        )


if __name__ == "__main__":
    main()
