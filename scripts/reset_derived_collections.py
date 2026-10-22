#!/usr/bin/env python3
"""
Drop the DERIVED Qdrant collections so they are recreated at the dense lane's dimension.

WHY THIS EXISTS (§I12 / §I47)
`derivative_artifacts` and `concept_embeddings` were created at the retired 768d
`embedding_dim`. The query side moved to the dense lane (1024d), and **Qdrant cannot resize
a collection in place** — so a 768d collection can only become 1024d by being dropped and
recreated. Until that happens every query against the lane is rejected with
`Vector dimension error: expected dim: 768, got 1024`, the lane's `except Exception`
swallows it and returns `[]`, and the lane is **silently empty**:

    * `derivative_artifacts`  -> the DA lane, empty on EVERY query (§I12)
    * `concept_embeddings`    -> the graph lane, empty on every MULTIHOP query (§I47)

The code half of the move landed in `6773022` (`_ensure_*_collection` now create at
`dense_dim`; `graph_builder._assert_collection_dim` refuses a stale collection loudly). This
script is the DATA half: it removes the stale collections so the next `get_qdrant()` recreates
them at `dense_dim`.

⚠️ THIS SCRIPT DELETES NOTHING ELSE, AND REFUSES ANY OTHER NAME.
`scripts/reset_for_reingest.py` also deletes the right collection — and `knowledge_base` and
every SQLite row with it. It is too broad for this job. Here, only the two derived collections
are droppable; `knowledge_base`, `visual_knowledge_base`, and anything else are **refused with
exit 2** rather than deleted. That refusal is the safety property: it is what stops a typo
from deleting the index.

WHAT RE-POPULATES THEM (this script does not do it)
    * `derivative_artifacts` — `scripts/index_derivative_artifacts.py --clear --doc-id <uuid>`
      (SQLite active cards; the `--doc-id` scope is required — without it the script indexes
      every document's cards).
    * `concept_embeddings`   — a Phase 3 rebuild: `scripts/run_phase3.py --graph-only`
      (Memgraph `Concept` names, embedded on the dense lane). The graph must be cleared first
      (`scripts/clear_graph_document.py`), or the rebuild doubles every `RELATES_TO` weight.

⚠️ WHICH STORE? The default config points at the LOCAL embedded Qdrant when `QDRANT_HOST` is
blank in `.env`. The cluster's collections are reached only with an explicit override:
    QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
Run the dry-run first and read the collection it names — the local and cluster stores hold
different (and differently stale) generations.

SAFETY
    * dry-run is the DEFAULT; nothing is deleted without `--yes`.
    * an allowlist of droppable collections; every other name is refused (exit 2).
    * no `--force`.

Usage:
    uv run python scripts/reset_derived_collections.py --collections concept_embeddings
    uv run python scripts/reset_derived_collections.py --collections concept_embeddings --yes
    QDRANT_HOST=10.0.10.65 uv run python scripts/reset_derived_collections.py \\
        --collections derivative_artifacts concept_embeddings --yes
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

# The repopulation source, per collection — printed in the dry-run so the operator sees what
# the drop costs and how it comes back.
_REPOPULATE = {
    "derivative_artifacts": "SQLite active cards (index_derivative_artifacts.py --clear --doc-id <uuid>)",
    "concept_embeddings":   "Memgraph Concept nodes (run_phase3.py --graph-only, after clear_graph_document.py)",
}


def _droppable(cfg) -> dict[str, str]:
    """The allowlist, keyed by collection NAME -> the cfg attribute it came from.

    Only these two names are ever deletable. Everything else is refused, so `knowledge_base`
    and `visual_knowledge_base` cannot be dropped by this script even if asked for.
    """
    return {
        cfg.da_collection: "da_collection",
        cfg.concept_collection: "concept_collection",
    }


def collection_state(client, name: str) -> dict:
    """{exists, points, dim} for one collection. `dim` is None for a named-vector layout."""
    try:
        info = client.get_collection(name)
    except Exception as exc:  # absent, or unreadable
        return {"exists": False, "points": 0, "dim": None, "error": str(exc)[:120]}
    try:
        size = getattr(info.config.params.vectors, "size", None)
    except Exception:
        size = None
    return {"exists": True, "points": int(info.points_count or 0), "dim": size}


def plan_reset(client, droppable: dict[str, str], requested: list[str]) -> dict:
    """Work out what a reset would do, and whether the request is allowed.

    Returns {"allowed": [...], "refused": [...], "states": {name: state}}.
    A name is refused if it is not in `droppable` — the allowlist is the whole guard.
    """
    allowed, refused = [], []
    for name in requested:
        (allowed if name in droppable else refused).append(name)
    states = {name: collection_state(client, name) for name in allowed}
    return {"allowed": allowed, "refused": refused, "states": states}


def apply_reset(client, names: list[str]) -> list[str]:
    """Delete the named collections. Returns the ones actually deleted (present beforehand)."""
    deleted = []
    for name in names:
        state = collection_state(client, name)
        if not state["exists"]:
            logger.info("Skipped (not found): {}", name)
            continue
        client.delete_collection(name)
        deleted.append(name)
        logger.info("Deleted collection: {}", name)
    return deleted


def main(argv: list[str] | None = None, client=None, cfg=None) -> int:
    """Returns the process exit code. `client` and `cfg` are injectable so the guards are testable."""
    p = argparse.ArgumentParser(
        description="Drop the derived Qdrant collections so they recreate at dense_dim (§I12)"
    )
    p.add_argument("--collections", nargs="+", required=True, metavar="NAME",
                   help="Collection name(s) to drop (must be derivative_artifacts / concept_embeddings)")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Apply the deletion. Without it this is a dry run.")
    args = p.parse_args(argv)

    if cfg is None:
        from src.core.config import get_settings
        cfg = get_settings()

    console.print("[bold]Synapse — drop derived collections (dense-lane move, §I12)[/bold]")
    console.print(
        f"  Qdrant: {'server ' + cfg.qdrant_host if cfg.qdrant_host else 'LOCAL ' + cfg.qdrant_local_path}"
        f"  |  dense_dim={cfg.dense_dim}, legacy embedding_dim={cfg.embedding_dim}"
    )

    if client is None:
        from src.core.database import get_qdrant
        client = get_qdrant(cfg)

    droppable = _droppable(cfg)
    plan = plan_reset(client, droppable, list(args.collections))

    if plan["refused"]:
        # The allowlist is the guard. Refuse the whole request rather than delete a subset —
        # the caller's intent is unambiguous, its name is not.
        console.print(
            f"\n[bold red]REFUSING TO PROCEED.[/bold red] Not droppable by this script:\n"
            f"  {plan['refused']}\n"
            f"  Droppable: {sorted(droppable)}\n"
            "`knowledge_base` and `visual_knowledge_base` are deliberately not droppable here "
            "(use reset_for_reingest.py if that is really what you mean)."
        )
        return 2

    table = Table(title="Collections to drop")
    table.add_column("collection")
    table.add_column("points", justify="right")
    table.add_column("dim", justify="right")
    table.add_column("repopulated by")
    for name in plan["allowed"]:
        st = plan["states"][name]
        table.add_row(
            name,
            f"{st['points']:,}" if st["exists"] else "[dim]absent[/dim]",
            str(st["dim"]) if st["dim"] is not None else "[dim]named[/dim]",
            _REPOPULATE.get(name, ""),
        )
    console.print(table)

    wrong = [n for n in plan["allowed"]
             if plan["states"][n]["exists"] and plan["states"][n]["dim"] not in (None, cfg.dense_dim)]
    if wrong:
        console.print(
            f"[yellow]NOTE:[/yellow] {wrong} are at a dimension != dense_dim ({cfg.dense_dim}) — "
            "that is the stale state this script exists to remove."
        )

    if not args.yes:
        console.print("[yellow]Dry run — nothing was deleted. Re-run with --yes to apply.[/yellow]")
        return 0

    deleted = apply_reset(client, plan["allowed"])
    console.print(
        f"[green]Done.[/green] Deleted {len(deleted)} collection(s): {deleted}. "
        "The next get_qdrant() recreates them at dense_dim; they are EMPTY until re-populated "
        "(see the table's last column)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
