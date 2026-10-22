#!/usr/bin/env python
"""§G1 verifier 4 — the retrieval ABLATION: PPR ranking vs the current fixed-hop ranking.

Why this exists
---------------
`IMPROVEMENTS.md` §G1 and the §G plan's verifier 4, verbatim: *"the graph lane's
contribution to multihop retrieval, PPR vs the current fixed-hop ranking, on the v2 gold
set. **No claim without this.**"* The behaviour probe (`g1_ppr_probe.py`) measures what
the algorithm does; it cannot show the ranking is BETTER. This does.

The comparison, and what makes it a single-variable change
----------------------------------------------------------
Both arms see the SAME seeds (the query's top-8 concepts, exactly as
`GraphBuilder._find_concepts_scored(vec, 8)` produces them) and the SAME candidate chunks
(every chunk mentioning >= 1 of those concepts, within the content page window). The only
difference is the number the chunks are ranked by:

  * **fixed-hop** — production `graph_search`'s own ORDER BY: `matched_concepts` DESC,
    then `sum(c.score)` DESC (the raw concept-similarity sum). This is what ships today.
  * **PPR** — the sum of the *propagated* score, `personalized_pagerank(G, seeds, lam=1/2,
    10 iterations)` over the weighted `RELATES_TO` adjacency, evaluated at each chunk's
    matched concepts.

`matched_concepts` is deliberately NOT a primary key in the PPR arm: §I32 measured that
**97.86 %** of matching chunks tie at exactly 1 matched concept, so that key is nearly
constant and using it would hide the thing under test.

⚠️ Read the POWER block before quoting any number
-------------------------------------------------
The graph lane's candidate pool is TINY — median **7.5** candidate chunks / **6.5** candidate
pages per query (min 2, max 101 chunks). A page-level Recall@20 therefore has nothing to rank:
when a query has fewer than 20 candidate pages the top-20 cut returns the entire pool, both arms
return the same set, and the metric is identical **by construction**. The artifact reports, per k,
how many queries the cut actually bites on (`cut_bites_at_k`). A k where that count is small cannot
discriminate, and a null result at such a k is uninformative rather than negative.
⚠️ Do not restate those medians from this docstring — quote `meta.power` in the artifact, which is
the frozen record. An earlier revision of this line said "median 7" (a rounding artifact of the
audit that produced it) and disagreed with the artifact's own 7.5.

⚠️ What this ablation does NOT test
-----------------------------------
It compares two RANKINGS over the same candidate set. PPR's other possible lever is
**candidate expansion** — chunks that mention no seed concept but are graph-near. That is a
different treatment, it is not what §G1's verifier 4 specifies, and it is NOT measured
here. Do not read a null result here as "PPR is useless"; read it as "re-ranking alone, on
this graph, at this pool size, does not move the number".

Two seed sets, because of a real confound
-----------------------------------------
`concept_embeddings` on the cluster holds **15,276** points while the current graph holds
**7,834** concepts — the collection accumulates across ingests and its payload carries no
document id, so the ANN cannot be scoped. A top-8 seed can therefore name a concept that
does not exist in the graph. That degrades BOTH arms equally, so the **delta is still
valid**, but it lowers the absolute numbers. Both seed sets are run; expect them to agree
exactly, because a seed absent from the graph matches no node in either arm — that
agreement is the evidence the confound is inert, and it is reported rather than assumed.

⚠️ This runs on the graph as it stands — **before the §I21 filter is applied and the graph
is rebuilt**. It is a before-arm for that rebuild, and §G3's merges would move it again.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/g1_ppr_ablation.py
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import httpx  # noqa: E402
import numpy as np  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.graph_analytics import personalized_pagerank  # noqa: E402
from src.pdf_ingestion.graph_builder import GraphBuilder  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
TOP_K_CONCEPTS = 8        # graph_builder.graph_search: `_find_concepts_scored(vec, top_k=8)`
KS = (3, 5, 10, 20)       # the headline cut is 20 (B6); the smaller ones are the ones that bite
HEADLINE_K = 20
SCORE_DP = 6
LAM = 0.5
ITERATIONS = 10

# graph_search's ranking Cypher (graph_builder.py:449-459) with `page_number` added — the
# ablation needs the page to score against the gold labels. The ORDER BY is reproduced in
# Python so the tie-break is explicit and deterministic.
_RANK_CYPHER = """
UNWIND $concepts AS c
MATCH (k:Concept {name: c.name})
MATCH (ch:Chunk)-[:MENTIONS]->(k)
WHERE ch.tenant_id IN [$tenant_id, 'global']
WITH ch, collect(DISTINCT k.name) AS matched, sum(c.score) AS concept_score
RETURN ch.id AS chunk_id, ch.page_number AS page_number,
       matched AS concept_path, size(matched) AS matched_concepts, concept_score
