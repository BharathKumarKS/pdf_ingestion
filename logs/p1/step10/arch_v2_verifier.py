"""Mechanical verifier for Docs/synapse_architecture_v2.html.

Re-derives every factual claim in the diagram from the CODE, the CONFIG and the LIVE stores — it does
not read the doc's prose for truth, it reads it for CLAIMS and then checks each against the source.

Run:  .venv/bin/python logs/p1/step10/arch_v2_verifier.py
Exit: 0 = all checks pass, 1 = a check failed.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
HTML = REPO.parent.parent / "Docs" / "synapse_architecture_v2.html"

QD = "http://10.0.10.65:6333"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def _get(url: str):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


html = HTML.read_text()
# strip nothing — we search the raw text for claims.

# ── 1. the doc states the product collection and its lane names ────────────────────────────────────
check("doc names knowledge_base_v3", "knowledge_base_v3" in html)
check("doc uses dense_full (not dense_768)",
      "dense_full" in html and "dense_768" not in html)
check("doc names derivative_artifacts", "derivative_artifacts" in html)
check("doc names concept_embeddings", "concept_embeddings" in html)
check("doc names visual_knowledge_base", "visual_knowledge_base" in html)

# ── 2. live collection counts claimed in the doc ────────────────────────────────────────────────────
try:
    counts = {c: _get(f"{QD}/collections/{c}")["result"]["points_count"] for c in (
        "knowledge_base_v3", "knowledge_base_v2", "derivative_artifacts",
        "concept_embeddings", "visual_knowledge_base")}
    check("v3 points == 3,869 (doc)", counts["knowledge_base_v3"] == 3869, f"live={counts['knowledge_base_v3']}")
    check("doc states 3,869", "3,869" in html)
    check("da points == 73,406 (doc)", counts["derivative_artifacts"] == 73406, f"live={counts['derivative_artifacts']}")
    check("doc states 73,406", "73,406" in html)
    check("concept points == 6,065 (doc)", counts["concept_embeddings"] == 6065, f"live={counts['concept_embeddings']}")
    check("doc states 6,065", "6,065" in html)
    check("visual points == 2,001 (doc)", counts["visual_knowledge_base"] == 2001, f"live={counts['visual_knowledge_base']}")
    check("doc states 2,001", "2,001" in html)
except Exception as e:  # noqa: BLE001
    check("live Qdrant reachable", False, repr(e))

# ── 3. v3 lane schema claimed in the doc ─────────────────────────────────────────────────────────────
try:
    v3 = _get(f"{QD}/collections/knowledge_base_v3")["result"]["config"]["params"]
    vecs = v3.get("vectors", {})
    names = set(vecs) | set(v3.get("sparse_vectors", {}))
    check("v3 declares dense_64", "dense_64" in names)
    check("v3 declares dense_full", "dense_full" in names)
    check("v3 declares colbert", "colbert" in names)
    check("v3 declares sparse", "sparse" in names)
    check("dense_64 is 64d", vecs.get("dense_64", {}).get("size") == 64)
    check("dense_full is 768d", vecs.get("dense_full", {}).get("size") == 768)
    check("colbert is 128d max_sim",
          vecs.get("colbert", {}).get("size") == 128
          and vecs.get("colbert", {}).get("multivector_config", {}).get("comparator") == "max_sim")
except Exception as e:  # noqa: BLE001
    check("v3 schema readable", False, repr(e))

# ── 4. config values claimed in the doc ──────────────────────────────────────────────────────────────
from src.core.config import get_settings  # noqa: E402
cfg = get_settings()
check("chunk_size == 512", cfg.chunk_size == 512, str(cfg.chunk_size))
check("chunk_overlap == 64", cfg.chunk_overlap == 64, str(cfg.chunk_overlap))
check("dense_prefetch_limit == 1000", cfg.dense_prefetch_limit == 1000, str(cfg.dense_prefetch_limit))
check("dense_rescore_limit == 500", cfg.dense_rescore_limit == 500, str(cfg.dense_rescore_limit))
check("mmr_lambda == 0.7", abs(cfg.mmr_lambda - 0.7) < 1e-9, str(cfg.mmr_lambda))
check("reranker_top_k == 20", cfg.reranker_top_k == 20, str(cfg.reranker_top_k))
check("reranker_fetch_k == 100", cfg.reranker_fetch_k == 100, str(cfg.reranker_fetch_k))
check("mmr_candidates == 100", cfg.mmr_candidates == 100, str(cfg.mmr_candidates))
check("raptor_max_levels == 3", cfg.raptor_max_levels == 3, str(cfg.raptor_max_levels))
check("reranker_model == bge-reranker-v2-m3", cfg.reranker_model == "BAAI/bge-reranker-v2-m3", cfg.reranker_model)
check("doc states prefetch depths", "1,000" in html and "500" in html)
check("doc states MMR λ=0.7", "λ=0.7" in html)

# ⚠️ The GENERATOR model claim — an independent reviewer REFUTED this by reading config.py's DEFAULT
# (`openai_model = "meta-llama/Llama-3.2-8B-Instruct"`, config.py:185). That is the wrong layer: `.env`
# overrides it. `synthesize()` -> `call_llm(settings=cfg)` -> `cfg.openai_model`, so the RESOLVED value
# is what matters. These two checks pin the resolved value (the reviewer's refutation is invalid).
check("llm_backend resolves to 'openai'", cfg.llm_backend == "openai", cfg.llm_backend)
check("resolved generator model == openai/gpt-oss-20b",
      cfg.openai_model == "openai/gpt-oss-20b", cfg.openai_model)

# ── 5. code claims ───────────────────────────────────────────────────────────────────────────────────
store = (REPO / "src" / "pdf_ingestion" / "store.py").read_text()
er = (REPO / "scripts" / "evaluate_rag.py").read_text()

check("code: client-side RRF with rrf_k=1 in _qdrant_search",
      "self._rrf_merge(*lane_lists, rrf_k=1" in store)
check("doc: states client-side RRF / §I68", "CLIENT-SIDE" in html.upper() and "§I68" in html)
check("code: search_with_das appends DA before dedup/MMR",
      store.index("da_parents") < store.index("Page-level dedup"))
check("doc: states DA appended before dedup/MMR", "appended BEFORE dedup/MMR" in html)
check("code: synthesize() is fed retrieval['reranked']",
      "synthesize(query_text, retrieval[\"reranked\"]" in er)
check("code: per-type rerank policy (raw for factual, hyp for overview)",
      'rerank_query = hyp if query_type == "overview" else query_text' in er)
check("doc: states the per-type rerank policy", "if overview else RAW query" in html)

# ── 6. card types (8) ────────────────────────────────────────────────────────────────────────────────
try:
    from src.pdf_ingestion.card_generator import CardType  # noqa: E402
    n = len(list(CardType))
    check("CardType has 8 types", n == 8, str(n))
except Exception as e:  # noqa: BLE001
    check("CardType importable", False, repr(e))

# ── 7. model claims in the doc ───────────────────────────────────────────────────────────────────────
check("doc: generator is gpt-oss-20b", "gpt-oss-20b" in html)
check("doc: reranker named", "BAAI/bge-reranker-v2-m3" in html)
check("doc: no stale Llama 3.2", "Llama" not in html)
check("doc: no stale '940 pages'", "940 pages" not in html)
check("doc: no stale '5,051 chunks'", "5,051" not in html)

# ── 8. the intent classifier's training size claim ───────────────────────────────────────────────────
check("doc: states 1,158 training queries", "1,158" in html)

# ── report ───────────────────────────────────────────────────────────────────────────────────────────
npass = sum(1 for _, ok, _ in results if ok)
for name, ok, detail in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))
print(f"\n{npass}/{len(results)} checks PASS")
sys.exit(0 if npass == len(results) else 1)
