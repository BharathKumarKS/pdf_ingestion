#!/usr/bin/env python3
"""
Calibration helper — run this on the machine with Feynman ingested.
For each non-visual query in eval_queries.json, it retrieves the top-10
chunks and prints the page numbers so you can update relevant_pages.

Usage:
  uv run python scripts/calibrate_eval_pages.py
  uv run python scripts/calibrate_eval_pages.py --query-file data/eval_queries.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from rich.console import Console
from rich.table import Table

console = Console()


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--query-file", default="data/eval_queries.json")
    p.add_argument("--tenant",     default="global")
    p.add_argument("--limit",      type=int, default=10)
    args = p.parse_args()

    from src.core.config import get_settings
    from src.pdf_ingestion.embedder import get_embedder
    from src.pdf_ingestion.store import DocumentStore

    cfg      = get_settings()
    store    = DocumentStore(cfg)
    embedder = get_embedder(cfg)

    queries = json.loads(Path(args.query_file).read_text())
    queries = [q for q in queries if not q.get("id", "").startswith("_")]
    queries = [q for q in queries if q.get("query_type") != "visual"]

    console.print("\n[bold blue]Eval Query Calibration[/]")
    console.print("For each query, review the retrieved pages and update eval_queries.json.\n")

    updates = []

    for q in queries:
        qid    = q["id"]
        qtext  = q["query"]
        current_pages = q.get("relevant_pages")
        calibrated    = q.get("calibrated", False)

        if calibrated:
            console.print(f"[green]✓ {qid}[/] already calibrated: {current_pages}")
            updates.append(q)
            continue

        vec  = np.array(embedder.embed_query(qtext), dtype=np.float32)
        hits = store.search(vec, tenant_id=args.tenant, limit=args.limit)

        if not hits:
            console.print(f"[red]✗ {qid}[/] {qtext[:50]} — no hits")
            updates.append(q)
            continue

        console.print(f"\n[bold cyan]━━ {qid}: {qtext} ━━[/]")
        console.print(f"   Current relevant_pages: {current_pages}\n")

        for i, h in enumerate(hits, start=1):
            page  = h.get("page_number", "?")
            score = h.get("score", 0)
            text  = h.get("text", "").strip()
            console.print(f"  [bold]#{i}[/]  page=[yellow]{page}[/]  score={score:.4f}")
            console.print(f"  {text}\n")

        pages_found = [h.get("page_number") for h in hits]
        console.print(
            f"  [yellow]→ Mark relevant_pages with the page numbers whose text above "
            f"actually answers the query. Set calibrated=true when done.[/]\n"
        )
        console.print("─" * 80)
        updates.append(q)

    console.print("\n[bold]Calibration guidance:[/]")
    console.print(
        "1. For each query, identify which retrieved pages actually contain the answer.\n"
        "2. Update relevant_pages in data/eval_queries.json with the correct page numbers.\n"
        "3. Set calibrated=true for that query.\n"
        "4. Re-run: uv run python scripts/evaluate_rag.py --retrieval-only --skip-visual"
    )


if __name__ == "__main__":
    main()
