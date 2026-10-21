#!/usr/bin/env python
"""§G2 — the Leiden community-detection gate, on the live concept graph. 2026-10-21.

What this is
------------
The §G plan's §3 gate, re-run on **Leiden** (owner decision 2026-10-21: *"use Leiden,
not Louvain, as that's the improvement over Louvain"*). The before arm (§I33) ran on
Louvain only, because `nx.community.leiden_communities` is a backend-dispatch stub
that raises `NotImplementedError` with no backend installed — so its number must not
be quoted again until it is re-run here.

Procedure (the course's Lab 2, verbatim)
----------------------------------------
`Labs/Week_5/ms_graphrag_tutorial/docs/graph_analysis.md` §1: loop over resolutions
**0.5, 1.0, 2.0**; for each, run **both** Louvain and Leiden; score each partition's
modularity against a **degree-preserving random rewiring** of the same graph
(`nx.double_edge_swap`) and report the **surplus over chance**. Assert every community
is connected — Leiden's guarantee, which Louvain does not give.

Single-variable discipline
--------------------------
The primary comparison keeps the before arm's settings exactly (unweighted,
resolution 1.0, seed 20261020) so Louvain->Leiden is the ONLY change. The weighted
variant is reported alongside, not instead: changing partitioner *and* weights at once
would confound the comparison. Modularity is scored with networkx in both arms, so the
metric does not move either.

Run:
    unset PYTHONPATH && uv run python logs/p1/step10/g2_leiden_gate.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import networkx as nx  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.graph_analytics import (  # noqa: E402
    connectedness_report,
    leiden_partition,
    louvain_partition,
    modularity,
    rewire_degree_preserving,
)

SEED = 20261020          # same as the before arm — the null must not move between runs
RESOLUTIONS = (0.5, 1.0, 2.0)
PRIMARY_RESOLUTION = 1.0

ONE_SIDED_CAVEAT = (
    "ONE-SIDED RESULT — do not read a FAIL as evidence of no community structure. The graph "
    "carries TOC concepts because the Phase 3 build does not apply the E5 content filter (§I21), "
    "and the §G plan states §I21 'is a prerequisite for good communities, since TOC concepts are "
    "exactly the noise that fragments them'. So a PASS (Q beats the rewired null) is trustworthy "
    "even under that noise, while a FAIL is CONFOUNDED. Do not let a FAIL kill G2."
)


def load_relates_to(cfg) -> tuple[list[tuple[str, str, float]], list[str]]:
    """Read the RELATES_TO adjacency, with weights, from the live Memgraph."""
    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )
    try:
        with driver.session() as s:
            rows = s.run(
                "MATCH (a:Concept)-[r:RELATES_TO]->(b:Concept) "
                "RETURN a.name AS a, b.name AS b, r.weight AS w"
            ).data()
            total = s.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n").single()["n"]
            docs = [r["id"] for r in s.run("MATCH (d:Document) RETURN d.id AS id").data()]
    finally:
        driver.close()
    print(f"RELATES_TO edges in the graph: {total:,} (rows read: {len(rows):,}); docs {docs}")
    return [(r["a"], r["b"], float(r["w"] or 1.0)) for r in rows], sorted(docs)


def build_graph(edges: list[tuple[str, str, float]]) -> tuple[nx.Graph, dict]:
    """Undirected simple graph. Self-loops are dropped (they carry no co-occurrence)."""
    g = nx.Graph()
    self_loops = 0
    for a, b, w in edges:
        if a == b:
            self_loops += 1
            continue
        g.add_edge(a, b, weight=w)
    meta = {
        "directed_edges": len(edges),
        "self_loops_dropped": self_loops,
        "nodes": g.number_of_nodes(),
        "undirected_edges": g.number_of_edges(),
        "components": nx.number_connected_components(g),
        "density": round(nx.density(g), 6),
        "max_degree": max(d for _, d in g.degree()),
        "isolates": sum(1 for _, d in g.degree() if d == 0),
    }
    return g, meta


def canon(communities: list[set]) -> list[list[str]]:
    """Deterministic, order-independent representation — byte-identity depends on this."""
    rows = [sorted(c) for c in communities]
    rows.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return rows


def nesting(fine: list[set], coarse: list[set]) -> dict:
    """How far the finer partition nests inside the coarser one.

    "Hierarchy: 2-4 levels" is only meaningful if the levels actually nest — a
    resolution ladder that repartitions from scratch at every step is a sweep, not a
    hierarchy. Reports the fraction of fine communities that lie wholly inside a
    single coarse community.
    """
    coarse_of = {}
    for i, c in enumerate(coarse):
        for node in c:
            coarse_of[node] = i
    nested = sum(
        1 for c in fine
        if len({coarse_of.get(n, -1) for n in c}) == 1
    )
    return {
        "n_fine": len(fine),
        "n_coarse": len(coarse),
        "n_fine_wholly_inside_one_coarse": nested,
        "fraction_nested": round(nested / len(fine), 4) if fine else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/g2_leiden_gate.json")
    ap.add_argument("--nswap-factor", type=int, default=10)
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing artifact (refused by default)")
    args = ap.parse_args()

    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force — a registered artifact "
              f"must not be clobbered by accident.")
        return 2

    cfg = get_settings()
    edges, graph_docs = load_relates_to(cfg)
    if not edges:
        print("ABORT: no RELATES_TO edges — writing nothing (no data must not look like "
              "an all-zero result).")
        return 3
    g, gmeta = build_graph(edges)
    print(f"graph: {gmeta['nodes']:,} nodes, {gmeta['undirected_edges']:,} undirected edges, "
          f"{gmeta['components']} components, density {gmeta['density']}")

    # ---- the degree-preserving rewired null -----------------------------------
    h, preserved = rewire_degree_preserving(g, seed=SEED, nswap_factor=args.nswap_factor)
    print(f"rewired null: degree sequence preserved = {preserved}; "
          f"{h.number_of_edges():,} edges")
    if not preserved:
        print("ABORT: the null did not preserve the degree sequence — a null with a different "
              "degree sequence differs for a trivial reason. Writing nothing.")
        return 4

    # ---- resolution ladder, both partitioners, both against their own null -----
    ladder: dict[str, dict] = {}
    for resolution in RESOLUTIONS:
        row: dict = {}
        for name, fn in (("leiden", leiden_partition), ("louvain", louvain_partition)):
            # unweighted — the before arm's setting, so the partitioner is the only change
            comm, q = fn(g, resolution=resolution, seed=SEED, weight=None)
            null_comm, q_null = fn(h, resolution=resolution, seed=SEED, weight=None)
            q_fixed = modularity(h, comm, weight=None, resolution=resolution)
            row[name] = {
                "q": round(q, 6),
                "n_communities": len(comm),
                "community_sizes": sorted((len(c) for c in comm), reverse=True)[:20],
                "connectivity": connectedness_report(g, comm),
                "null_q": round(q_null, 6),
                "null_q_observed_partition_on_null_graph": round(q_fixed, 6),
                "surplus": round(q - q_null, 6),
                "ratio": round(q / q_null, 4) if q_null else None,
                "communities_sha256": hashlib.sha256(
                    json.dumps(canon(comm), ensure_ascii=False).encode()).hexdigest(),
            }
            print(f"  res {resolution}  {name:7} Q={q:.6f}  null={q_null:.6f}  "
                  f"surplus={q - q_null:+.6f}  n={len(comm):4}  "
                  f"connected={row[name]['connectivity']['all_connected']}")
        # weighted variant — secondary, reported not substituted
        comm_w, q_w = leiden_partition(g, resolution=resolution, seed=SEED, weight="weight")
        row["leiden_weighted"] = {
            "q": round(q_w, 6),
            "n_communities": len(comm_w),
            "connectivity": connectedness_report(g, comm_w),
        }
        print(f"  res {resolution}  leiden(weighted) Q={q_w:.6f} n={len(comm_w)} "
              f"connected={row['leiden_weighted']['connectivity']['all_connected']}")
        ladder[str(resolution)] = row

    # ---- hierarchy: does the ladder actually nest? ----------------------------
    parts: dict[float, list[set]] = {}
    for resolution in RESOLUTIONS:
        parts[resolution], _ = leiden_partition(g, resolution=resolution, seed=SEED, weight=None)
    ordered = sorted(RESOLUTIONS)
    hier = {
        f"{coarse}->{fine}": nesting(parts[fine], parts[coarse])
        for coarse, fine in zip(ordered, ordered[1:])
    }
    print("hierarchy nesting:", json.dumps(hier))

    primary = ladder[str(PRIMARY_RESOLUTION)]
    out = {
        "meta": {
            "generated_by": "logs/p1/step10/g2_leiden_gate.py",
            "what": "§G2 modularity gate on LEIDEN (owner decision 2026-10-21), re-running §I33",
            "graph_source": f"memgraph {cfg.memgraph_host}:{cfg.memgraph_port} RELATES_TO",
            "graph_document_ids": graph_docs,
            "partitioners": ["leiden (leidenalg on igraph)", "louvain (networkx, comparison arm)"],
            "leiden_backend": "leidenalg + python-igraph (added 2026-10-21)",
            "resolution": PRIMARY_RESOLUTION,
            "resolutions_run": list(RESOLUTIONS),
            "weight_primary": None,
            "weight_secondary": "weight",
            "seed": SEED,
            "nswap_factor": args.nswap_factor,
            "modularity_scorer": "networkx.community.modularity (same as the §I33 before arm)",
            "no_llm_calls": True,
            "no_reingest": True,
            "before_arm_reference": {
                "artifact": "logs/p1/step10/g2_modularity_gate.json",
                "partitioner": "louvain (leiden unavailable then, §I33)",
                "q_observed": 0.589597,
                "q_rewired_null": 0.280330,
                "note": "superseded — quote THIS artifact from now on",
            },
        },
        "graph": gmeta,
        "null_rewired": {"degree_sequence_preserved": preserved,
                         "nswap_factor": args.nswap_factor},
        "ladder": ladder,
        "hierarchy_nesting": hier,
        "comparison_primary": {
            "resolution": PRIMARY_RESOLUTION,
            "leiden": {k: primary["leiden"][k] for k in
                       ("q", "null_q", "surplus", "ratio", "n_communities")},
            "louvain": {k: primary["louvain"][k] for k in
                        ("q", "null_q", "surplus", "ratio", "n_communities")},
            "verdict": ("PASS (one-sided)" if primary["leiden"]["surplus"] > 0
                        else "FAIL (CONFOUNDED — see caveat)"),
        },
        "connectedness": {
            "leiden_all_connected_at_every_resolution": all(
                ladder[str(r)]["leiden"]["connectivity"]["all_connected"] for r in RESOLUTIONS
            ),
            "louvain_all_connected_at_every_resolution": all(
                ladder[str(r)]["louvain"]["connectivity"]["all_connected"] for r in RESOLUTIONS
            ),
            "louvain_disconnected_communities": {
                str(r): ladder[str(r)]["louvain"]["connectivity"]["disconnected"]
                for r in RESOLUTIONS
                if not ladder[str(r)]["louvain"]["connectivity"]["all_connected"]
            },
        },
        "one_sided_caveat": ONE_SIDED_CAVEAT,
        "top_communities_leiden_res_1": [
            {"size": len(c), "sample_members": sorted(c)[:15]}
            for c in sorted(parts[PRIMARY_RESOLUTION], key=len, reverse=True)[:10]
        ],
    }
    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("\n=== §G2 Leiden gate ===")
    print(f"Q(leiden, res {PRIMARY_RESOLUTION})   = {primary['leiden']['q']:.6f}")
    print(f"Q(null,   res {PRIMARY_RESOLUTION})   = {primary['leiden']['null_q']:.6f}")
    print(f"surplus                     = {primary['leiden']['surplus']:+.6f} "
          f"(ratio {primary['leiden']['ratio']})")
    print(f"leiden all connected        = {out['connectedness']['leiden_all_connected_at_every_resolution']}")
    print(f"louvain all connected       = {out['connectedness']['louvain_all_connected_at_every_resolution']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
