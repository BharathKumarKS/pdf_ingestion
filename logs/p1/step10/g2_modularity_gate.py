#!/usr/bin/env python
"""A4 — the §G2 modularity gate, run as the **before** arm (report-only). 2026-10-20.

What this is
------------
Compute the modularity `Q` of a **Leiden** partition of the `RELATES_TO` concept subgraph,
and compare it against a **degree-preserving random rewiring** of the same graph — the
course's Lab 2 procedure. Pure local CPU: no LLM, no new dependency (Leiden and
`modularity` are both in the installed networkx 3.6.1).

Why now, and why REPORT-ONLY
----------------------------
It gives the **before** number that §G3's effect will be read against. But it is
**one-sided on this graph**: the §G plan itself says §I21 (TOC concepts in the graph) "is a
prerequisite for good communities, since TOC concepts are exactly the noise that fragments
them". So a **PASS is trustworthy** (Q beats the null despite the noise) and a **FAIL is
confounded and proves nothing** — it cannot distinguish "no community structure" from
"structure destroyed by TOC noise". That caveat is written into the artifact itself
(`one_sided_caveat`), not only into the register.

Verifiers this script exists to satisfy
---------------------------------------
1. BOTH numbers reported — `Q(observed)` and `Q(rewired null)`, never the former alone.
2. The null is REPRODUCIBLE — fixed seed, run twice, byte-identical JSON.
3. Every community asserted CONNECTED (Leiden's guarantee, which Louvain does not give).
4. The one-sided caveat is IN the artifact.
5. An independent reviewer reads the script.

Run:
    unset PYTHONPATH && uv run python logs/p1/step10/g2_modularity_gate.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import networkx as nx  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from src.core.config import get_settings  # noqa: E402

SEED = 20261020          # fixed: the null must not move between runs
RESOLUTION = 1.0

ONE_SIDED_CAVEAT = (
    "ONE-SIDED RESULT — do not read a FAIL as evidence of no community structure. The graph "
    "carries TOC concepts because the Phase 3 build does not apply the E5 content filter (§I21), "
    "and the §G plan states §I21 'is a prerequisite for good communities, since TOC concepts are "
    "exactly the noise that fragments them'. So a PASS (Q beats the rewired null) is trustworthy "
    "even under that noise, while a FAIL is CONFOUNDED: it cannot distinguish 'no structure' from "
    "'structure fragmented by TOC noise'. Do not let a FAIL kill G2."
)


def load_relates_to(cfg) -> list[tuple[str, str]]:
    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )
    try:
        with driver.session() as s:
            rows = s.run(
                "MATCH (a:Concept)-[:RELATES_TO]->(b:Concept) RETURN a.name AS a, b.name AS b"
            ).data()
            total = s.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS n").single()["n"]
    finally:
        driver.close()
    print(f"RELATES_TO edges in the graph: {total:,} (rows read: {len(rows):,})")
    return [(r["a"], r["b"]) for r in rows]


def build_graph(edges: list[tuple[str, str]]) -> tuple[nx.Graph, dict]:
    g = nx.Graph()
    self_loops = 0
    for a, b in edges:
        if a == b:
            self_loops += 1
            continue
        g.add_edge(a, b)
    meta = {
        "directed_edges": len(edges),
        "self_loops_dropped": self_loops,
        "nodes": g.number_of_nodes(),
        "undirected_edges": g.number_of_edges(),
        "duplicate_directed_edges_collapsed": len(edges) - self_loops - g.number_of_edges(),
        "components": nx.number_connected_components(g),
        "density": round(nx.density(g), 6),
        "max_degree": max(d for _, d in g.degree()),
        "isolates": sum(1 for _, d in g.degree() if d == 0),
    }
    return g, meta


def resolve_partitioner() -> tuple[str, object, str | None]:
    """Return (name, callable, why_not_leiden).

    ⚠️ MEASURED 2026-10-20 — the §G plan's premise does NOT hold. It says "Leiden and
    `modularity` are both present in the installed networkx 3.6.1 ... no new dependency".
    `modularity` is native, but `nx.community.leiden_communities` in networkx 3.6.1 is an
    **API stub for backend dispatch**: with no backend installed it raises
    `NotImplementedError: 'leiden_communities' is not implemented by 'networkx' backend`.
    The only registered backend here is `nx_loopback`; igraph/leidenalg/nx_parallel/graphblas
    are all absent. So the *symbol* exists and the *algorithm* does not run.

    This script therefore falls back to Louvain — which IS native — and says so in the
    artifact, because the difference is material: **Leiden's selling point over Louvain is
    that every community it returns is connected**. That guarantee is NOT inherited by the
    fallback, so connectivity is measured below rather than assumed (verifier 3).
    """
    try:
        nx.community.leiden_communities(nx.path_graph(2), seed=SEED)
        return "leiden", nx.community.leiden_communities, None
    except NotImplementedError as exc:
        return ("louvain",
                nx.community.louvain_communities,
                f"leiden_communities is not implemented by the installed networkx backend "
                f"({exc}); no backend package (igraph/leidenalg/nx_parallel/graphblas) is "
                f"installed and this plan forbids adding a dependency")


def partition(g: nx.Graph, algo, name: str) -> tuple[list[set], float]:
    communities = [set(c) for c in algo(
        g, weight=None, resolution=RESOLUTION, seed=SEED
    )]
    q = nx.community.modularity(g, communities, weight=None, resolution=RESOLUTION)
    return communities, float(q)


def canon(communities: list[set]) -> list[list[str]]:
    """Deterministic, order-independent representation (verifier 2 depends on this)."""
    rows = [sorted(c) for c in communities]
    rows.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return rows


def connectedness(g: nx.Graph, communities: list[set]) -> dict:
    bad = []
    for i, c in enumerate(communities):
        if len(c) > 1 and not nx.is_connected(g.subgraph(c)):
            bad.append({"index": i, "size": len(c), "members": sorted(c)[:10]})
    return {
        "n_communities": len(communities),
        "n_singleton_communities": sum(1 for c in communities if len(c) == 1),
        "n_multi_member": sum(1 for c in communities if len(c) > 1),
        "all_connected": not bad,
        "disconnected": bad,
        "largest_community_size": max((len(c) for c in communities), default=0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/g2_modularity_gate.json")
    ap.add_argument("--nswap-factor", type=int, default=10,
                    help="null swaps = factor x number of undirected edges")
    args = ap.parse_args()

    cfg = get_settings()
    edges = load_relates_to(cfg)
    g, gmeta = build_graph(edges)
    print(f"graph: {gmeta['nodes']:,} nodes, {gmeta['undirected_edges']:,} undirected edges, "
          f"{gmeta['components']} components, density {gmeta['density']}")

    part_name, part_algo, leiden_gap = resolve_partitioner()
    print(f"partitioner: {part_name}"
          + (f"   ⚠️ Leiden unavailable: {leiden_gap}" if leiden_gap else ""))

    # ---- 1. observed partition ------------------------------------------------
    t = time.time()
    comm, q_obs = partition(g, part_algo, part_name)
    obs_secs = time.time() - t
    print(f"{part_name}(observed): {len(comm)} communities, Q = {q_obs:.6f}  ({obs_secs:.1f}s)")
    conn = connectedness(g, comm)
    print(f"  connectivity: all_connected={conn['all_connected']} "
          f"disconnected={len(conn['disconnected'])}")

    # ---- 2. the degree-preserving rewired null --------------------------------
    nswap = args.nswap_factor * g.number_of_edges()
    h = g.copy()
    t = time.time()
    nx.double_edge_swap(h, nswap=nswap, max_tries=nswap * 20, seed=SEED)
    swap_secs = time.time() - t
    degree_sequence_preserved = (
        sorted(d for _, d in g.degree()) == sorted(d for _, d in h.degree())
    )
    print(f"rewired null: {nswap:,} swaps in {swap_secs:.1f}s; "
          f"degree sequence preserved = {degree_sequence_preserved}")

    t = time.time()
    comm_null, q_null = partition(h, part_algo, part_name)
    null_secs = time.time() - t
    # Secondary null: the OBSERVED partition scored on the rewired graph — "is the observed
    # partition's Q higher than the same partition would score on a degree-matched random graph".
    q_null_fixed = float(nx.community.modularity(
        h, comm, weight=None, resolution=RESOLUTION))
    print(f"{part_name}(rewired null): {len(comm_null)} communities, Q = {q_null:.6f} "
          f"({null_secs:.1f}s); Q(observed partition) on the null graph = {q_null_fixed:.6f}")

    q_gap = q_obs - q_null
    verdict = "PASS (one-sided)" if q_obs > q_null else "FAIL (CONFOUNDED — see caveat)"

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/g2_modularity_gate.py",
            "what": "§G2 modularity gate, BEFORE arm (report-only)",
            "graph_source": f"memgraph {cfg.memgraph_host}:{cfg.memgraph_port} RELATES_TO",
            "algorithm": f"networkx.community.{part_name}_communities",
            "algorithm_requested": "leiden",
            "leiden_available": part_name == "leiden",
            "leiden_unavailable_reason": leiden_gap,
            "connectivity_guarantee": (
                "Leiden guarantees every returned community is connected; Louvain does NOT. "
                "Connectivity is therefore MEASURED (see `connectivity`), not assumed."
            ),
            "networkx": nx.__version__,
            "resolution": RESOLUTION,
            "weight": None,
            "seed": SEED,
            "nswap_factor": args.nswap_factor,
            "no_llm_calls": True,
        },
        "graph": gmeta,
        "observed": {
            "q": round(q_obs, 6),
            "n_communities": len(comm),
            "seconds": round(obs_secs, 1),
            "community_sizes": sorted((len(c) for c in comm), reverse=True)[:20],
            "communities_sha256": hashlib.sha256(
                json.dumps(canon(comm), ensure_ascii=False).encode()).hexdigest(),
        },
        "null_rewired": {
            "q": round(q_null, 6),
            "q_observed_partition_on_null_graph": round(q_null_fixed, 6),
            "n_communities": len(comm_null),
            "nswap": nswap,
            "swap_seconds": round(swap_secs, 1),
            "degree_sequence_preserved": degree_sequence_preserved,
            "communities_sha256": hashlib.sha256(
                json.dumps(canon(comm_null), ensure_ascii=False).encode()).hexdigest(),
        },
        "comparison": {
            "q_observed": round(q_obs, 6),
            "q_null": round(q_null, 6),
            "gap": round(q_gap, 6),
            "ratio": round(q_obs / q_null, 4) if q_null else None,
            "verdict": verdict,
        },
        "connectivity": conn,
        "one_sided_caveat": ONE_SIDED_CAVEAT,
        "top_communities": [
            {"size": len(c), "sample_members": sorted(c)[:15]}
            for c in sorted(comm, key=len, reverse=True)[:10]
        ],
    }
    # Byte-identity across runs (verifier 2) requires NO wall-clock field in the artifact:
    # timings are printed to stdout (the .log) and never written into the JSON.
    for sect in ("observed", "null_rewired"):
        out[sect].pop("seconds", None)
        out[sect].pop("swap_seconds", None)

    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("\n=== §G2 modularity gate (BEFORE arm, report-only) ===")
    print(f"Q(observed)            = {q_obs:.6f}")
    print(f"Q(rewired null)        = {q_null:.6f}")
    print(f"Q(observed part.) on null graph = {q_null_fixed:.6f}")
    print(f"gap                    = {q_gap:+.6f}   ratio {out['comparison']['ratio']}")
    print(f"verdict                = {verdict}")
    print(f"communities            = {len(comm)} "
          f"({conn['n_multi_member']} multi-member, largest {conn['largest_community_size']})")
    print(f"all communities connected = {conn['all_connected']}")
    print(f"\nONE-SIDED: {ONE_SIDED_CAVEAT[:120]}…")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