"""


def embed_nomic(client: httpx.Client, url: str, model: str, text: str, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            r = client.post(url, json={"model": model, "input": [text]})
            r.raise_for_status()
            items = sorted(r.json()["data"], key=lambda it: it.get("index", 0))
            return [float(x) for x in items[0]["embedding"]]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"embed failed for {text!r}: {last}")


def load_concept_graph(cfg):
    """The weighted RELATES_TO concept adjacency, from the live Memgraph."""
    import networkx as nx

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
    finally:
        driver.close()
    g = nx.Graph()
    for r in rows:
        if r["a"] != r["b"]:
            g.add_edge(r["a"], r["b"], weight=float(r["w"] or 1.0))
    return g


def pages_in_rank_order(rows: list[dict]) -> list[int]:
    """Distinct page numbers in rank order — a page scores once, at its best chunk's rank."""
    seen, out = set(), []
    for r in rows:
        pg = r.get("page_number")
        if pg is None or pg in seen:
            continue
        seen.add(pg)
        out.append(int(pg))
    return out


def page_metrics(ranked_pages: list[int], relevant: set[int], ks=KS) -> dict:
    """Recall at each k, Hit@headline, and reciprocal rank of the first relevant page."""
    rr = 0.0
    for i, p in enumerate(ranked_pages, 1):
        if p in relevant:
            rr = 1.0 / i
            break
    out = {
        "recall_at": {str(k): (len({p for p in ranked_pages[:k]} & relevant) / len(relevant))
                      if relevant else None for k in ks},
        "hit": 1.0 if any(p in relevant for p in ranked_pages[:HEADLINE_K]) else 0.0,
        "rr": rr,
        "n_pages_retrieved": len(ranked_pages),
    }
    return out


def paired_ci(diffs: list[float]) -> dict:
    """mean +/- 1.96*SD/sqrt(n) — the repo's convention (required_n.py prints no CI)."""
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None}
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(mean, 6), "sd": round(sd, 6),
            "ci95": [round(mean - half, 6), round(mean + half, 6)],
            "resolved": bool((mean - half) > 0 or (mean + half) < 0)}


