#!/usr/bin/env python
"""§G1 — personalized PageRank over the concept adjacency. 2026-10-21.

What this is
------------
`IMPROVEMENTS.md` §G1: *"the course's answer to 'which concepts actually matter for
this query'. Replaces the current fixed-hop walk."* The current walk does not walk —
`hop_distance` is a constant 0 (§I2).

The iteration is the syllabus's, verbatim (`Week_Plan/week-5-summer-lesson-plan.pdf`,
"The Honey and the Springs"):

    W = D^-1 A                 # "split, don't dump — share along your edges in
                               #  weighted proportion"
    v(k+1) = (1 - lam) W v(k) + lam v(0),    lam = 1/2,    ten rounds

*"With lam = 1/2 and ten rounds, (0.5)^10 = 1/1024 — a tenth of a percent. You do not
iterate many times."* The syllabus also asks for the lambda sweep to be **reported**
(*"at lam = 0.1 the honey wanders; at lam = 0.9 it never leaves home"*), which is the
check that 1/2 is the middle it claims to be.

What this probe measures (and what it does NOT)
-----------------------------------------------
It measures the **algorithm's behaviour on the live graph**: the score distribution,
the hop decay (the syllabus's *"52% of the energy stays on the seed, 29% reaches its
neighbours, 16% the second hop — 97% within two hops"*), the lambda sweep, and hub
suppression — *"a PPR top-20 dominated by the highest-degree nodes means the
personalization is not doing its job."*

It does **NOT** run the retrieval ablation (PPR vs the fixed-hop ranking on the v2 gold
set). That needs the query->concept resolution path — a 768d query embedding against
`Concept.embedding` via the cluster embedder (§I12) — and the cluster is unreachable
while the lab tunnel is down. The ablation is recorded as DEFERRED in the artifact, not
silently omitted, and §G1 is not claimable until it runs.

Seeding without the cluster
---------------------------
Seeds are given by NAME (default: the eight concepts §I32 measured for `gold-062`, so
this is directly comparable to that baseline). A name that is not a node is reported as
missing rather than dropped silently — a probe that resolves nothing must not look like
a probe that found nothing.

Run:
    unset PYTHONPATH && uv run python logs/p1/step10/g1_ppr_probe.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import networkx as nx  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.graph_analytics import (  # noqa: E402
    hub_suppression_report,
    personalized_pagerank,
    ppr_lambda_sweep,
)

# The eight concepts §I32 measured as `gold-062`'s top-8 — one concept in three
# spellings plus near-synonyms, which is exactly why the current ranking ties at 1.
DEFAULT_SEEDS = [
    "Kinetic energy of gas particles",
    "total energy equals kinetic energy for monatomic gas",
    "total energy of a particle",
    "Total energy of a particle",
    "Kinetic energy",
    "kinetic energy",
    "Kinetic Energy",
    "kinetic theory of gases",
]

LAM = 0.5
ITERATIONS = 10
LAMBDAS = (0.1, 0.3, 0.5, 0.7, 0.9)


def load_relates_to(cfg) -> tuple[list[tuple[str, str, float]], list[str]]:
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
            docs = [r["id"] for r in s.run("MATCH (d:Document) RETURN d.id AS id").data()]
    finally:
        driver.close()
    return [(r["a"], r["b"], float(r["w"] or 1.0)) for r in rows], sorted(docs)


def build_graph(edges: list[tuple[str, str, float]]) -> nx.Graph:
    g = nx.Graph()
    for a, b, w in edges:
        if a != b:
            g.add_edge(a, b, weight=w)
    return g


def hop_decay(g: nx.Graph, seeds: list[str], scores: dict) -> dict:
    """Fraction of the total score at each hop distance from the nearest seed.

    The syllabus's reading of lam = 1/2 is that the honey *"glazes a one-or-two-hop
    neighbourhood before the leash yanks it back"*. This is that claim, measured.
    """
    depth = {}
    for seed in seeds:
        if seed not in g:
            continue
        for node, d in nx.single_source_shortest_path_length(g, seed, cutoff=4).items():
            depth[node] = min(depth.get(node, 99), d)
    total = sum(scores.values())
    buckets = {"hop0_seed": 0.0, "hop1": 0.0, "hop2": 0.0, "hop3_plus": 0.0, "unreached": 0.0}
    counts = {k: 0 for k in buckets}
    for node, score in scores.items():
        d = depth.get(node)
        key = "unreached" if d is None else (
            "hop0_seed" if d == 0 else "hop1" if d == 1 else "hop2" if d == 2 else "hop3_plus"
        )
        buckets[key] += score
        counts[key] += 1
    return {
        "mass_fraction": {k: round(v / total, 4) if total else 0.0 for k, v in buckets.items()},
        "node_counts": counts,
        "within_two_hops_mass_fraction": round(
            (buckets["hop0_seed"] + buckets["hop1"] + buckets["hop2"]) / total, 4
        ) if total else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/g1_ppr_probe.json")
    ap.add_argument("--seeds", nargs="*", default=None,
                    help="seed concept names (default: the §I32 gold-062 top-8)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing artifact (refused by default)")
    args = ap.parse_args()

    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.")
        return 2

    cfg = get_settings()
    edges, graph_docs = load_relates_to(cfg)
    if not edges:
        print("ABORT: no RELATES_TO edges — writing nothing.")
        return 3
    g = build_graph(edges)
    print(f"graph: {g.number_of_nodes():,} nodes, {g.number_of_edges():,} undirected edges")

    requested = args.seeds or DEFAULT_SEEDS
    matched = [s for s in requested if s in g]
    missing = [s for s in requested if s not in g]
    print(f"seeds: {len(matched)}/{len(requested)} resolved; missing = {missing}")
    if not matched:
        print("ABORT: no seed concept is a node of the graph — writing nothing "
              "(a probe that resolves nothing must not look like one that found nothing).")
        return 4

    scores = personalized_pagerank(g, matched, lam=LAM, iterations=ITERATIONS, weight="weight")
    total = sum(scores.values())
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    hubs = hub_suppression_report(g, scores, top=20)
    decay = hop_decay(g, matched, scores)
    sweep = ppr_lambda_sweep(g, matched, lambdas=LAMBDAS, iterations=ITERATIONS,
                             weight="weight", top=10)

    print(f"sum(v) = {total:.6f}  (W = D^-1 A is row-stochastic, not doubly stochastic, so "
          f"mass is not conserved on a non-regular graph — the spec's own behaviour)")
    print(f"hop decay: {decay['mass_fraction']}  within-two-hops = "
          f"{decay['within_two_hops_mass_fraction']}")
    print(f"hub overlap (top-20 PPR vs top-20 degree): {hubs['n_overlap']}")
    print("top-10 by PPR:")
    for name, score in ranked[:10]:
        print(f"   {score:.8f}  deg={g.degree(name):4}  {name}")

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/g1_ppr_probe.py",
            "what": "§G1 personalized PageRank over the RELATES_TO adjacency (behaviour probe)",
            "graph_source": f"memgraph {cfg.memgraph_host}:{cfg.memgraph_port} RELATES_TO",
            "graph_document_ids": graph_docs,
            "transition": "W = D^-1 A, row-normalised (the syllabus's 'split, don't dump')",
            "iteration": "v(k+1) = (1-lam) W v(k) + lam v(0)",
            "lam": LAM,
            "iterations": ITERATIONS,
            "weight": "weight (RELATES_TO co-occurrence count)",
            "source": "Week_Plan/week-5-summer-lesson-plan.pdf — 'The Honey and the Springs'",
            "no_llm_calls": True,
            "no_reingest": True,
        },
        "graph": {
            "nodes": g.number_of_nodes(),
            "undirected_edges": g.number_of_edges(),
            "components": nx.number_connected_components(g),
        },
        "seeds": {
            "requested": requested,
            "matched": matched,
            "missing": missing,
        },
        "distribution": {
            "sum": round(total, 6),
            "mass_conserved": abs(total - 1.0) < 1e-9,
            "note": ("W = D^-1 A is row-stochastic. Total mass is conserved only where W is "
                     "also doubly stochastic (a regular graph); on this graph it is not, and "
                     "that is the specified iteration, not a defect."),
            "n_nonzero": sum(1 for v in scores.values() if v > 0),
            "max": round(ranked[0][1], 8),
            "median_nonzero": round(
                sorted(v for v in scores.values() if v > 0)[
                    sum(1 for v in scores.values() if v > 0) // 2], 10),
        },
        "top_20_by_ppr": [
            {"name": n, "score": round(s, 8), "degree": g.degree(n)} for n, s in ranked[:20]
        ],
        "hub_suppression": hubs,
        "hop_decay": decay,
        "lambda_sweep": {str(k): v for k, v in sweep.items()},
        "deferred": {
            "retrieval_ablation": (
                "NOT RUN — PPR vs the current fixed-hop ranking on the v2 gold set requires "
                "query->concept resolution (768d query embedding against Concept.embedding via "
                "the cluster embedder, §I12) and the lab cluster is unreachable while the tunnel "
                "is down. §G1's verifier 4 ('no claim without this') is therefore UNMET, and "
                "§G1 must not be reported as done until it runs."
            ),
        },
    }
    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
