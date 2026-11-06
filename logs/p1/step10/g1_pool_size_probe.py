"""§G1/§G5 pool-size probe — READ-ONLY. How big is the graph lane's candidate pool at hops=1
(shipped) vs the 2-hop expansion, and does a page-level cut finally BITE?

The original §G1 ablation was inert because the single-hop pool was median 7.5 chunks / 6.5 pages
per query — a page-level R@20 returned the whole pool and both arms tied by construction. This
measures whether the expansion makes the pool big enough for a page-level metric to discriminate.

Pool definition replicates `g1_ppr_ablation._RANK_CYPHER`: chunks mentioning >= 1 of the query's
top-8 concepts, filtered to the content page window [min_content_page, max_content_page].
Expanded = chunks mentioning any concept within `*0..2` RELATES_TO edges of a seed.

No writes, no LLM. Writes logs/p1/step10/g1_pool_size_probe.json.
Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
    .venv/bin/python -u logs/p1/step10/g1_pool_size_probe.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
from src.core.config import get_settings  # noqa: E402

QUERIES = REPO / "data" / "eval_queries_v2.json"
OUT = REPO / "logs" / "p1" / "step10" / "g1_pool_size_probe.json"
TOP_K = 8
KS = [3, 5, 10, 20]

SHIPPED_CYPHER = """
UNWIND $concepts AS c
MATCH (k:Concept {name: c.name})
MATCH (ch:Chunk)-[:MENTIONS]->(k)
WHERE ch.tenant_id IN [$tenant_id, 'global']
RETURN DISTINCT ch.id AS chunk_id, ch.page_number AS page_number
"""

# ⚠️ Level-by-level BFS, NOT `MATCH p = (k)-[:RELATES_TO*0..2]-(n)`. The path-enumeration form
# enumerates EVERY length-≤2 path and blows up on a high-degree seed (measured 2026-11-05: some
# seed sets did not return in minutes; the DISTINCT neighbour query is 0.2-0.4 s). Bounded and
# identical in RESULT (the reached node set), so the pool is the same.
NEIGHBOURS_CYPHER = """
MATCH (k:Concept)-[:RELATES_TO]-(n:Concept)
WHERE k.name IN $names
RETURN DISTINCT n.name AS name
"""

CHUNKS_OF_NAMES_CYPHER = """
UNWIND $names AS nm
MATCH (k:Concept {name: nm})
MATCH (ch:Chunk)-[:MENTIONS]->(k)
WHERE ch.tenant_id IN [$tenant_id, 'global']
RETURN DISTINCT ch.id AS chunk_id, ch.page_number AS page_number
"""


def load_queries(path: Path) -> list[dict]:
    d = json.loads(path.read_text())
    if isinstance(d, dict):
        for k in ("queries", "data", "items"):
            if k in d:
                d = d[k]
                break
    return d


def main() -> int:
    cfg = get_settings()
    lo, hi = cfg.min_content_page, cfg.max_content_page
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.graph_builder import GraphBuilder

    qs = [q for q in load_queries(QUERIES)
          if (q.get("query_type") or q.get("type")) == "multihop" and q.get("relevant_pages")]
    print(f"multihop queries with labels: {len(qs)}  page window [{lo},{hi}]")

    embedder = get_cluster_embedder(cfg)
    gb = GraphBuilder(cfg)
    drv = gb._get_driver()

    rows = []
    t0 = time.time()
    for q in qs:
        vec = np.asarray(embedder.embed_query(q["query"]), dtype="float32")
        seeds = gb._find_concepts_scored(vec, top_k=TOP_K, query_text=q["query"])
        if not seeds:
            rows.append({"id": q["id"], "error": "no concepts resolved"})
            continue
        seed_names = [n for n, _ in seeds]
        params = {"concepts": [{"name": n, "score": round(s, 6)} for n, s in seeds],
                  "tenant_id": cfg.global_tenant_id}
        tq = time.monotonic()
        with drv.session() as s:
            ship = s.run(SHIPPED_CYPHER, **params).data()
            hop1 = [r["name"] for r in s.run(NEIGHBOURS_CYPHER, names=seed_names).data()]
            seen1 = set(seed_names)
            reached1 = seed_names + [n for n in hop1 if n not in seen1]
            hop2 = [r["name"] for r in s.run(NEIGHBOURS_CYPHER, names=hop1).data()]
            seen2 = set(reached1)
            reached2 = reached1 + [n for n in hop2 if n not in seen2]
            exp = s.run(CHUNKS_OF_NAMES_CYPHER, names=reached2,
                        tenant_id=cfg.global_tenant_id).data()
        f = lambda rs: [r for r in rs if r.get("page_number") is not None
                        and lo <= int(r["page_number"]) <= hi]
        ship, exp = f(ship), f(exp)
        with drv.session() as s:
            exp1 = f(s.run(CHUNKS_OF_NAMES_CYPHER, names=reached1,
                           tenant_id=cfg.global_tenant_id).data())
        ship_pages = sorted({int(r["page_number"]) for r in ship})
        exp_pages = sorted({int(r["page_number"]) for r in exp})
        exp1_pages = sorted({int(r["page_number"]) for r in exp1})
        rows.append({
            "id": q["id"], "n_seeds": len(seeds),
            "shipped": {"n_chunks": len(ship), "n_pages": len(ship_pages), "pages": ship_pages},
            "expanded_1hop": {"n_chunks": len(exp1), "n_pages": len(exp1_pages)},
            "expanded": {"n_chunks": len(exp), "n_pages": len(exp_pages), "pages": exp_pages},
            "pages_added": len(set(exp_pages) - set(ship_pages)),
        })
        print(f"  {q['id']}: shipped {len(ship)}c/{len(ship_pages)}p  "
              f"1hop {len(exp1)}c/{len(exp1_pages)}p  "
              f"2hop {len(exp)}c/{len(exp_pages)}p  "
              f"(+{len(set(exp_pages)-set(ship_pages))}p) [{time.monotonic()-tq:.1f}s]")

    ok = [r for r in rows if "error" not in r]
    ship_p = [r["shipped"]["n_pages"] for r in ok]
    exp_p = [r["expanded"]["n_pages"] for r in ok]
    exp1_p = [r["expanded_1hop"]["n_pages"] for r in ok]

    def bites(pages): return {str(k): sum(1 for n in pages if n > k) for k in KS}
    art = {
        "meta": {"what": "§G1/§G5 pool size — shipped vs 2-hop expanded, page-level",
                 "queries_file": str(QUERIES.name), "n_queries": len(ok),
                 "page_window": [lo, hi], "top_k_concepts": TOP_K,
                 "qdrant": cfg.qdrant_host, "collection": cfg.qdrant_collection,
                 "graph": f"{cfg.memgraph_host}:{cfg.memgraph_port}",
                 "read_only": True, "wall_s": round(time.time() - t0, 1)},
        "shipped": {"n_pages": {"min": min(ship_p), "median": statistics.median(ship_p),
                                "max": max(ship_p), "mean": round(statistics.mean(ship_p), 2)},
                    "cut_bites_at_k": bites(ship_p)},
        "expanded_1hop": {"n_pages": {"min": min(exp1_p), "median": statistics.median(exp1_p),
                                      "max": max(exp1_p), "mean": round(statistics.mean(exp1_p), 2)},
                          "cut_bites_at_k": bites(exp1_p)},
        "expanded": {"n_pages": {"min": min(exp_p), "median": statistics.median(exp_p),
                                 "max": max(exp_p), "mean": round(statistics.mean(exp_p), 2)},
                     "cut_bites_at_k": bites(exp_p)},
        "queries_gaining_pages": sum(1 for r in ok if r["pages_added"] > 0),
        "rows": rows,
    }
    OUT.write_text(json.dumps(art, indent=2) + "\n")
    print(f"\nshipped pages       median {statistics.median(ship_p)}  bites {bites(ship_p)}")
    print(f"expanded 1-hop pages median {statistics.median(exp1_p)}  bites {bites(exp1_p)}")
    print(f"expanded 2-hop pages median {statistics.median(exp_p)}  bites {bites(exp_p)}")
    print(f"queries gaining pages: {art['queries_gaining_pages']}/{len(ok)}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
