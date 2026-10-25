#!/usr/bin/env python
"""PROBE — is the graph (multihop) lane REACHABLE and does it RETURN anything?

Why this probe exists
---------------------
`HANDOFF.md` (session 15, §5) records the graph lane as out of scope because *"Memgraph is DOWN —
7687 refused"*. That was measured by probing the **cluster** IPs (10.0.10.70 / 10.0.10.65), but the
code's default is `memgraph_host = "localhost"` (`config.py:238`) and `.env` sets
`MEMGRAPH_HOST=localhost` — the container `synapse_memgraph` (memgraph/memgraph:2.18.1) is **up** on
this machine with 7687 published. So the recorded blocker is **mis-scoped**, not real.

This probe answers the question that actually matters: **does the lane work end to end?**
It exercises the production path — `cluster_embedder.embed_query` → `GraphBuilder.graph_search`
→ `_find_concepts_scored` (Qdrant `concept_embeddings` ANN) → Memgraph Cypher → chunks.

⚠️ READ-ONLY: no writes to Memgraph or Qdrant, no LLM calls.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/graph_lane_probe.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.core.config import get_settings  # noqa: E402

QUERIES = REPO / "data" / "eval_queries_v2.json"
OUT = REPO / "logs" / "p1" / "step10" / "graph_lane_probe.json"


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
    print(f"memgraph: {cfg.memgraph_host}:{cfg.memgraph_port}   "
          f"qdrant: {cfg.qdrant_host or 'LOCAL'}  collection={cfg.qdrant_collection}")

    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.graph_builder import get_graph_builder

    qs = load_queries(QUERIES)
    print(f"queries loaded: {len(qs)}")
    kinds = Counter(q.get("query_type") or q.get("type") for q in qs)
    print(f"query types: {dict(kinds)}")

    multihop = [q for q in qs if (q.get("query_type") or q.get("type")) == "multihop"]
    sample = (multihop or qs)[:5]
    print(f"probing {len(sample)} {'multihop' if multihop else 'arbitrary'} queries\n")

    embedder = get_cluster_embedder(cfg)
    graph = get_graph_builder(cfg)

    rows = []
    for q in sample:
        text = q.get("query") or q.get("question") or ""
        qid = q.get("id") or q.get("query_id")
        vec = embedder.embed_query(text)
        concepts = graph._find_concepts_scored(vec, top_k=8)
        hits = graph.graph_search(text, cfg.global_tenant_id or "global",
                                  query_vector=vec, limit=5)
        rows.append({
            "query_id": qid,
            "query": text[:120],
            "concepts_resolved": [c for c, _ in concepts],
            "n_concepts_resolved": len(concepts),
            "n_hits": len(hits),
            "hits": [{"chunk_id": h["chunk_id"],
                      "matched_concepts": h.get("matched_concepts"),
                      "hop_distance": h.get("hop_distance"),
                      "concept_path": h.get("concept_path")} for h in hits],
        })
        print(f"[{qid}] {text[:70]!r}")
        print(f"    concepts resolved: {len(concepts)} -> {[c for c, _ in concepts][:5]}")
        print(f"    graph hits: {len(hits)}"
              + (f"  hop_distance={hits[0].get('hop_distance')}" if hits else ""))

    n_with_hits = sum(1 for r in rows if r["n_hits"] > 0)
    n_with_concepts = sum(1 for r in rows if r["n_concepts_resolved"] > 0)
    print(f"\nqueries with >=1 concept resolved: {n_with_concepts}/{len(rows)}")
    print(f"queries with >=1 graph hit:        {n_with_hits}/{len(rows)}")
    verdict = ("REACHABLE AND SERVING" if n_with_hits else
               "REACHABLE BUT RETURNING NOTHING" if n_with_concepts else
               "NOT SERVING — no concepts resolved")
    print(f"VERDICT: {verdict}")

    OUT.write_text(json.dumps({
        "probe": "graph_lane_probe",
        "memgraph": f"{cfg.memgraph_host}:{cfg.memgraph_port}",
        "qdrant": cfg.qdrant_host or "LOCAL",
        "collection": cfg.qdrant_collection,
        "queries_total": len(qs),
        "query_types": dict(kinds),
        "probed": rows,
        "n_with_concepts": n_with_concepts,
        "n_with_hits": n_with_hits,
        "verdict": verdict,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"artifact: {OUT}")
    return 0 if n_with_hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
