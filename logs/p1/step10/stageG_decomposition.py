"""Stage G — the §I66 stage decomposition on BOTH arms: where does each index lose its reachable pages?

Pre-registration: `.hermes/plans/2026-10-25-p1-nomic-adoption-reembed-and-finetune-plan.md` §3 Stage G:
*"base recall → the funnel/fusion → the cross-encoder → the generator, on v3 vs v2. This is the
diagnostic half and it is cheap. It answers what the writeup needs: did the embedder fix the
full-dimension ranking lane, or just move the loss around?"* Verifier G: **the probe reproduces
§I66's v2 decomposition on v2** (a known-answer check) before it is trusted on v3.

WHY IT EXISTS. Stage F (§I85) returned a NULL at the product endpoint (ΔcR@20 −0.0012, unresolved)
while the ORACLE screen measured nomic − qwen3 = +0.1400 on the base lane (§I63). That gap is
unexplained, and it is the question that decides whether a **fine-tune** (S6) can work at all: if the
loss sits in the base / full-dim ranking lane, a better embedder can fix it; if it sits in the
100-slot fusion output (§I66's finding), no embedder change can. So this is a ~5-min, read-only
pre-check on an hours-long GPU job.

THE ARMS. The SAME two indexes as Stage F, each queried with its OWN embedder (a cross-embedder
comparison is impossible — v3's `dense_full` is 768d and a 1024d query 400s):
  arm A = `knowledge_base_v2` / `Qwen/Qwen3-Embedding-0.6B` / 1024
  arm B = `knowledge_base_v3` / `nomic-ai/nomic-embed-text-v1.5` / 768
⚠️ Both collections hold the IDENTICAL corpus — **3,489 in-window content chunks / 888 pages** — so
the denominator is the same and only the vectors differ. (Measured, not assumed.)

THE FOUR STAGES, and the unit. Coverage = |pages(stage) ∩ REACHABLE labelled pages| / |reachable|
— §I66's own unit, so the rows are comparable across arms AND to §I66.
  1. **base**    — the exact 64d MRL lane at limit N (cfg.dense_prefetch_limit = 1000)
  2. **cut**     — within that lane, the exact full-dim top-L (cfg.dense_rescore_limit = 500)
  3. **fusion**  — the PRODUCT's `search_with_das` pool (RRF + page dedup + MMR → fetch_k = 100)
  4. **cross-encoder** — the PRODUCT's reranked top-20
⚠️ Stages 1–2 are **exact brute force** (§I66's method — no ANN, no Qdrant scoring), so the filtered
HNSW loss (§I60: up to 18.5 %) is excluded. Stages 3–4 are the **real product path**. The raw
product metrics (R@100 / R@20, over ALL labelled pages — a DIFFERENT unit) are reported beside the
coverage so the two are never conflated.

DA and graph lanes are OFF (the re-registration, §I85) — so stages 3–4 do NOT reproduce §I66's
0.6048 / 0.4318, which were measured with the DA lane live. The known-answer check is therefore on
stages 1–2 only (DA-independent), which is exactly §I66's own exact-probe rows.

READ-ONLY: no writes to any collection, no LLM calls (HyDE is served from the frozen §I73 cache).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import numpy as np  # noqa: E402
from loguru import logger  # noqa: E402
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder  # noqa: E402
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for  # noqa: E402
from src.pdf_ingestion.reranker import get_reranker  # noqa: E402
from src.pdf_ingestion.store import DocumentStore, _resolve_low_lane  # noqa: E402
from evaluate_rag import run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
PROD_N, PROD_L = 1000, 500          # cfg.dense_prefetch_limit / cfg.dense_rescore_limit (asserted)
TOP_K = 20
# §I86's named GAP row: full-dimension over ALL chunks, NO 64d prefilter — the configuration §I63's
# oracle corresponds to. It separates "nomic is worse on this corpus" from "nomic's full-dim advantage
# is hidden by the product's 64d prefilter". §I66's grid has this row for v2 (N=3489, L=500 = 0.8286);
# it is added here for BOTH arms.
FULLDIM_LS = (100, 500, 1000, 2000)

EXPECT = {
    "A": dict(collection="knowledge_base_v2", model="Qwen/Qwen3-Embedding-0.6B", dim=1024,
              dim_low=64, doc_prefix="", instr_kind="qwen3"),
    "B": dict(collection="knowledge_base_v3", model="nomic-ai/nomic-embed-text-v1.5", dim=768,
              dim_low=64, doc_prefix="search_document: ", instr_kind="nomic"),
}
# §I66's exact-probe rows on v2 (coverage of reachable) — the known-answer check.
I66 = {"stage0_base_N1000": 0.8151, "stage1_cut_L500": 0.7478}
I66_TOL = 0.002

# ── The RE-RUN's anchors (pre-registration 2026-10-26 §4) ──────────────────────────────────────
# G7 — §I87's `nomic_pooled` row, L=500. After the §I88 write, v3's STORED index IS the pooled
# construction, so this row must reproduce. A half-written or still-late-chunked v3 reads 0.6887 —
# far outside the tolerance — which is exactly why this guard makes the treatment identifiable.
I87_POOLED_L500 = 0.843325
I87_TOL = 0.002
# G8 — §I86's arm-A rows. v2 is untouched and §I68 made the funnel deterministic, so arm A must be
# bit-stable across the two runs. Arm A shares nothing with the treatment: drift here is harness drift.
I86_ARM_A = {"cov_base": 0.815136, "cov_cut": 0.747763, "cov_fusion": 0.660452,
             "cov_ce": 0.458824, "cov_fulldim_L500": 0.828609}
I86_A_TOL = 1e-6


def _load_queries() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _content_filter(cfg) -> Filter:
    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    return Filter(must_not=must_not, should=[
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cfg.global_tenant_id))]),
        Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value="global"))]),
    ])


def _fetch_corpus(client, cfg, filt, dense_name) -> tuple[np.ndarray, np.ndarray]:
    """Every in-window content chunk: (full-dim vectors, pages)."""
    vectors, pages = [], []
    offset = None
    while True:
        pts, offset = client.scroll(
            collection_name=cfg.qdrant_collection, scroll_filter=filt, limit=1000, offset=offset,
            with_payload=["page_number"], with_vectors=[dense_name])
        for p in pts:
            v = p.vector
            if isinstance(v, dict):
                v = v.get(dense_name)
            pg = (p.payload or {}).get("page_number")
            if v is None or pg is None:
                continue
            vectors.append(v)
            pages.append(int(pg))
        if offset is None:
            break
    return np.asarray(vectors, dtype=np.float32), np.asarray(pages, dtype=np.int64)


def _cov(stage_pages: set[int], reach: set[int]) -> float | None:
    return (len(stage_pages & reach) / len(reach)) if reach else None


def _raw(pages: set[int], rel: set[int]) -> float | None:
    return (len(pages & rel) / len(rel)) if rel else None


def _ci(diffs):
    n = len(diffs)
    if n < 2:
        return [float("nan"), float("nan")]
    m = statistics.mean(diffs)
    half = 1.96 * statistics.stdev(diffs) / (n ** 0.5)
    return [m - half, m + half]


def run_arm(arm: str, out: Path, limit: int = 0) -> int:
    exp = EXPECT[arm]
    cfg = get_settings()

    problems = []
    if not cfg.qdrant_host:
        problems.append("QDRANT_HOST blank")
    if cfg.qdrant_collection != exp["collection"]:
        problems.append(f"collection {cfg.qdrant_collection!r} != {exp['collection']!r}")
    if cfg.dense_model != exp["model"] or cfg.dense_dim != exp["dim"]:
        problems.append(f"model/dim {cfg.dense_model}/{cfg.dense_dim} != {exp['model']}/{exp['dim']}")
    if cfg.dense_dim_low != exp["dim_low"]:
        problems.append(f"dim_low {cfg.dense_dim_low} != {exp['dim_low']}")
    if cfg.document_prefix != exp["doc_prefix"]:
        problems.append(f"doc_prefix {cfg.document_prefix!r} != {exp['doc_prefix']!r}")
    if exp["instr_kind"] == "nomic" and cfg.query_instruction != "search_query: ":
        problems.append(f"instr {cfg.query_instruction!r} != 'search_query: '")
    if exp["instr_kind"] == "qwen3" and "Instruct:" not in (cfg.query_instruction or ""):
        problems.append("instr is not Qwen3's")
    if (cfg.dense_prefetch_limit, cfg.dense_rescore_limit) != (PROD_N, PROD_L):
        problems.append(f"N/L {(cfg.dense_prefetch_limit, cfg.dense_rescore_limit)} != {(PROD_N, PROD_L)}")
    if cfg.da_enabled:
        problems.append("da_enabled is True — Stage G mirrors Stage F's DA-off config")
    if problems:
        for p in problems:
            logger.error("CONFIG FAIL: {}", p)
        print(json.dumps({"arm": arm, "ok": False, "problems": problems}, indent=2))
        return 2

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    dense_name = store._dense_vector_name()
    low_name, low_size = _resolve_low_lane(store._collection_vectors(), cfg)

    queries = _load_queries()
    if limit:
        queries = queries[:limit]

    # HyDE frozen (§4) + graph lane off (§2c) — identical to Stage F.
    cache = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map = {prompt_for(q["query"]): cache.get(q["id"])
                  for q in queries if q.get("query_type") in ("factual", "overview")}
    import src.core.llm as llm_mod
    _real_llm = llm_mod.call_llm

    def _frozen(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        raise RuntimeError(f"HyDE cache miss mid-run for {str(prompt)[:80]!r} — refusing a live call")
    llm_mod.call_llm = _frozen

    import src.pdf_ingestion.graph_builder as gb_mod
    class _NoGraph:
        def graph_search(self, *a, **kw):
            return []
    _real_gb = gb_mod.get_graph_builder
    gb_mod.get_graph_builder = lambda settings=None: _NoGraph()

    logger.info("ARM {} — {} {}d low={}({}) dense_lane={} N={} L={} queries={}",
                arm, cfg.qdrant_collection, cfg.dense_dim, low_name, low_size, dense_name,
                PROD_N, PROD_L, len(queries))

    filt = _content_filter(cfg)
    E, pages = _fetch_corpus(store._qdrant, cfg, filt, dense_name)
    coll_pages = {int(p) for p in pages.tolist()}
    logger.info("corpus: {} in-window content chunks / {} distinct pages", len(pages), len(coll_pages))

    Q = np.asarray([embedder.embed_query(q["query"]) for q in queries], dtype=np.float32)

    # exact 64d view (the MRL lane) — re-normalised, §I60
    E64 = E[:, :low_size].copy()
    E64 /= np.linalg.norm(E64, axis=1, keepdims=True) + 1e-12
    Q64 = Q[:, :low_size].copy()
    Q64 /= np.linalg.norm(Q64, axis=1, keepdims=True) + 1e-12

    per_query, errors = [], []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
        rel = {int(p) for p in q["relevant_pages"]}
        reach = rel & coll_pages
        rec = {"id": qid, "query_type": qtype, "n_relevant": len(rel), "n_reachable": len(reach)}
        try:
            # stages 1-2: EXACT (§I66's method)
            order64 = np.argsort(-(E64 @ Q64[i - 1]), kind="stable")[:PROD_N]
            p_base = {int(pages[j]) for j in order64}
            within = np.argsort(-(E[order64] @ Q[i - 1]), kind="stable")[:PROD_L]
            p_cut = {int(pages[j]) for j in order64[within]}
            # §I86 GAP ROW: full-dim over ALL chunks, NO prefilter (§I63's oracle configuration).
            order_all = np.argsort(-(E @ Q[i - 1]), kind="stable")
            fulldim = {f"cov_fulldim_L{L}": _cov({int(pages[j]) for j in order_all[:L]}, reach)
                       for L in FULLDIM_LS}
            # stages 3-4: the REAL product path
            ret = run_retrieval(text, store, embedder, reranker, cfg, "global", 0.0, query_type=qtype)
            p_fus = {h.get("page_number") for h in ret["hits"] if h.get("page_number")}
            p_ce = {h.get("page_number") for h in ret["reranked"][:TOP_K] if h.get("page_number")}
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("[{}] FAILED: {}", qid, exc)
            per_query.append({**rec, "error": str(exc)})
            continue
        rec.update({
            "cov_base": _cov(p_base, reach), "cov_cut": _cov(p_cut, reach),
            "cov_fusion": _cov(p_fus, reach), "cov_ce": _cov(p_ce, reach),
            "raw_r100_fusion": _raw(p_fus, rel), "raw_r20_ce": _raw(p_ce, rel),
            "pool_size": len(ret["hits"]), **fulldim,
        })
        per_query.append(rec)
        if i % 40 == 0:
            logger.info("  {}/{}", i, len(queries))
    wall = time.time() - t0
    llm_mod.call_llm = _real_llm
    gb_mod.get_graph_builder = _real_gb

    def m(key, sub=None):
        vals = [r[key] for r in (sub or per_query) if r.get(key) is not None]
        return round(statistics.mean(vals), 6) if vals else None

    agg = {k: m(k) for k in ("cov_base", "cov_cut", "cov_fusion", "cov_ce",
                             "raw_r100_fusion", "raw_r20_ce",
                             *[f"cov_fulldim_L{L}" for L in FULLDIM_LS])}
    # known-answer check (§I66's exact-probe rows) — only meaningful on arm A / v2
    ka = {"stage0_base_N1000": agg["cov_base"], "stage1_cut_L500": agg["cov_cut"]}
    ka_gaps = {k: (ka[k] - I66[k]) if ka[k] is not None else None for k in I66}
    ka_ok = all(g is not None and abs(g) <= I66_TOL for g in ka_gaps.values())

    artifact = {
        "meta": {
            "arm": arm, "collection": cfg.qdrant_collection, "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model, "dense_dim": cfg.dense_dim,
            "dense_lane": dense_name, "low_lane": low_name, "low_size": low_size,
            "document_prefix": cfg.document_prefix, "query_instruction": cfg.query_instruction,
            "N": PROD_N, "L": PROD_L, "top_k": TOP_K, "da_enabled": cfg.da_enabled,
            "graph_lane": "OFF (mirrors Stage F)", "hyde": "ON, frozen (data/hyde_cache)",
            "unit": "coverage of a query's REACHABLE labelled pages (§I66's unit)",
            "n_chunks": len(pages), "n_pages": len(coll_pages),
            "n_queries": len(per_query), "n_errors": len(errors), "wall_seconds": round(wall, 1),
        },
        "guards": {
            "G1_config_resolved": True, "G2_all_queries_scored": len(errors) == 0,
            "G3_known_answer_I66": ka_ok if arm == "A" else None,
        },
        "known_answer": {"target_I66": I66, "measured": ka, "gaps": ka_gaps, "tol": I66_TOL},
        "aggregate": agg,
        "errors": errors,
        "per_query": per_query,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    logger.info("arm {} → {} ({}s) sha256 {}", arm, out, round(wall, 1), sha[:16])
    print(f"ARM {arm}: {len(per_query)} queries, {len(errors)} errors, {round(wall,1)}s → {out}")
    print("  " + json.dumps(agg, indent=2).replace("\n", "\n  "))
    if arm == "A":
        print(f"  known-answer vs §I66: gaps {ka_gaps}  {'PASS' if ka_ok else 'FAIL'}")
    return 0


def combine(paths, out: Path) -> int:
    A = json.loads(paths["A"].read_text())
    B = json.loads(paths["B"].read_text())
    a = {r["id"]: r for r in A["per_query"] if "error" not in r}
    b = {r["id"]: r for r in B["per_query"] if "error" not in r}
    ids = sorted(set(a) & set(b))

    stages = [("base (64d lane @N=1000)", "cov_base"), ("after full-dim cut L=500", "cov_cut"),
              ("after fusion (pool=100)", "cov_fusion"), ("after cross-encoder (top-20)", "cov_ce")]
    table, deltas = {}, {}
    for label, key in stages:
        va = statistics.mean(a[i][key] for i in ids if a[i].get(key) is not None)
        vb = statistics.mean(b[i][key] for i in ids if b[i].get(key) is not None)
        d = [b[i][key] - a[i][key] for i in ids
             if a[i].get(key) is not None and b[i].get(key) is not None]
        lo, hi = _ci(d)
        table[label] = {"A_v2_qwen3": round(va, 6), "B_v3_nomic": round(vb, 6)}
        deltas[label] = {"mean_delta_B_minus_A": round(statistics.mean(d), 6),
                         "ci95": [round(lo, 6), round(hi, 6)],
                         "resolved": bool(lo > 0 or hi < 0), "n": len(d),
                         "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0),
                         "ties": sum(1 for x in d if x == 0)}
    # §I86's GAP ROW — full-dim over ALL chunks, NO 64d prefilter (§I63's oracle configuration).
    fulldim = {}
    for L in FULLDIM_LS:
        key = f"cov_fulldim_L{L}"
        va = statistics.mean(a[i][key] for i in ids if a[i].get(key) is not None)
        vb = statistics.mean(b[i][key] for i in ids if b[i].get(key) is not None)
        d = [b[i][key] - a[i][key] for i in ids
             if a[i].get(key) is not None and b[i].get(key) is not None]
        lo, hi = _ci(d)
        fulldim[f"L{L}"] = {"A_v2_qwen3": round(va, 6), "B_v3_nomic": round(vb, 6),
                            "mean_delta_B_minus_A": round(statistics.mean(d), 6),
                            "ci95": [round(lo, 6), round(hi, 6)],
                            "resolved": bool(lo > 0 or hi < 0),
                            "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0)}
    # §I66's grid row N=3489 / L=500 = 0.8286 (v2, exact, no prefilter) — a second known-answer check.
    i66_fulldim = {"target_I66_N3489_L500": 0.8286, "measured_A_L500": fulldim["L500"]["A_v2_qwen3"],
                   "gap": (fulldim["L500"]["A_v2_qwen3"] - 0.8286)}
    i66_fulldim["pass"] = abs(i66_fulldim["gap"]) <= 0.002

    # G7 — arm B's gap row must BE the pooled index (pre-registration 2026-10-26 §4).
    i87_pooled = {"target_I87_pooled_L500": I87_POOLED_L500,
                  "measured_B_L500": fulldim["L500"]["B_v3_nomic"],
                  "gap": round(fulldim["L500"]["B_v3_nomic"] - I87_POOLED_L500, 6),
                  "tol": I87_TOL}
    i87_pooled["pass"] = abs(i87_pooled["gap"]) <= I87_TOL
    # G8 — arm A must be bit-stable against §I86 (v2 untouched; §I68 deterministic).
    i86_a_gaps = {k: round(A["aggregate"][k] - v, 9) for k, v in I86_ARM_A.items()}
    i86_a = {"target_I86_armA": I86_ARM_A, "measured": {k: A["aggregate"][k] for k in I86_ARM_A},
             "gaps": i86_a_gaps, "tol": I86_A_TOL,
             "pass": all(abs(g) <= I86_A_TOL for g in i86_a_gaps.values())}

    # raw product metrics (the OTHER unit — over all labelled pages)
    raw = {k: {"A_v2_qwen3": A["aggregate"][k], "B_v3_nomic": B["aggregate"][k]}
           for k in ("raw_r100_fusion", "raw_r20_ce")}
    by_type = {}
    for qt in ("factual", "multihop", "overview"):
        ii = [i for i in ids if a[i]["query_type"] == qt]
        by_type[qt] = {"n": len(ii), "cov_base": {"A": round(statistics.mean(a[i]["cov_base"] for i in ii), 6),
                                                  "B": round(statistics.mean(b[i]["cov_base"] for i in ii), 6)},
                       "cov_ce": {"A": round(statistics.mean(a[i]["cov_ce"] for i in ii), 6),
                                  "B": round(statistics.mean(b[i]["cov_ce"] for i in ii), 6)}}

    art = {
        "meta": {"what": "Stage G — the §I66 stage decomposition on BOTH arms (base → cut → fusion → cross-encoder)",
                 "arms": {"A": A["meta"], "B": B["meta"]},
                 "unit": "coverage of a REACHABLE labelled page set; raw R@k reported separately",
                 "n_queries": len(ids)},
        "guards": {"G1_A_config": True, "G2_B_config": True,
                   "G3_A_known_answer_I66": A["guards"]["G3_known_answer_I66"],
                   "G4_133_both_arms": len(a) == 133 and len(b) == 133,
                   "G5_same_corpus": A["meta"]["n_chunks"] == B["meta"]["n_chunks"],
                   "G6_A_fulldim_known_answer_I66": i66_fulldim["pass"],
                   "G7_B_fulldim_reproduces_I87_pooled": i87_pooled["pass"],
                   "G8_A_reproduces_I86_exactly": i86_a["pass"]},
        "known_answer": A["known_answer"],
        "decomposition": table,
        "deltas_B_minus_A": deltas,
        "fulldim_no_prefilter": fulldim,
        "i66_fulldim_cross_check": i66_fulldim,
        "i87_pooled_cross_check": i87_pooled,
        "i86_armA_cross_check": i86_a,
        "raw_product_metrics": raw,
        "by_type": by_type,
    }
    out.write_text(json.dumps(art, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({k: art[k] for k in ("guards", "decomposition", "deltas_B_minus_A",
                                          "fulldim_no_prefilter", "i66_fulldim_cross_check",
                                          "raw_product_metrics")}, indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}")
    failed = [k for k, v in art["guards"].items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["A", "B"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--combine", action="store_true")
    args = ap.parse_args()
    base = Path("logs/p1/step10")
    if args.combine:
        return combine({"A": base / "stageG_arm_A.json", "B": base / "stageG_arm_B.json"},
                       base / "stageG_decomposition.json")
    if not args.arm:
        ap.error("--arm or --combine required")
    out = Path(args.out) if args.out else base / f"stageG_arm_{args.arm}.json"
    return run_arm(args.arm, out, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
