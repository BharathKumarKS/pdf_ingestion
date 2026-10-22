#!/usr/bin/env python
"""Is the gate-vs-builder Q difference NODE ORDERING? Read-only, no LLM. 2026-10-22.

The gate (logs/p1/step10/g2_leiden_gate.py) reports Q=0.783332 at resolution 1.0 on 7,398 nodes /
22,799 edges. `build_hierarchy` on the same node/edge counts reports 0.7774. Same function
(`graph_analytics.leiden_partition`), same seed, same resolution, same edge set — so the remaining
suspect is the ORDER nodes are inserted, because `nx_to_igraph` indexes vertices by
`list(g.nodes())`, i.e. insertion order, and igraph's seeded RNG draws from that indexing.

This probe settles it: build the SAME edge set in three different orders and compare Q.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import networkx as nx  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import get_memgraph  # noqa: E402
from src.pdf_ingestion.graph_analytics import leiden_partition  # noqa: E402

SEED = 20261020          # the gate's SEED
RES = 1.0


def main() -> int:
    cfg = get_settings()
    driver = get_memgraph(cfg)
    with driver.session() as s:
        rows = s.run(
            "MATCH (a:Concept)-[r:RELATES_TO]->(b:Concept) "
            "RETURN a.name AS a, b.name AS b, r.weight AS w"
        ).data()
    edges = [(r["a"], r["b"], float(r["w"] or 1.0)) for r in rows]
    print(f"directed rows read: {len(edges):,}")

    def build(order):
        g = nx.Graph()
        for a, b, w in order:
            if a == b:
                continue
            g.add_edge(a, b, weight=w)
        return g

    variants = {
        "gate order (as read)": edges,
        "reversed": list(reversed(edges)),
        "sorted by (a,b)": sorted(edges, key=lambda e: (e[0], e[1])),
    }
    for label, order in variants.items():
        g = build(order)
        comm, q = leiden_partition(g, resolution=RES, seed=SEED, weight=None)
        first = list(g.nodes())[:3]
        print(f"  {label:22} nodes={g.number_of_nodes():,} edges={g.number_of_edges():,} "
              f"n_comm={len(comm):3}  Q={q:.6f}  first_nodes={first}")

    print("\ngate reports: nodes=7,398 edges=22,799 n_comm=338 Q=0.783332")
    print("If only the 'gate order' row reproduces 0.783332, the difference is node insertion "
          "order — an igraph vertex-indexing artifact, not a different graph or a bug.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
