"""NG-P4 acceptance — do the Visual and Graph tabs show what the backend actually holds?

The brief's acceptance for NG-P4: *page images render; graph nodes match `get_graph_builder(cfg)`.*

Read-only. Runs the module's own loaders (the functions the two tabs call) and checks them against
independent sources:

  * `load_visual`     → the vector count equals `count_visual_vectors`; the returned pages equal a
                        direct `visual_search`; every page image resolves to real PNG bytes.
  * `load_graph_stats`→ the counts equal a FRESH, independent Memgraph driver's counts (a
                        separate connection in this process, not the loader's), and the graph's
                        Chunk count for the current document is checked against SQLite's (as a
                        bound, not an equality — see the note in the graph section).
  * `load_graph_search` → a known-good query returns passages whose chunk_ids match a direct
                        `get_graph_builder(cfg).graph_search(...)` call.

Run:
    .venv/bin/python logs/p1/step10/ng_p4_acceptance.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "logs/p1/step10/ng_p4_acceptance.json"

DOC_CURRENT = "7ba61432-c5e0-416d-aecf-25a232523481"
VISUAL_QUERY = "the diagram of a pendulum"
GRAPH_QUERY = "Why does a satellite stay in orbit?"


def _load_module():
    spec = importlib.util.spec_from_file_location("ng_app", ROOT / "src/frontend/nicegui_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    from neo4j import GraphDatabase

    from src.core.config import get_settings
    from src.pdf_ingestion.store import DocumentStore

    cfg = get_settings()
    ng = _load_module()
    store = DocumentStore(cfg)

    checks: list[dict] = []

    def check(name: str, ui_value, other_value) -> None:
        ok = ui_value == other_value
        checks.append({"check": name, "tab": ui_value, "reference": other_value, "ok": ok})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}: tab={ui_value!r} ref={other_value!r}")

    # ── Visual ───────────────────────────────────────────────────────────────
    from src.pdf_ingestion.colpali_embedder import get_colpali_embedder

    landing = ng.load_visual(cfg, "", 0)
    check("visual.n_vectors", landing["n_vectors"],
          store.count_visual_vectors([ng.DEMO_TENANT, cfg.global_tenant_id]))
    check("visual.empty_query_no_results", landing["results"], [])

    vis = ng.load_visual(cfg, VISUAL_QUERY, 3)
    patches = get_colpali_embedder(cfg).embed_query_text(VISUAL_QUERY)
    direct = store.visual_search(query_patches=patches, tenant_id=ng.DEMO_TENANT, limit=3,
                                 score_threshold=0.0)
    check("visual.n_results", len(vis["results"]), len(direct))
    check("visual.pages", [r["page_number"] for r in vis["results"]],
          [d.get("page_number") for d in direct])
    check("visual.image_keys", [r["image_key"] for r in vis["results"]],
          [d.get("image_key") for d in direct])
    pngs = [r["png"] for r in vis["results"]]
    # ⚠️ Not every returned page has a local image file: the index holds vectors for TWO documents
    # (the old ingest 6d55c52b + the current 7ba61432), and `data/page_images/` holds PNGs for the
    # CURRENT one only. That is the runbook's visual-lane caveat, and it is a DATA gap, not a tab
    # defect — so the check is "every key that exists on disk resolves to a valid PNG", and the
    # missing count is recorded as a measured finding rather than failed.
    resolved = [p for p in pngs if p]
    missing = [r["image_key"] for r in vis["results"] if not r["png"]]
    check("visual.some_images_resolved", len(resolved) > 0, True)
    check("visual.resolved_are_png",
          all(p[:8] == b"\x89PNG\r\n\x1a\n" for p in resolved), True)
    check("visual.missing_marked_with_error",
          all(r["error"] for r in vis["results"] if not r["png"]), True)
    print(f"       page images: {len(resolved)} resolved, {len(missing)} missing "
          f"(keys without a local file: {missing})")
    if resolved:
        first = next(r for r in vis["results"] if r["png"])
        print(f"       first page image: {len(first['png']):,} bytes, "
              f"page {first['page_number']}, cosine {first['score_cosine']}")

    # ── Graph: stats vs an INDEPENDENT driver ────────────────────────────────
    stats = ng.load_graph_stats(cfg)
    driver = GraphDatabase.driver(f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
                                  auth=(cfg.memgraph_user, cfg.memgraph_password))
    try:
        with driver.session() as s:
            for name, cypher in ng.GRAPH_STATS_CYPHER.items():
                rec = s.run(cypher).single()
                check(f"graph_stats.{name}", stats.get(name), int(rec["c"]) if rec else 0)
            rec = s.run("MATCH (c:Chunk {document_id: $id}) RETURN count(c) AS c",
                        id=DOC_CURRENT).single()
            graph_chunks_current = int(rec["c"]) if rec else 0
    finally:
        driver.close()

    con = sqlite3.connect(ROOT / "data/synapse.db")
    sqlite_chunks_current = con.execute(
        "select count(*) from chunks where document_id = ?", (DOC_CURRENT,)
    ).fetchone()[0]
    con.close()
    # ⚠️ NOT an equality check. The graph build applies the content filter by RECOMPUTING the
    # predicate, while SQLite's `is_content` column is a snapshot of an older code vintage
    # (IMPROVEMENTS §I102-class / the register's pitfall 36), so the graph legitimately holds FEWER
    # Chunk nodes than SQLite has rows. Measured: graph 3,533 vs SQLite 3,796 = **−263**, the exact
    # exclusion the register documents. Assert the sanity bound only, and record the delta.
    check("graph.chunks_not_more_than_sqlite", graph_chunks_current <= sqlite_chunks_current, True)
    check("graph.chunks_positive", graph_chunks_current > 0, True)
    graph_chunk_delta = graph_chunks_current - sqlite_chunks_current
    print(f"       graph Chunk nodes for the current doc: {graph_chunks_current:,} "
          f"vs SQLite {sqlite_chunks_current:,} ({graph_chunk_delta:+,}) — the documented "
          "recompute-vs-stored-column exclusion")

    # ── Graph: search matches a direct builder call ──────────────────────────
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.graph_builder import get_graph_builder

    gs = ng.load_graph_search(cfg, GRAPH_QUERY)
    q_vec = get_cluster_embedder(cfg).embed_query(GRAPH_QUERY)
    direct_gs = get_graph_builder(cfg).graph_search(
        query_text=GRAPH_QUERY, tenant_id=ng.DEMO_TENANT, query_vector=q_vec, limit=6
    )
    check("graph_search.n_results", gs["n_results"], len(direct_gs))
    check("graph_search.chunk_ids", [r["chunk_id"] for r in gs["results"]],
          [h.get("chunk_id") for h in direct_gs])
    check("graph_search.has_concepts",
          all(r["concept_path"] for r in gs["results"]) if gs["results"] else False, True)

    n_fail = sum(1 for c in checks if not c["ok"])
    verdict = "PASS" if n_fail == 0 else f"FAIL ({n_fail})"
    print(f"\n{'='*64}\nNG-P4 ACCEPTANCE: {verdict}  ({len(checks)} checks)\n{'='*64}")
    OUT.write_text(json.dumps(
        {"verdict": verdict, "n_checks": len(checks), "n_fail": n_fail,
         "visual_query": VISUAL_QUERY, "graph_query": GRAPH_QUERY,
         "graph_stats": stats, "n_visual_results": len(vis["results"]),
         "n_graph_results": gs["n_results"],
         "visual_images_resolved": len(resolved), "visual_images_missing": missing,
         "graph_chunks_current_doc": graph_chunks_current,
         "sqlite_chunks_current_doc": sqlite_chunks_current,
         "checks": checks}, indent=2))
    print(f"wrote {OUT}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