def summarise_arm(usable: list[dict], arm: str, ks=KS) -> dict:
    f_r = [r["arms"]["production"]["fixed"]["recall_at"] for r in usable]
    p_r = [r["arms"]["production"][arm]["recall_at"] for r in usable]
    f_m = [r["arms"]["production"]["fixed"]["rr"] for r in usable]
    p_m = [r["arms"]["production"][arm]["rr"] for r in usable]
    f_h = [r["arms"]["production"]["fixed"]["hit"] for r in usable]
    p_h = [r["arms"]["production"][arm]["hit"] for r in usable]
    d_m = [p - f for p, f in zip(p_m, f_m)]
    out = {
        "queries": len(usable),
        "mrr": {"fixed": round(statistics.mean(f_m), 6), "ppr": round(statistics.mean(p_m), 6)},
        "mrr_paired_delta_ppr_minus_fixed": paired_ci(d_m),
        "hit20": {"fixed": round(statistics.mean(f_h), 6), "ppr": round(statistics.mean(p_h), 6)},
        "recall_at": {}, "recall_at_paired_delta": {}, "cut_bites_at_k": {},
        "mrr_win_loss_tie": {
            "ppr_better": sum(1 for d in d_m if d > 1e-12),
            "fixed_better": sum(1 for d in d_m if d < -1e-12),
            "identical": sum(1 for d in d_m if abs(d) <= 1e-12),
        },
    }
    for k in ks:
        key = str(k)
        fv = [x[key] for x in f_r]
        pv = [x[key] for x in p_r]
        d = [p - f for p, f in zip(pv, fv)]
        out["recall_at"][key] = {"fixed": round(statistics.mean(fv), 6),
                                 "ppr": round(statistics.mean(pv), 6)}
        out["recall_at_paired_delta"][key] = paired_ci(d)
        # how many queries have MORE candidate pages than k — i.e. the cut can change the set
        out["cut_bites_at_k"][key] = sum(
            1 for r in usable
            if r["arms"]["production"]["fixed"]["n_pages_retrieved"] > k
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/g1_ppr_ablation.json")
    ap.add_argument("--query-type", default="multihop",
                    help="gold query_type to evaluate (default multihop); 'all' for every answerable query")
    ap.add_argument("--limit", type=int, default=0, help="0 = all selected queries")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force — a registered artifact "
              f"must not be clobbered by accident.", file=sys.stderr)
        return 4

    cfg = get_settings()
    with open(QUERIES, encoding="utf-8") as fh:
        raw = json.load(fh)
    queries = [q for q in raw if q.get("id") and q.get("id") != "_note"]
    queries = [q for q in queries if q.get("answerable", True)]
    if args.query_type != "all":
        queries = [q for q in queries if q.get("query_type") == args.query_type]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("ABORT: no queries selected — writing nothing.", file=sys.stderr)
        return 3

    graph = load_concept_graph(cfg)
    if graph.number_of_nodes() == 0:
        print("ABORT: the concept graph is empty — writing nothing.", file=sys.stderr)
        return 3
    print(f"concept graph: {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")

    gb = GraphBuilder(cfg)
    tenant = cfg.global_tenant_id
    lo, hi = cfg.min_content_page, cfg.max_content_page

    results: list[dict] = []
    t0 = time.time()
    with httpx.Client(timeout=60.0) as client:
        for i, q in enumerate(queries, 1):
            qid, text = q["id"], q["query"]
            relevant = {int(p) for p in (q.get("relevant_pages") or [])}
            if not relevant:
                continue
            vec = embed_nomic(client, cfg.sv_embed_url, cfg.embedding_model, text)
            scored = gb._find_concepts_scored(  # noqa: SLF001 — production parity
                np.asarray(vec, dtype="float32"), top_k=TOP_K_CONCEPTS
            )
            if not scored:
                results.append({"id": qid, "error": "no concepts resolved"})
                continue

            with gb._get_driver().session() as s:  # noqa: SLF001
                rows = s.run(
                    _RANK_CYPHER,
                    concepts=[{"name": n, "score": round(sc, SCORE_DP)} for n, sc in scored],
                    tenant_id=tenant,
                ).data()
            rows = [r for r in rows
                    if r.get("page_number") is not None and lo <= int(r["page_number"]) <= hi]

            absent = [n for n, _ in scored if n not in graph]
            arms = {}
            for seed_name, seeds in (("production", {n: sc for n, sc in scored}),
                                     ("graph_restricted",
                                      {n: sc for n, sc in scored if n in graph})):
                if not seeds:
                    arms[seed_name] = {"skipped": "no seed present in the graph"}
                    continue
                ppr = personalized_pagerank(graph, seeds, lam=LAM, iterations=ITERATIONS,
                                            weight="weight")

                fixed = sorted(rows, key=lambda r: (-r["matched_concepts"],
                                                    -round(r["concept_score"], SCORE_DP),
                                                    str(r["chunk_id"])))
                # PPR arm: rank by the PROPAGATED score only. `matched_concepts` is nearly
                # constant (§I32: 97.86 % tie at 1) and would mask the effect under test.
                ppr_ranked = sorted(
                    rows,
                    key=lambda r: (-round(sum(ppr.get(c, 0.0) for c in r["concept_path"]), 12),
                                   str(r["chunk_id"])),
                )
                arms[seed_name] = {
                    "seeds": len(seeds),
                    "n_candidates": len(rows),
                    "fixed": page_metrics(pages_in_rank_order(fixed), relevant),
                    "ppr": page_metrics(pages_in_rank_order(ppr_ranked), relevant),
                    "top20_pages_fixed": pages_in_rank_order(fixed)[:HEADLINE_K],
                    "top20_pages_ppr": pages_in_rank_order(ppr_ranked)[:HEADLINE_K],
                }

            results.append({
                "id": qid,
                "query": text,
                "query_type": q.get("query_type"),
                "n_relevant": len(relevant),
                "top8_concepts": [n for n, _ in scored],
                "top8_absent_from_graph": absent,
                "arms": arms,
            })
            if i % 10 == 0:
                print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    gb.close()

    ok = [r for r in results if "error" not in r and r["arms"]
          and not r["arms"]["production"].get("skipped")]
    if not ok:
        print("\nABORT: no query produced a comparison — NOT writing the artifact.", file=sys.stderr)
        return 3

    summary = {
        "production_seeds": summarise_arm(ok, "ppr"),
        "graph_restricted_seeds": summarise_arm(ok, "ppr"),
    }
    # The two seed sets are expected to agree exactly (an absent seed matches no node in
    # either arm). Verify that rather than assert it.
    same = all(
        r["arms"]["production"]["fixed"] == r["arms"]["graph_restricted"]["fixed"]
        and r["arms"]["production"]["ppr"] == r["arms"]["graph_restricted"]["ppr"]
        for r in ok
    )
    n_cand = [r["arms"]["production"]["n_candidates"] for r in ok]
    n_pages = [r["arms"]["production"]["fixed"]["n_pages_retrieved"] for r in ok]
    absent_counts = [len(r["top8_absent_from_graph"]) for r in ok]

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/g1_ppr_ablation.py",
            "what": "§G1 verifier 4 — PPR ranking vs the current fixed-hop ranking (the ablation)",
            "query_type": args.query_type,
            "queries_file": QUERIES,
            "n_queries": len(ok),
            "ks": list(KS),
            "headline_k": HEADLINE_K,
            "lam": LAM,
            "iterations": ITERATIONS,
            "ppr_weight": "weight",
            "content_page_window": [lo, hi],
            "embed_model": cfg.embedding_model,
            "embed_dim": cfg.embedding_dim,
            "concept_collection": cfg.concept_collection,
            "graph": f"{cfg.memgraph_host}:{cfg.memgraph_port}",
            "no_llm_calls": True,
            "graph_state": ("the graph BEFORE the §I21 content filter is applied and it is "
                            "rebuilt — a before-arm for that rebuild, and §G3's merges would "
                            "move it again"),
            "power": {
                "why_it_matters": ("the graph lane's candidate pool is tiny, so a page-level "
                                   "Recall@k is inert at any k larger than the pool: the cut "
                                   "returns the whole set and BOTH ARMS ARE IDENTICAL BY "
                                   "CONSTRUCTION. `cut_bites_at_k[k]` counts the queries where "
                                   "the cut can actually change the retrieved set. A k with a "
                                   "small count cannot discriminate, and a null result there is "
                                   "UNINFORMATIVE, not negative."),
                "n_candidates_chunks": {"min": min(n_cand), "median": statistics.median(n_cand),
                                        "max": max(n_cand)},
                "n_candidate_pages": {"min": min(n_pages), "median": statistics.median(n_pages),
                                      "max": max(n_pages)},
                "cut_bites_at_k": {str(k): sum(1 for n in n_pages if n > k) for k in KS},
            },
            "not_tested": ("candidate EXPANSION (chunks that mention no seed concept but are "
                           "graph-near). §G1's verifier 4 specifies a ranking comparison, and "
                           "that is what this is; a null result here is NOT evidence that PPR "
                           "cannot help the lane."),
            "seed_confound": {
                "note": ("concept_embeddings accumulates across ingests and carries no "
                         "document id, so a top-8 seed can name a concept absent from the "
                         "current graph. Both arms see the same seeds, so the DELTA is "
                         "unaffected; the absolute numbers are."),
                "top8_absent_from_graph": {
                    "mean": round(statistics.mean(absent_counts), 4),
                    "max": max(absent_counts),
                    "queries_with_any_absent": sum(1 for c in absent_counts if c > 0),
                },
                "the_two_seed_sets_agree_exactly": same,
                "why": ("a seed absent from the graph matches no Concept node in the ranking "
                        "Cypher and is skipped by personalized_pagerank, so restricting the "
                        "seed set to the graph cannot change either arm. Agreement is the "
                        "evidence the confound is INERT here."),
            },
        },
        "summary": summary,
        "queries": sorted(results, key=lambda r: r["id"]),
    }
    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    p = summary["production_seeds"]
    print(f"\n=== §G1 ablation: PPR vs fixed-hop ({args.query_type}, n={len(ok)}) ===")
    print(f"  pool: median {statistics.median(n_cand):.1f} candidate chunks, "
          f"median {statistics.median(n_pages):.1f} candidate pages")
    print(f"  cut bites at: " + "  ".join(
        f"k={k}: {p['cut_bites_at_k'][str(k)]}/{len(ok)}" for k in KS))
    print(f"  MRR  fixed {p['mrr']['fixed']:.4f} -> ppr {p['mrr']['ppr']:.4f}   "
          f"delta {p['mrr_paired_delta_ppr_minus_fixed']['mean']:+.4f}  "
          f"CI95 [{p['mrr_paired_delta_ppr_minus_fixed']['ci95'][0]:+.4f}, "
          f"{p['mrr_paired_delta_ppr_minus_fixed']['ci95'][1]:+.4f}]  "
          f"{'RESOLVED' if p['mrr_paired_delta_ppr_minus_fixed']['resolved'] else 'UNRESOLVED'}"
          f"  W/L/T {p['mrr_win_loss_tie']['ppr_better']}/"
          f"{p['mrr_win_loss_tie']['fixed_better']}/{p['mrr_win_loss_tie']['identical']}")
    for k in KS:
        d = p["recall_at_paired_delta"][str(k)]
        print(f"  R@{k:<2} fixed {p['recall_at'][str(k)]['fixed']:.4f} -> "
              f"ppr {p['recall_at'][str(k)]['ppr']:.4f}   delta {d['mean']:+.4f}  "
              f"CI95 [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}  "
              f"(bites {p['cut_bites_at_k'][str(k)]}/{len(ok)})")
    print(f"  seed sets agree exactly: {same}   "
          f"top8 seeds absent from graph: mean {statistics.mean(absent_counts):.2f}/8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
