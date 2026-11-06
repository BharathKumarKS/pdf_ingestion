"""Diagnose why the §I112 probe's arm A (0.1878) does not reproduce §I111's D100 (0.2128).

Reproduces fusion_attribution's D100 (HyDE vector, store.search limit=100, query_text=None) for a few
overview queries and diffs the page list against the recorded D100_pages. Read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

cfg = get_settings()
cfg.splade_enabled = False
cfg.colbert_enabled = False
store = DocumentStore(cfg)
emb = get_cluster_embedder(cfg)
hyde = load_hyde(Path("data/eval_queries_v2.json"), cfg=cfg)

fus = json.loads(Path("logs/p1/step10/fusion_attribution.json").read_text())
rows = [r for r in fus["per_query"] if "error" not in r and r["query_type"] == "overview"]
qmap = {q["id"]: q for q in json.loads(Path("data/eval_queries_v2.json").read_text())
        if isinstance(q, dict)}

print("global_tenant_id =", repr(cfg.global_tenant_id), " dense_prefetch_limit =", cfg.dense_prefetch_limit)

for r in rows[:4]:
    qid = r["id"]
    htext = hyde.get(qid)
    vec = emb.embed_query(htext)
    hits = store.search(vec, tenant_id=cfg.global_tenant_id, limit=100, query_text=None)
    pages = [int((h.get("payload") or h)["page_number"]) for h in hits if (h.get("payload") or h).get("page_number") is not None]
    rec = r["D100_pages"]
    first = next((i for i in range(max(len(pages), len(rec))) if (pages[i] if i < len(pages) else None) != (rec[i] if i < len(rec) else None)), None)
    print(f"\n{qid}: reproduced_len={len(pages)} recorded_len={len(rec)} first_diff_idx={first}")
    print("  reproduced[:12]:", pages[:12])
    print("  recorded   [:12]:", rec[:12])
    print("  hyde_text head:", repr(htext[:70]))
PY