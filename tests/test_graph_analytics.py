"""Unit tests for `graph_analytics` — §G1 (PPR) and §G2 (Leiden).

All local: synthetic graphs only, no Memgraph, no cluster, no LLM. The live-graph
measurements live in `logs/p1/step10/g{1,2}_*.py`; these tests pin the *behaviour*
the probes rely on, on graphs whose answer is known by construction.
"""
from __future__ import annotations

import networkx as nx
import pytest

from src.pdf_ingestion.graph_analytics import (
    connectedness_report,
    hub_suppression_report,
    leiden_ladder,
    leiden_partition,
    modularity,
    nx_to_igraph,
    personalized_pagerank,
    ppr_lambda_sweep,
    rewire_degree_preserving,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def three_cliques() -> nx.Graph:
    """Three 5-cliques joined by single bridge edges — three communities by construction."""
    g = nx.Graph()
    for base in (0, 10, 20):
        g.add_edges_from(
            (base + i, base + j) for i in range(5) for j in range(i + 1, 5)
        )
    g.add_edge(0, 10)   # bridge clique A - clique B
    g.add_edge(10, 20)  # bridge clique B - clique C
    return g


def barbell() -> nx.Graph:
    """Two 5-cliques joined by one edge — the canonical 2-community graph."""
    return nx.barbell_graph(5, 1)


# ── translation ──────────────────────────────────────────────────────────────

def test_nx_to_igraph_round_trips_node_names_and_edges():
    g = three_cliques()
    ig = nx_to_igraph(g)
    assert ig.vcount() == g.number_of_nodes()
    assert ig.ecount() == g.number_of_edges()
    assert set(ig.vs["name"]) == set(g.nodes())
    assert ig.is_directed() is False


def test_nx_to_igraph_carries_the_named_weight():
    g = nx.Graph()
    g.add_edge("a", "b", weight=7.5)
    g.add_edge("b", "c")            # no weight attribute -> default 1.0
    ig = nx_to_igraph(g, weight="weight")
    weights = sorted(ig.es["weight"])
    assert weights == [1.0, 7.5]


def test_nx_to_igraph_omits_weight_attribute_when_not_requested():
    g = nx.Graph()
    g.add_edge("a", "b", weight=7.5)
    assert "weight" not in nx_to_igraph(g).es.attributes()


# ── §G2: Leiden ──────────────────────────────────────────────────────────────

def test_leiden_recovers_the_planted_communities():
    communities, q = leiden_partition(three_cliques(), seed=1)
    assert len(communities) == 3
    # Each planted clique must be wholly inside one recovered community.
    for base in (0, 10, 20):
        clique = {base + i for i in range(5)}
        assert any(clique <= c for c in communities), f"clique {base} was split"
    assert q > 0.3


def test_leiden_communities_are_connected_on_a_graph_where_they_are():
    """Leiden's guarantee — asserted, not assumed. Two cliques + one bridge."""
    communities, _ = leiden_partition(barbell(), seed=1)
    report = connectedness_report(barbell(), communities)
    assert report["all_connected"] is True
    assert report["disconnected"] == []
    assert report["n_multi_member"] == 2


def test_connectedness_report_can_fail():
    """Discriminating test: the check must be able to report a disconnected community.

    A check that has never been seen to fail proves nothing. Here the community is
    disconnected *by construction* (two 5-cliques with no edge between them), so a
    report that says `all_connected` has been neutered.
    """
    g = nx.Graph()
    g.add_edges_from((i, j) for i in range(5) for j in range(i + 1, 5))
    g.add_edges_from((10 + i, 10 + j) for i in range(5) for j in range(i + 1, 5))
    report = connectedness_report(g, [set(range(5)) | set(range(10, 15))])
    assert report["all_connected"] is False
    assert len(report["disconnected"]) == 1
    assert report["disconnected"][0]["size"] == 10


def test_leiden_ladder_moves_in_the_documented_direction():
    """0.5 = few broad communities, 2.0 = many tight ones (the syllabus's finite zoom)."""
    ladder = leiden_ladder(three_cliques(), resolutions=(0.5, 1.0, 2.0), seed=1)
    assert ladder[0.5]["n_communities"] <= ladder[2.0]["n_communities"]
    for resolution, row in ladder.items():
        assert row["connectivity"]["all_connected"] is True, f"resolution {resolution}"


def test_modularity_of_the_planted_partition_beats_a_degenerate_one():
    g = three_cliques()
    planted = [{0 + i for i in range(5)}, {10 + i for i in range(5)}, {20 + i for i in range(5)}]
    single = [set(g.nodes())]
    assert modularity(g, planted) > modularity(g, single)
    assert modularity(g, planted) > 0.3


# ── the null ─────────────────────────────────────────────────────────────────

def test_rewire_preserves_the_degree_sequence_and_changes_the_edges():
    g = three_cliques()
    h, preserved = rewire_degree_preserving(g, seed=7)
    assert preserved is True
    assert sorted(d for _, d in h.degree()) == sorted(d for _, d in g.degree())
    assert set(map(frozenset, h.edges())) != set(map(frozenset, g.edges()))


def test_rewired_null_scores_below_the_observed_partition():
    """The gate's whole premise: structure is a surplus over chance."""
    g = three_cliques()
    communities, q_observed = leiden_partition(g, seed=1)
    h, preserved = rewire_degree_preserving(g, seed=1)
    assert preserved
    _, q_null = leiden_partition(h, seed=1)
    assert q_observed > q_null


def test_rewire_is_deterministic_for_a_fixed_seed():
    g = three_cliques()
    a, _ = rewire_degree_preserving(g, seed=3)
    b, _ = rewire_degree_preserving(g, seed=3)
    assert set(map(frozenset, a.edges())) == set(map(frozenset, b.edges()))


# ── §G1: personalized PageRank ───────────────────────────────────────────────

def test_ppr_concentrates_on_the_seed_community():
    g = three_cliques()
    scores = personalized_pagerank(g, [0], lam=0.5, iterations=10)
    clique_a = {0, 1, 2, 3, 4}
    clique_c = {20, 21, 22, 23, 24}
    assert scores[0] == max(scores.values())
    assert min(scores[n] for n in clique_a) > max(scores[n] for n in clique_c)


def test_ppr_accepts_weighted_seeds_and_weights_pull_the_mass():
    g = three_cliques()
    uniform = personalized_pagerank(g, [0, 10], lam=0.5, iterations=10)
    weighted = personalized_pagerank(g, {0: 100.0, 10: 1.0}, lam=0.5, iterations=10)
    assert all(v > 0 for v in uniform.values())
    # Weighting the seed 100:1 must pull the mass toward clique A and away from C.
    assert weighted[0] / weighted[20] > uniform[0] / uniform[20]


def test_ppr_conserves_mass_on_a_regular_graph_only():
    """The spec's `W = D^-1 A` is row-stochastic, not doubly stochastic.

    So the iteration conserves total mass exactly when the graph is regular (where
    W happens to be doubly stochastic) and not otherwise. Asserted both ways, so
    the property is pinned rather than assumed.
    """
    regular = nx.cycle_graph(8)          # every node degree 2 -> W doubly stochastic
    scores = personalized_pagerank(regular, [0], lam=0.5, iterations=10)
    assert abs(sum(scores.values()) - 1.0) < 1e-9

    irregular = three_cliques()          # degrees 1..5 -> column sums are not 1
    scores = personalized_pagerank(irregular, [0], lam=0.5, iterations=10)
    assert sum(scores.values()) > 1.0    # measured 1.14 here; never normalised away


def test_ppr_raises_when_no_seed_is_a_node():
    with pytest.raises(ValueError, match="none of the"):
        personalized_pagerank(three_cliques(), ["not-a-concept"])


def test_ppr_isolated_nodes_never_accumulate_score():
    g = three_cliques()
    g.add_node("isolated")
    scores = personalized_pagerank(g, [0])
    assert scores["isolated"] == 0.0


def test_lambda_sweep_moves_in_the_documented_direction():
    """lam=0.9 'never leaves home' (seed's own community holds more mass than at lam=0.1)."""
    g = three_cliques()
    sweep = ppr_lambda_sweep(g, [0], lambdas=(0.1, 0.9), iterations=10)
    # The top-1 concept is the seed at both ends; the *gap* to a far node widens with lam.
    low = personalized_pagerank(g, [0], lam=0.1, iterations=10)
    high = personalized_pagerank(g, [0], lam=0.9, iterations=10)
    assert high[0] > low[0]
    assert high[20] < low[20]
    assert sweep[0.9][0][0] == 0 and sweep[0.1][0][0] == 0


# ── hub suppression ──────────────────────────────────────────────────────────

def test_hub_report_flags_a_global_centrality_ranking():
    """A hub-dominated ranking must be visible: seed the highest-degree node."""
    g = nx.Graph()
    g.add_edges_from((0, i) for i in range(1, 40))   # node 0 is the hub
    g.add_edges_from((40, 40 + i) for i in range(1, 10))
    scores = personalized_pagerank(g, [0])
    report = hub_suppression_report(g, scores, top=5)
    assert report["top_by_degree"][0]["name"] == 0
    assert report["n_overlap"] >= 1
    assert report["max_degree"] == 39
