"""§G5/§I2 BEHAVIOUR PROBE — read-only. Does the traversal actually traverse on the LIVE graph?

Runs the production path (`cluster_embedder.embed_query` → `GraphBuilder.graph_search`) at
`graph_max_hops` = 1 (shipped) and 2, with a WIDE limit so the expansion's tail is visible, and
reports per query:
  * the hop_distance distribution (the §I2 defect was a CONSTANT 0);
  * how many chunks the expansion ADDS that the shipped hop-1 set never reaches (the plan's
    verifier: "a query requiring two hops retrieves a page neither one-hop endpoint reaches");
  * a concrete example chunk reachable only at hop >= 1, and the per-call wall time.

⚠️ READ-ONLY: no Memgraph or Qdrant writes, no LLM calls. Writes an artifact JSON.
Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
    .venv/bin/python -u logs/p1/step10/graph_multihop_probe.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.core.config import get_settings  # noqa: E402

QUERIES = REPO / "data" / "eval_queries_v2.json"
OUT = REPO / "logs" / "p1" / "step10" / "graph_multihop_probe.json"
SAMPLE = 8
WIDE = 500          # wide enough that the expansion's tail is in the returned list


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
    print(f"memgraph {cfg.memgraph_host}:{cfg.memgraph_port}  qdrant {cfg.qdrant_host} "
          f"collection={cfg.qdrant_collection}  default graph_max_hops={cfg.graph_max_hops}")

    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.graph_builder import GraphBuilder

    qs = load_queries(QUERIES)
    multihop = [q for q in qs if (q.get("query_type") or q.get("type")) == "multihop"]
    sample = (multihop or qs)[:SAMPLE]
    print(f"{len(qs)} queries, {len(multihop)} multihop; probing {len(sample)}\n")

    embedder = get_cluster_embedder(cfg)
    builders = {h: GraphBuilder(cfg.model_copy(update={"graph_max_hops": h})) for h in (1, 2)}

    rows, agg = [], Counter()
    for q in sample:
        text = q.get("query") or q.get("question") or ""
        qid = q.get("id") or q.get("query_id")
        vec = embedder.embed_query(text)
        per, wall = {}, {}
        for h, g in builders.items():
            t = time.monotonic()
            per[h] = g.graph_search(text, cfg.global_tenant_id or "global",
                                    query_vector=vec, limit=WIDE)
            wall[h] = round(time.monotonic() - t, 2)
        ids = {h: {r["chunk_id"] for r in per[h]} for h in per}
        new2 = ids[2] - ids[1]
        hops2 = [r["hop_distance"] for r in per[2]]
        hops1 = [r["hop_distance"] for r in per[1]]
        ex = next((r for r in per[2] if r["chunk_id"] in new2), None)

        rows.append({
            "query_id": qid, "query": text[:120],
            "n_at_hop1": len(per[1]), "n_at_hop2": len(per[2]),
            "wall_s_hop1": wall[1], "wall_s_hop2": wall[2],
            "hop1_distances": sorted(set(hops1)),
            "hop2_distance_hist": dict(Counter(hops2)),
            "new_chunks_at_hop2": len(new2),
            "example_2hop_chunk": (None if not ex else {
                "chunk_id": ex["chunk_id"], "hop_distance": ex["hop_distance"],
                "concepts": ex["concept_path"][:5], "preview": ex["text_preview"][:90]}),
        })
        agg["queries"] += 1
        agg["queries_hop2_adds"] += 1 if new2 else 0
        agg["hop1_all_zero"] += 1 if set(hops1) <= {0} else 0
        agg["hop2_not_constant"] += 1 if len(set(hops2)) > 1 else 0
        print(f"  {qid}: hop1={len(per[1])} ({wall[1]}s) hop2={len(per[2])} ({wall[2]}s) "
              f"+{len(new2)} new  hop2_dist={dict(Counter(hops2))}")

    art = {"meta": {"memgraph": f"{cfg.memgraph_host}:{cfg.memgraph_port}",
                    "qdrant": cfg.qdrant_host, "collection": cfg.qdrant_collection,
                    "sample": len(sample), "limit": WIDE, "read_only": True},
           "aggregate": dict(agg), "rows": rows}
    OUT.write_text(json.dumps(art, indent=2) + "\n")
    print(f"\naggregate: {dict(agg)}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
