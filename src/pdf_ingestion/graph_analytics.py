"""
Graph analytics over the concept graph — §G1 (personalized PageRank) and §G2
(Leiden community detection).

Why this module exists
----------------------
`IMPROVEMENTS.md` §G. The graph's *storage* model is right (`Document/Page/Chunk/
Concept` + `PART_OF/ON_PAGE/MENTIONS/RELATES_TO/PREREQUISITE_OF`) but nothing is
built on top of it: `graph_search` ranks by distinct concepts matched and
`hop_distance` is a constant 0 (§I2), so there is no traversal and no notion of
which concepts actually matter for a query. This module supplies the two the
course specifies.

* **§G1 — personalized PageRank.** ``v(k+1) = (1 - lam) * W v(k) + lam * v(0)``
  with ``W = D^-1 A`` over the ``RELATES_TO`` adjacency, seeded at the query's
  concepts. ``lam = 1/2`` for 10 iterations (HippoRAG / MemGraphRAG); the
  syllabus also asks for a lambda sweep to be *reported*.
* **§G2 — Leiden community detection**, scored against a degree-preserving
  rewired null. **Leiden, not Louvain** (owner decision 2026-10-21): every
  community Leiden returns is connected, which Louvain does not guarantee.

`leidenalg` operates on **igraph** objects, so :func:`nx_to_igraph` is the
translation layer — the same one the course's Lab 2 uses. networkx's own
``leiden_communities`` is an API-dispatch stub that raises ``NotImplementedError``
with no backend installed: the symbol exists, the algorithm does not (§I33).

Two deliberate scoring choices
------------------------------
* Modularity is scored with **networkx**, not igraph. The §G2 gate's *before* arm
  (§I33) scored a Louvain partition with ``nx.community.modularity``; scoring
  Leiden the same way keeps Louvain-vs-Leiden a **single-variable** change rather
  than a change of partitioner *and* of metric.
* Everything here is deterministic given ``seed`` — the null must not move between
  runs, so no wall-clock value is ever written into an artifact.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import networkx as nx
import numpy as np

__all__ = [
    "nx_to_igraph",
    "leiden_partition",
    "leiden_ladder",
    "louvain_partition",
    "modularity",
    "rewire_degree_preserving",
    "connectedness_report",
    "personalized_pagerank",
    "ppr_lambda_sweep",
    "hub_suppression_report",
]


# ── translation: networkx -> igraph ──────────────────────────────────────────

def nx_to_igraph(g: nx.Graph, weight: str | None = None):
    """Translate a networkx graph to an igraph object, preserving node names.

    ``leidenalg`` runs on igraph objects, not networkx ones (§I33). Node names
    survive on the ``name`` vertex attribute so a partition can be mapped back to
    the original node objects; edges are added undirected, because Leiden is
    defined on undirected graphs and ``RELATES_TO`` is stored once per pair.

    ``weight`` names an edge attribute to carry across as the igraph ``weight``
    edge attribute; edges missing it default to 1.0.
    """
    import igraph as ig

    nodes = list(g.nodes())
    index = {node: i for i, node in enumerate(nodes)}
    edges = [(index[u], index[v]) for u, v in g.edges()]
    out = ig.Graph(n=len(nodes), edges=edges, directed=False)
    out.vs["name"] = nodes
    if weight is not None:
        out.es["weight"] = [
            float(g.edges[u, v].get(weight, 1.0)) for u, v in g.edges()
        ]
    return out


# ── §G2: Leiden ──────────────────────────────────────────────────────────────

def leiden_partition(
    g: nx.Graph,
    resolution: float = 1.0,
    seed: int = 0,
    weight: str | None = None,
    n_iterations: int = 2,
) -> tuple[list[set], float]:
    """Leiden communities of ``g``, as ``(communities, modularity)``.

    ``communities`` is a list of node sets; ``modularity`` is scored with
    :func:`modularity` (networkx) on those communities, so it is directly
    comparable to the Louvain before-arm.

    ``resolution`` is Leiden's resolution parameter: below 1 favours fewer, broader
    communities, above 1 favours many tight ones.
    """
    import leidenalg as la

    if g.number_of_nodes() == 0:
        return [], 0.0

    ig_graph = nx_to_igraph(g, weight=weight)
    kwargs: dict = {"resolution_parameter": resolution, "seed": seed}
    if weight is not None:
        kwargs["weights"] = "weight"
    partition = la.find_partition(
        ig_graph,
        la.RBConfigurationVertexPartition,
        n_iterations=n_iterations,
        **kwargs,
    )
    communities = [set(ig_graph.vs[i]["name"] for i in community) for community in partition]
    return communities, modularity(g, communities, weight=weight, resolution=resolution)


def modularity(
    g: nx.Graph,
    communities: Iterable[set],
    weight: str | None = None,
    resolution: float = 1.0,
) -> float:
    """``nx.community.modularity`` — the §G2 gate's objective, and the before-arm's metric."""
    communities = [set(c) for c in communities]
    if not communities or g.number_of_edges() == 0:
        return 0.0
    return float(nx.community.modularity(g, communities, weight=weight, resolution=resolution))


def louvain_partition(
    g: nx.Graph,
    resolution: float = 1.0,
    seed: int = 0,
    weight: str | None = None,
) -> tuple[list[set], float]:
    """Louvain communities of ``g`` — the comparison arm, kept for the Lab 2 contrast.

    Lab 2 runs **both** algorithms and compares each against its own rewired null.
    Louvain is native to networkx; it is *not* the chosen partitioner (owner
    decision 2026-10-21) and is here only so the connectedness difference is
    measured rather than asserted — the §G2 before-arm already caught Louvain
    returning a disconnected 75-member community (§I33).
    """
    if g.number_of_nodes() == 0:
        return [], 0.0
    communities = [
        set(c) for c in nx.community.louvain_communities(
            g, weight=weight, resolution=resolution, seed=seed
        )
    ]
    return communities, modularity(g, communities, weight=weight, resolution=resolution)


def leiden_ladder(
    g: nx.Graph,
    resolutions: Iterable[float] = (0.5, 1.0, 2.0),
    seed: int = 0,
    weight: str | None = None,
) -> dict[float, dict]:
    """Run Leiden at each resolution — the syllabus's finite-zoom ladder.

    ``0.5`` gives few broad communities, ``2.0`` many tight ones. Returns a mapping
    ``resolution -> {"communities", "q", "n_communities", "community_sizes",
    "connectivity"}``.
    """
    out: dict[float, dict] = {}
    for resolution in resolutions:
        communities, q = leiden_partition(g, resolution=resolution, seed=seed, weight=weight)
        out[float(resolution)] = {
            "communities": communities,
            "q": q,
            "n_communities": len(communities),
            "community_sizes": sorted((len(c) for c in communities), reverse=True),
            "connectivity": connectedness_report(g, communities),
        }
    return out


def connectedness_report(g: nx.Graph, communities: Iterable[set]) -> dict:
    """Check every community is internally connected — Leiden's guarantee over Louvain.

    Measured, never assumed: the before-arm ran on Louvain and returned a
    disconnected community of 75 members (§I33). Singletons are connected by
    definition and are counted separately.
    """
    communities = [set(c) for c in communities]
    disconnected = []
    for i, community in enumerate(communities):
        if len(community) > 1 and not nx.is_connected(g.subgraph(community)):
            disconnected.append({
                "index": i,
                "size": len(community),
                "members": sorted(community)[:10],
            })
    return {
        "n_communities": len(communities),
        "n_singletons": sum(1 for c in communities if len(c) == 1),
        "n_multi_member": sum(1 for c in communities if len(c) > 1),
        "largest": max((len(c) for c in communities), default=0),
        "all_connected": not disconnected,
        "disconnected": disconnected,
    }


# ── the null: a degree-preserving rewiring ───────────────────────────────────

def rewire_degree_preserving(
    g: nx.Graph,
    seed: int = 0,
    nswap_factor: int = 10,
) -> tuple[nx.Graph, bool]:
    """Degree-preserving random rewiring of ``g``, as ``(rewired, degrees_preserved)``.

    The course's Lab 2 procedure, verbatim: *"structure is a surplus over chance,
    so compute the chance."* ``nx.double_edge_swap`` rewires by swapping edge
    endpoints, which leaves the degree of every node unchanged — that is the point,
    because a null with a different degree sequence would differ for a trivial
    reason. ``degrees_preserved`` is asserted by the caller, not assumed here.

    If the graph has too few edges for a swap to succeed, the copy is returned
    unchanged and ``degrees_preserved`` is still computed — the caller can see that
    the null is degenerate rather than silently reading a null equal to the graph.
    """
    h = g.copy()
    nswap = nswap_factor * h.number_of_edges()
    if nswap > 0 and h.number_of_edges() >= 2:
        try:
            nx.double_edge_swap(h, nswap=nswap, max_tries=nswap * 20, seed=seed)
        except nx.NetworkXAlgorithmError:
            pass  # too few edges to swap — h stays a copy of g; the caller sees it
    preserved = (
        sorted(d for _, d in g.degree()) == sorted(d for _, d in h.degree())
    )
    return h, preserved


# ── §G1: personalized PageRank ───────────────────────────────────────────────

def personalized_pagerank(
    g: nx.Graph,
    seeds: Mapping[str, float] | Iterable[str],
    lam: float = 0.5,
    iterations: int = 10,
    weight: str | None = None,
) -> dict:
    """Personalized PageRank over ``g``'s adjacency, seeded at ``seeds``.

    The iteration is the syllabus's, verbatim::

        v(k+1) = (1 - lam) * W v(k) + lam * v(0)      W = D^-1 A

    ``lam`` is the restart probability toward the seed vector ``v(0)``; ``lam = 1/2``
    for 10 iterations is the HippoRAG / MemGraphRAG setting. ``W`` is row-normalised,
    so a node with no ``RELATES_TO`` edge (a dangling row) contributes nothing and
    its mass is not re-injected — isolated concepts simply never accumulate score.

    ``seeds`` is either a mapping of concept name to weight (e.g. the similarity
    scores ``GraphBuilder._find_concepts_scored`` returns) or a plain iterable of
    names, in which case every seed is weighted 1.0. Seed weights are normalised to
    sum to 1. Raises ``ValueError`` when no seed is a node of ``g`` — a silent
    all-zero vector would look like "no concepts matter".

    ⚠️ **The returned scores are NOT a probability distribution in general, and this
    is the spec, not a bug.** ``W = D^-1 A`` is row-stochastic, so ``1^T W v`` is
    weighted by W's *column* sums, which need not be 1 — the iteration conserves
    total mass only when ``W`` is doubly stochastic, i.e. on a regular graph. The
    syllabus's own figure reads the result as fractions ("52% of the energy stays on
    the seed"), which holds on a regular graph and is approximate otherwise. Ranking
    is unaffected (a positive scalar would not reorder), so **do not normalise here**
    — that would silently change the specified iteration. Callers that need a
    distribution should divide by the sum and say so.
    """
    import scipy.sparse as sp

    nodes = list(g.nodes())
    n = len(nodes)
    index = {node: i for i, node in enumerate(nodes)}

    rows, cols, data = [], [], []
    for u, v in g.edges():
        w = float(g.edges[u, v].get(weight, 1.0)) if weight else 1.0
        i, j = index[u], index[v]
        rows.extend((i, j))
        cols.extend((j, i))
        data.extend((w, w))
    adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))

    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    inv_degree = np.zeros(n)
    nz = degree > 0
    inv_degree[nz] = 1.0 / degree[nz]
    transition = sp.diags(inv_degree) @ adjacency

    items = seeds.items() if isinstance(seeds, Mapping) else ((s, 1.0) for s in seeds)
    v0 = np.zeros(n)
    matched = 0
    for name, score in items:
        if name in index:
            v0[index[name]] += float(score)
            matched += 1
    if matched == 0:
        raise ValueError(
            f"none of the {len(list(seeds))} seed concept(s) is a node of the graph "
            f"({n} nodes) — the seed vector would be all-zero"
        )
    v0 /= v0.sum()

    v = v0.copy()
    for _ in range(iterations):
        v = (1.0 - lam) * (transition @ v) + lam * v0
    return {node: float(v[index[node]]) for node in nodes}


def ppr_lambda_sweep(
    g: nx.Graph,
    seeds: Mapping[str, float] | Iterable[str],
    lambdas: Iterable[float] = (0.1, 0.3, 0.5, 0.7, 0.9),
    iterations: int = 10,
    weight: str | None = None,
    top: int = 10,
) -> dict[float, list[tuple[str, float]]]:
    """Run PPR at each ``lam`` and return ``lam -> top-k (concept, score)``.

    The syllabus: *"at lam = 0.1 the honey wanders; at lam = 0.9 it never leaves
    home."* Reporting the sweep is the check that the chosen ``lam = 1/2`` is the
    middle it claims to be, rather than a number adopted from the reading.
    """
    out: dict[float, list[tuple[str, float]]] = {}
    for lam in lambdas:
        scores = personalized_pagerank(
            g, seeds, lam=lam, iterations=iterations, weight=weight
        )
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top]
        out[float(lam)] = [(name, round(score, 8)) for name, score in ranked]
    return out


def hub_suppression_report(
    g: nx.Graph,
    scores: Mapping[str, float],
    top: int = 20,
) -> dict:
    """Compare the top-PPR concepts against the graph's highest-degree concepts.

    The course's warning: *"expand two hops from 'USA' and you have retrieved the
    encyclopedia."* If the PPR top-k is dominated by the highest-degree nodes, the
    personalization is not doing its job — PPR has degenerated into a global
    centrality ranking. Reports the degree of each top-PPR concept, the degree of
    each top-degree concept, and the overlap between the two sets.
    """
    ranked = [name for name, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top]]
    degrees = dict(g.degree())
    by_degree = [name for name, _ in sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)[:top]]
    return {
        "top_ppr": [{"name": n, "degree": degrees.get(n, 0), "score": round(scores[n], 8)} for n in ranked],
        "top_by_degree": [{"name": n, "degree": degrees.get(n, 0)} for n in by_degree],
        "overlap": sorted(set(ranked) & set(by_degree)),
        "n_overlap": len(set(ranked) & set(by_degree)),
        "max_degree": max(degrees.values(), default=0),
    }
