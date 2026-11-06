"""Probe EVERY backend the Streamlit app's tabs call. Read-only.

Usage:  python logs/p1/step10/app_parts_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.core.config import get_settings
from src.pdf_ingestion.store import DocumentStore

cfg = get_settings()
store = DocumentStore(cfg)
print(f"collection={cfg.qdrant_collection} host={cfg.qdrant_host} colpali={cfg.colpali_collection}")

def sec(name):
    print(f"\n=== {name} ===")

sec("documents (global tenant)")
try:
    docs = store.list_documents(tenant_id=cfg.global_tenant_id)
    for d in docs:
        print(f"  {d.id}  {d.filename}  colpali_status={getattr(d,'colpali_status',None)}  pages={getattr(d,'page_count',None)}")
    print(f"  n={len(docs)}")
except Exception as e:
    print("  ERR:", type(e).__name__, e)

doc = docs[0] if docs else None

sec("Cards tab — store.get_cards(doc)")
try:
    cards = store.get_cards(doc.id) if doc else []
    print(f"  cards for {doc.id if doc else None}: {len(cards)}")
    if cards:
        print("  sample card types:", sorted({getattr(c, 'card_type', '?') for c in cards})[:8])
except Exception as e:
    print("  ERR:", type(e).__name__, e)

sec("RAPTOR tab — store.get_raptor_tree(doc)")
try:
    nodes = store.get_raptor_tree(doc.id) if doc else []
    print(f"  raptor nodes: {len(nodes)}")
except Exception as e:
    print("  ERR:", type(e).__name__, e)

sec("Visual tab — store.count_visual_vectors")
try:
    print("  visual vectors (global):", store.count_visual_vectors([cfg.global_tenant_id]))
except Exception as e:
    print("  ERR:", type(e).__name__, e)

sec("Visual tab — store.visual_search (text query, current doc)")
try:
    from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
    q = get_colpali_embedder(cfg).embed_query_text("a diagram of a diffraction pattern")
    hits = store.visual_search(query_patches=q, tenant_id=cfg.global_tenant_id, limit=10, score_threshold=0.0)
    print(f"  hits: {len(hits)}")
    for h in hits[:5]:
        print("   ", {k: h.get(k) for k in ('page_number', 'document_id', 'score_cosine') if k in h})
except Exception as e:
    print("  ERR:", type(e).__name__, e)

sec("Ask tab — dense search sanity (one query)")
try:
    import numpy as np
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    emb = get_cluster_embedder(cfg)
    v = np.array(emb.embed_query("What is Newton's second law?"), dtype=np.float32)
    hits = store.search(v, tenant_id=cfg.global_tenant_id, limit=5, query_text="What is Newton's second law?")
    print(f"  hits: {len(hits)}; top pages:", [h.get("page_number") for h in hits[:5]])
except Exception as e:
    print("  ERR:", type(e).__name__, e)

sec("Graph tab — Memgraph node counts (neo4j driver)")
try:
    from neo4j import GraphDatabase
    uri = getattr(cfg, "memgraph_uri", None) or getattr(cfg, "memgraph_url", None) or "bolt://localhost:7687"
    print("  uri:", uri)
    drv = GraphDatabase.driver(uri, auth=None)
    with drv.session() as s:
        for label in ("Document", "Chunk", "Page", "Concept"):
            r = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
            print(f"  {label}: {r['c'] if r else '?'}")
        r = s.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS c").single()
        print(f"  RELATES_TO: {r['c'] if r else '?'}")
    drv.close()
except Exception as e:
    print("  ERR:", type(e).__name__, e)

sec("Graph tab — DA lane (search_da)")
try:
    import numpy as np
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    emb = get_cluster_embedder(cfg)
    v = np.array(emb.embed_query("conservation of energy"), dtype=np.float32)
    da = store.search_da(query_vector=v, tenant_id=cfg.global_tenant_id, limit=5, query_text="conservation of energy")
    print(f"  DA hits: {len(da)}")
except Exception as e:
    print("  ERR:", type(e).__name__, e)
