"""T0 — the FULL-FUNNEL nomic BASELINE + the aperture (recall-vs-threshold) sweep.

Pre-registration: `.hermes/plans/2026-10-27-p1-t0-baseline-preregistration.md` (committed ALONE,
before this run). This file implements §2–§7 of that document and nothing else.

WHAT T0 IS. A CHARACTERISATION, not a ship test. ONE arm — the product as shipped on the adopted
embedder (`knowledge_base_v3` / `nomic-ai/nomic-embed-text-v1.5` @768/64) with the product's REAL
lane set ON (DA + graph), unlike Stage F/G which forced them OFF. It produces the reference table
that T1–T3 are read against, and it LOCATES the loss. It ships nothing and decides nothing.

THE FIVE BOUNDARIES (re-registration 2026-10-27 §2), and the SCORE SCALE at each — the load-bearing
part:

  1. base  — dense lane, EXACT 64d MRL @ N=1000             score = cosine        → THE APERTURE (swept)
  2. cut   — dense lane, EXACT full-dim @ L=500 (within 1)   score = cosine        → THE APERTURE (swept)
  3. fusion— the PRODUCT's `search_with_das` pool (fetch_k=100) score = RRF rank score (a RANK CUT)
  4. ce    — the PRODUCT's reranked top-20                    score = rerank score  (a third scale)
  5. b5    — the PRODUCT's dense lane THROUGH QDRANT (ANN) @ L=500, `query_text=None`
             score = cosine   → THE APERTURE (swept)         ⚠️ NEW in the re-registration

  ⚠️ 1–2 are EXACT BRUTE FORCE (§I66's method — no ANN, no Qdrant scoring, no RRF), which is what
  makes a cosine τ meaningful. 3–4 are the REAL product path. 5 is the DENSE LANE through the real
  index — one lane, so the score is still a cosine, but produced by Qdrant's ANN instead of by
  exhaustive arithmetic. ⇒ **B2 vs B5, same query vector and same limit, is the approximation loss
  as its own number.** The aperture sweep runs on 1, 2 and 5; a threshold at 3 is a rank cut and is
  never called an aperture.

  ⚠️ B5 is NOT boundary 3: 3 is the FUSED pool (all lanes, rank score, ≤100); 5 is the dense lane
  alone (cosine, ≤500). They are reported side by side and never conflated.

THE UNIT. Two units are reported and NEVER conflated:
  * the §I66 COVERAGE unit — coverage of a query's REACHABLE labelled pages — at all four boundaries,
    so T0 is comparable to §I66/§I86/§I89. This is the primary comparison.
  * the PRODUCT metric set (§6) at each boundary, computed with the product's own
    `evaluate_rag.compute_retrieval_metrics`. At every boundary the ranked unit is the PAGE (the
    product's own funnel is page-deduped at the fusion, and §6's metrics are page-level).

THE APERTURE UNIT. §5's "up to K documents": K=100 PAGES. The product's fusion output is page-deduped
to 100 candidates, so "the pool does the cutting" means 100 pages — and the metric is page-level.
`scoop` = the top-100 pages by cosine; `aperture@τ` = {cosine ≥ τ} ∩ top-100. `|{cos ≥ τ}|` is the
UNCAPPED admission over the boundary's whole candidate page set.

READ-ONLY: no writes to any collection, no re-ingest, no config change. The only LLM traffic is the
shared cluster embedder + cross-encoder (HyDE is served from the frozen §I73 cache; a miss RAISES).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
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
from evaluate_rag import compute_retrieval_metrics, run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
N, L = 1000, 500          # cfg.dense_prefetch_limit / cfg.dense_rescore_limit (asserted, G1)
FETCH_K, TOP_K = 100, 20  # cfg.reranker_fetch_k / cfg.reranker_top_k (asserted, G1)
K_APERTURE = 100          # §5's K — the aperture's own cap (pages)
TAUS = (0.0, 0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9)

# §3 — the single arm. `da_enabled=True` and the graph lane ON are the PRODUCT's values, NOT
# Stage F/G's forced false.
EXPECT = dict(collection="knowledge_base_v3", model="nomic-ai/nomic-embed-text-v1.5", dim=768,
              dim_low=64, doc_prefix="search_document: ", query_instruction="search_query: ")

# §7 G3 — the strongest anchor and it is DA-independent: §I89's arm-B EXACT rows.
I89_BASE, I89_CUT, I89_TOL = 0.918953, 0.838136, 0.002

# Metric keys the product function emits at k=20 (asserted present, G2).
PRODUCT_METRIC_KEYS = ("recall_at_100", "recall_at_20", "hit_at_20", "context_precision", "mrr",
                       "ndcg_at_20", "precision_at_20", "precision_ceiling_at_20", "f1_at_20", "map")


# ── shared helpers (mirrored from stageG_decomposition.py so the corpus is the SAME population) ──

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


def _dedup_pages(order: np.ndarray, pages: np.ndarray, cos: np.ndarray) -> list[list]:
    """Collapse a cosine-ordered chunk ranking to PAGES (first occurrence wins) with its cosine.

    The product's own funnel is page-deduped at the fusion, and every §6 metric is page-level, so
    the page is T0's ranked unit. Returns [[page, cosine], ...] in rank order.
    """
    seen: set[int] = set()
    out: list[list] = []
    for j in order:
        p = int(pages[j])
        if p in seen:
            continue
        seen.add(p)
        out.append([p, round(float(cos[j]), 6)])
    return out


def _dedup_hits(hits: list[dict]) -> list[list]:
    """Collapse Qdrant hits (already score-desc) to PAGES with the score that produced them.

    Boundary 5's unit, mirroring `_dedup_pages` for the exact boundaries.
    """
    seen: set[int] = set()
    out: list[list] = []
    for h in hits:
        p = h.get("page_number")
        if p is None or int(p) in seen:
            continue
        seen.add(int(p))
        out.append([int(p), round(float(h.get("score", 0.0)), 6)])
    return out


def _metrics_from_pages(ranked: list[list], rel: set[int], cfg) -> dict:
    """The product's own metric set, over a ranked PAGE list (hits = full list, reranked = top-k)."""
    hits = [{"page_number": p} for p, _ in ranked]
    return compute_retrieval_metrics({"hits": hits, "hits_above": hits,
                                      "reranked": hits[:cfg.reranker_top_k]}, sorted(rel), cfg)


def _aperture_curve(ranked: list[list], rel: set[int]) -> dict:
    """§5's sweep at ONE boundary. `ranked` = [[page, cosine], ...] in cosine-desc order.

    ⚠️ The admitted page SETS are deliberately NOT stored — the verifier re-derives them from
    `ranked` and τ (that is the point of an independent verifier). Only counts and metrics are
    recorded. `scoop_pages` is the top-K with NO threshold at all, computed on a separate path
    from the τ grid so G8 ("τ=0.0 == scoop") can actually fail: `{cos ≥ 0.0}` excludes a
    negative-cosine page, "no aperture" does not.
    """
    scoop = [p for p, _ in ranked[:K_APERTURE]]
    curve: dict[str, dict] = {}
    for tau in TAUS:
        admitted = [p for p, c in ranked[:K_APERTURE] if c >= tau]      # {cos >= tau} ∩ top-K
        admission = sum(1 for _, c in ranked if c >= tau)               # uncapped, whole candidate set
        hit = len(set(admitted) & rel)
        curve[f"{tau:.2f}"] = {
            "n_admitted": len(admitted),
            "admission_uncapped": admission,
            "recall_at_K": round(hit / len(rel), 6) if rel else None,
            "precision_at_K": round(hit / K_APERTURE, 6),
            "precision_ceiling_at_K": round(min(len(rel), K_APERTURE) / K_APERTURE, 6),
        }
    return {"scoop_pages": sorted(scoop), "curve": curve}


def _auc_pr(curve: dict) -> float | None:
    """AUC-PR from the sweep's own (recall, precision) points — trapezoid over recall ascending.

    W7 §6.1: a sweep recording precision AND recall at each τ IS the precision–recall curve.
    """
    pts = sorted(((v["recall_at_K"], v["precision_at_K"]) for v in curve.values()
                  if v["recall_at_K"] is not None))
    if len(pts) < 2:
        return None
    area = 0.0
    for (r0, p0), (r1, p1) in zip(pts, pts[1:]):
        area += (r1 - r0) * (p0 + p1) / 2.0
    return round(area, 6)


def _cov(stage_pages: set[int], reach: set[int]) -> float | None:
    return (len(stage_pages & reach) / len(reach)) if reach else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 6) if xs else None


# ── Robustness: the shared cluster STALLS ───────────────────────────────────────────────────────
# Measured 2026-10-27: the embed / rerank clients carry no request timeout, so a stalled shared
# endpoint blocks the process INDEFINITELY (a run sat at 0:48 CPU over 1 h 50 m of wall time with no
# output for 40 minutes). `socket.setdefaulttimeout` bounds every socket the clients open, and
# `_retry` re-attempts a whole product-path call so a transient stall becomes a retry rather than a
# scored query error (G2 requires 0 errors). NEITHER changes what is measured: no metric, no
# boundary, no ordering is touched — this only stops an infinite hang.
SOCKET_TIMEOUT = 90


def _retry(fn, *a, tries: int = 3, **kw):
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt == tries - 1:
                break
            logger.warning("retry {}/{} after {}: {}", attempt + 1, tries, type(exc).__name__, exc)
            time.sleep(5)
    raise last  # type: ignore[misc]


# ── the run ────────────────────────────────────────────────────────────────────────────────────

def run(out: Path, limit: int = 0, force: bool = False) -> int:
    # Bound every socket the clients open, so a stalled shared endpoint raises instead of hanging
    # the process forever (see the note on SOCKET_TIMEOUT above).
    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    if out.exists() and not force:
        logger.error("refusing to overwrite {} without --force", out)
        return 3

    cfg = get_settings()
    problems = []
    if not cfg.qdrant_host:
        problems.append("QDRANT_HOST blank — the derived lanes live on the cluster store")
    if cfg.qdrant_collection != EXPECT["collection"]:
        problems.append(f"collection {cfg.qdrant_collection!r} != {EXPECT['collection']!r}")
    if cfg.dense_model != EXPECT["model"] or cfg.dense_dim != EXPECT["dim"]:
        problems.append(f"model/dim {cfg.dense_model}/{cfg.dense_dim} != {EXPECT['model']}/{EXPECT['dim']}")
    if cfg.dense_dim_low != EXPECT["dim_low"]:
        problems.append(f"dim_low {cfg.dense_dim_low} != {EXPECT['dim_low']}")
    if cfg.document_prefix != EXPECT["doc_prefix"]:
        problems.append(f"doc_prefix {cfg.document_prefix!r} != {EXPECT['doc_prefix']!r}")
    if cfg.query_instruction != EXPECT["query_instruction"]:
        problems.append(f"query_instruction {cfg.query_instruction!r} != {EXPECT['query_instruction']!r}")
    if not cfg.da_enabled:
        problems.append("da_enabled is False — T0 runs the PRODUCT's lane set (DA ON)")
    if not cfg.splade_enabled:
        problems.append("splade_enabled is False — T0 runs the product's lane set")
    if not cfg.hyde_enabled:
        problems.append("hyde_enabled is False — T0 requires HyDE ON and frozen")
    if (cfg.dense_prefetch_limit, cfg.dense_rescore_limit) != (N, L):
        problems.append(f"N/L {(cfg.dense_prefetch_limit, cfg.dense_rescore_limit)} != {(N, L)}")
    if (cfg.reranker_fetch_k, cfg.reranker_top_k) != (FETCH_K, TOP_K):
        problems.append(f"fetch_k/top_k {(cfg.reranker_fetch_k, cfg.reranker_top_k)} != {(FETCH_K, TOP_K)}")
    g1 = {"collection": cfg.qdrant_collection == EXPECT["collection"],
          "model": cfg.dense_model == EXPECT["model"], "dim": cfg.dense_dim == EXPECT["dim"],
          "dim_low": cfg.dense_dim_low == EXPECT["dim_low"],
          "document_prefix": cfg.document_prefix == EXPECT["doc_prefix"],
          "query_instruction": cfg.query_instruction == EXPECT["query_instruction"],
          "da_enabled": bool(cfg.da_enabled), "splade_enabled": bool(cfg.splade_enabled),
          "hyde_enabled": bool(cfg.hyde_enabled),
          "N_L": (cfg.dense_prefetch_limit, cfg.dense_rescore_limit) == (N, L),
          "fetch_k_top_k": (cfg.reranker_fetch_k, cfg.reranker_top_k) == (FETCH_K, TOP_K)}
    if problems:
        for p in problems:
            logger.error("CONFIG FAIL: {}", p)
        print(json.dumps({"ok": False, "problems": problems}, indent=2))
        return 2

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    dense_name = store._dense_vector_name()
    low_name, low_size = _resolve_low_lane(store._collection_vectors(), cfg)

    queries = _load_queries()
    if limit:
        queries = queries[:limit]
    if not queries:
        logger.error("no queries loaded — aborting without writing")
        return 4

    # HyDE ON and FROZEN (§I73). A miss RAISES; it never falls back to a live LLM call.
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

    logger.info("T0 — {} {}d low={}({}) dense_lane={} N={} L={} fetch_k={} top_k={} DA={} queries={}",
                cfg.qdrant_collection, cfg.dense_dim, low_name, low_size, dense_name,
                N, L, FETCH_K, TOP_K, cfg.da_enabled, len(queries))

    filt = _content_filter(cfg)
    E, pages = _retry(_fetch_corpus, store._qdrant, cfg, filt, dense_name)
    coll_pages = {int(p) for p in pages.tolist()}
    logger.info("corpus: {} in-window content chunks / {} distinct pages", len(pages), len(coll_pages))

    Q = np.asarray([_retry(embedder.embed_query, q["query"]) for q in queries], dtype=np.float32)
    E64 = E[:, :low_size].copy(); E64 /= np.linalg.norm(E64, axis=1, keepdims=True) + 1e-12
    Q64 = Q[:, :low_size].copy(); Q64 /= np.linalg.norm(Q64, axis=1, keepdims=True) + 1e-12

    per_query, errors = [], []
    reranker_fallbacks = 0
    da_live = graph_live = 0
    t0 = time.time()
    try:
        for i, q in enumerate(queries, 1):
            qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
            rel = {int(p) for p in q["relevant_pages"]}
            reach = rel & coll_pages
            rec = {"id": qid, "query_type": qtype, "n_relevant": len(rel), "n_reachable": len(reach),
                   "relevant_pages": sorted(rel)}
            try:
                # ── boundaries 1–2: EXACT brute force (§I66's method) ───────────────────────
                c64 = E64 @ Q64[i - 1]
                order64 = np.argsort(-c64, kind="stable")[:N]
                base_ranked = _dedup_pages(order64, pages, c64)

                cfull = E[order64] @ Q[i - 1]
                within = np.argsort(-cfull, kind="stable")[:L]
                # `cfull` is ordered by RANK within the base lane; `_dedup_pages` indexes cosines by
                # CHUNK id, so scatter it back to chunk-index space first.
                cfull_by_chunk = np.zeros(len(pages), dtype=np.float64)
                cfull_by_chunk[order64] = cfull
                cut_ranked = _dedup_pages(order64[within], pages, cfull_by_chunk)

                # ── boundary 5: the PRODUCT's dense lane THROUGH QDRANT (the real ANN index) ──
                # ⚠️ `query_text=None` is what makes it dense-only: `_qdrant_search` skips the
                # SPLADE and ColBERT branches on their own guards (`cfg.splade_enabled and
                # query_text`), leaving the single-prefetch dense branch — so `.score` is the
                # full-dim COSINE rather than the fused RRF rank score. Same raw query vector and
                # same limit as boundary 2, so B2 vs B5 is single-variable: exact vs ANN.
                b5_hits = _retry(store.search, Q[i - 1], tenant_id=cfg.global_tenant_id,
                                 limit=L, query_text=None)
                b5_ranked = _dedup_hits(b5_hits)
                # G9 — the exact full-dim cosine of each page's best chunk, for the scale check.
                exact_full = E @ Q[i - 1]
                best_exact: dict[int, float] = {}
                for j, pg in enumerate(pages.tolist()):
                    pg = int(pg)
                    if exact_full[j] > best_exact.get(pg, -2.0):
                        best_exact[pg] = float(exact_full[j])

                # ── boundaries 3–4: the REAL product path (DA ON, graph ON) ─────────────────
                ret = _retry(run_retrieval, text, store, embedder, reranker, cfg, "global", 0.0,
                             query_type=qtype)
                fus_ranked = [[int(h["page_number"]), None] for h in ret["hits"] if h.get("page_number")]
                ce_ranked = [[int(h["page_number"]), None] for h in ret["reranked"][:TOP_K]
                             if h.get("page_number")]
                # G4 — a SECOND product-path repeat, bit-exact against the first.
                ret2 = _retry(run_retrieval, text, store, embedder, reranker, cfg, "global", 0.0,
                              query_type=qtype)
                fus2 = [[int(h["page_number"]), None] for h in ret2["hits"] if h.get("page_number")]
                ce2 = [[int(h["page_number"]), None] for h in ret2["reranked"][:TOP_K]
                       if h.get("page_number")]

                if ret.get("reranker_fallback"):
                    reranker_fallbacks += 1
                da_live += 1 if _retry(_da_live, store, cfg, Q[i - 1], qtype) else 0
                graph_live += 1 if _retry(_graph_live, cfg, text, Q[i - 1], qtype) else 0

                rec.update({
                    "base_ranked": base_ranked, "cut_ranked": cut_ranked,
                    "fusion_ranked": fus_ranked, "ce_ranked": ce_ranked,
                    "repeat_fusion_ranked": fus2, "repeat_ce_ranked": ce2,
                    "pool_size": len(fus_ranked), "n_ce": len(ce_ranked),
                    "reranker_fallback": bool(ret.get("reranker_fallback")),
                    "cov_base": _cov({p for p, _ in base_ranked}, reach),
                    "cov_cut": _cov({p for p, _ in cut_ranked}, reach),
                    "cov_fusion": _cov({p for p, _ in fus_ranked}, reach),
                    "cov_ce": _cov({p for p, _ in ce_ranked}, reach),
                    "m_base": _metrics_from_pages(base_ranked, rel, cfg),
                    "m_cut": _metrics_from_pages(cut_ranked, rel, cfg),
                    "m_fusion": _metrics_from_pages(fus_ranked, rel, cfg),
                    "m_ce": _metrics_from_pages(ce_ranked, rel, cfg),
                    "sweep_base": _aperture_curve(base_ranked, rel),
                    "sweep_cut": _aperture_curve(cut_ranked, rel),
                    # ── boundary 5 ──────────────────────────────────────────────────────────────
                    "b5_ranked": b5_ranked,
                    "cov_b5": _cov({p for p, _ in b5_ranked}, reach),
                    "m_b5": _metrics_from_pages(b5_ranked, rel, cfg),
                    "sweep_b5": _aperture_curve(b5_ranked, rel),
                    # G9 — |ANN score − the page's best EXACT full-dim cosine|, top-20 pages. A
                    # fused rank score would blow this up by an order of magnitude.
                    "b5_scale_gap_top20": _mean([
                        abs(c - best_exact.get(p, 0.0)) for p, c in b5_ranked[:20]]),
                    "b5_scores_in_range": all(-1.0 <= c <= 1.0 for _, c in b5_ranked),
                    # G10 — the ANN-vs-EXACT page overlap: how much of the ANN lane the exact lane
                    # also returns. The complement is the approximation loss at this limit.
                    "b5_overlap_with_cut": (
                        len({p for p, _ in b5_ranked} & {p for p, _ in cut_ranked})
                        / len({p for p, _ in b5_ranked})) if b5_ranked else None,
                    "b5_n_pages": len(b5_ranked),
                })
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
                logger.error("[{}] FAILED: {}", qid, exc)
                per_query.append({**rec, "error": str(exc)})
                continue
            per_query.append(rec)
            if i % 20 == 0:
                logger.info("  {}/{}", i, len(queries))
    finally:
        llm_mod.call_llm = _real_llm
    wall = time.time() - t0

    art = _assemble(cfg, per_query, errors, wall, g1, reranker_fallbacks, da_live, graph_live,
                    len(pages), sorted(coll_pages), low_name, low_size, dense_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(art, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({"guards": art["guards"], "aggregate": art["aggregate"],
                      "aperture_scoop": art["aperture_scoop"]}, indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}\nwall: {round(wall,1)}s")
    failed = [k for k, v in art["guards"].items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


def _da_live(store, cfg, qv, qtype) -> bool:
    try:
        return bool(store.search_da(qv, tenant_id=cfg.global_tenant_id, limit=cfg.da_fetch_k))
    except Exception:  # noqa: BLE001
        return False


def _graph_live(cfg, text, qv, qtype) -> bool:
    if qtype != "multihop":
        return False
    try:
        from src.pdf_ingestion.graph_builder import get_graph_builder
        return bool(get_graph_builder(cfg).graph_search(
            query_text=text, tenant_id=cfg.global_tenant_id, query_vector=qv, limit=5))
    except Exception:  # noqa: BLE001
        return False


def _assemble(cfg, per_query, errors, wall, g1, fallbacks, da_live, graph_live,
              n_chunks, coll_pages, low_name, low_size, dense_name) -> dict:
    n_pages = len(coll_pages)
    ok = [r for r in per_query if "error" not in r]
    n = len(ok)
    by_type = ("factual", "multihop", "overview")

    def agg_boundary(sub, cov_key, m_key):
        out = {"coverage_reachable": _mean(r[cov_key] for r in sub)}
        for mk in PRODUCT_METRIC_KEYS:
            out[mk] = _mean(r[m_key].get(mk) for r in sub)
        out["pool_size_mean"] = _mean(r["pool_size"] for r in sub if "pool_size" in r)
        return out

    aggregate = {}
    for label, cov_key, m_key in (("base", "cov_base", "m_base"), ("cut", "cov_cut", "m_cut"),
                                  ("fusion", "cov_fusion", "m_fusion"), ("ce", "cov_ce", "m_ce"),
                                  ("b5", "cov_b5", "m_b5")):
        aggregate[label] = {"overall": agg_boundary(ok, cov_key, m_key),
                            "by_type": {qt: {**agg_boundary([r for r in ok if r["query_type"] == qt],
                                                            cov_key, m_key), "n": sum(1 for r in ok if r["query_type"] == qt)}
                                        for qt in by_type}}

    # §5 — the aperture sweep. Monotonicity (G7) and τ=0 == scoop (G8) are checked per boundary.
    aperture = {}
    monotone_ok, tau0_ok = True, True
    n_neg_in_topk = 0
    for label, skey, rkey in (("base", "sweep_base", "base_ranked"),
                              ("cut", "sweep_cut", "cut_ranked"),
                              ("b5", "sweep_b5", "b5_ranked")):
        curves = {r["id"]: r[skey] for r in ok}
        ranked_map = {r["id"]: r[rkey] for r in ok}
        n_neg_in_topk += sum(1 for r in ok
                             for _, c in ranked_map[r["id"]][:K_APERTURE] if c < 0.0)
        per_tau = {}
        for tau in TAUS:
            tk = f"{tau:.2f}"
            sub = [r for r in ok]
            per_tau[tk] = {
                "recall_at_K": _mean(curves[r["id"]]["curve"][tk]["recall_at_K"] for r in sub),
                "precision_at_K": _mean(curves[r["id"]]["curve"][tk]["precision_at_K"] for r in sub),
                "precision_ceiling_at_K": _mean(curves[r["id"]]["curve"][tk]["precision_ceiling_at_K"] for r in sub),
                "admission_uncapped_mean": _mean(curves[r["id"]]["curve"][tk]["admission_uncapped"] for r in sub),
                "n_admitted_mean": _mean(curves[r["id"]]["curve"][tk]["n_admitted"] for r in sub),
                "recall_at_K_by_type": {qt: _mean(curves[r["id"]]["curve"][tk]["recall_at_K"]
                                                  for r in ok if r["query_type"] == qt) for qt in by_type},
            }
        # G7 — recall@K and the uncapped admission must be non-increasing in τ.
        recs = [per_tau[f"{t:.2f}"]["recall_at_K"] for t in TAUS]
        adms = [per_tau[f"{t:.2f}"]["admission_uncapped_mean"] for t in TAUS]
        mono = all(None not in (a, b) and b <= a + 1e-9 for a, b in zip(recs, recs[1:])) and \
               all(None not in (a, b) and b <= a + 1e-9 for a, b in zip(adms, adms[1:]))
        monotone_ok = monotone_ok and mono
        # G8 — τ=0.0 aperture arm == the scoop arm, exactly, every query. Computed on two separate
        # paths (`{cos >= 0.0} ∩ top-K` vs the bare `top-K`) so it can actually fail on a negative
        # cosine — "no aperture" is not the same statement as "threshold zero".
        t0ok = all({p for p, c in ranked_map[r["id"]][:K_APERTURE] if c >= 0.0}
                   == {p for p, _ in ranked_map[r["id"]][:K_APERTURE]} for r in ok)
        tau0_ok = tau0_ok and t0ok
        # AUC-PR per query, then mean.
        aucs = [_auc_pr({k: v for k, v in curves[r["id"]]["curve"].items()}) for r in ok]
        aperture[label] = {"per_tau": per_tau, "monotone_non_increasing": mono,
                           "tau0_equals_scoop": t0ok, "auc_pr_mean": _mean(aucs),
                           "scoop_recall_at_K": _mean(
                               len(set(curves[r["id"]]["scoop_pages"]) & set(r["relevant_pages"])) / r["n_relevant"]
                               for r in ok if r["n_relevant"])}

    g3_base = aggregate["base"]["overall"]["coverage_reachable"]
    g3_cut = aggregate["cut"]["overall"]["coverage_reachable"]
    g3 = (g3_base is not None and abs(g3_base - I89_BASE) <= I89_TOL
          and g3_cut is not None and abs(g3_cut - I89_CUT) <= I89_TOL)
    g4_bad = [r["id"] for r in ok
              if r["fusion_ranked"] != r["repeat_fusion_ranked"] or r["ce_ranked"] != r["repeat_ce_ranked"]]
    # G9 — boundary 5 must be on a COSINE scale. A lane that silently fell back to the fused path
    # would still return pages and still score within [-1, 1]; only the score's SHAPE catches it.
    # Test: the ANN score of each top-20 page must sit close to that page's best EXACT full-dim
    # cosine. Qdrant's dense-only path re-scores the candidates it returns exactly, so the gap is
    # the ANN's candidate loss, not a scale error — a fused rank score would be out by ~0.3+.
    b5_gap = _mean(r["b5_scale_gap_top20"] for r in ok)
    g9_ok = (b5_gap is not None and b5_gap <= 0.05
             and all(r["b5_scores_in_range"] for r in ok))
    # G10 — boundary 5 returns at least one page on EVERY query, and the ANN-vs-exact overlap is
    # recorded on every query (so the approximation gap cannot be silently dropped).
    g10_ok = all(r["b5_n_pages"] >= 1 and r["b5_overlap_with_cut"] is not None for r in ok)
    guards = {
        "G1_config_resolved": all(g1.values()),
        "G2_all_queries_scored": (n == len(per_query)) and len(errors) == 0
                                 and all("n_relevant" in r for r in per_query),
        "G3_reproduces_I89_arm_B_exact": g3,
        "G4_product_path_bit_exact_on_repeat": not g4_bad,
        "G5_reranked_metrics_valid": fallbacks == 0,
        "G6_lane_liveness": (da_live > 0) and (graph_live > 0),
        "G7_sweep_monotone_non_increasing": monotone_ok,
        "G8_tau0_equals_scoop": tau0_ok,
        "G9_b5_is_a_cosine_scale": g9_ok,
        "G10_b5_nonempty_and_overlap_recorded": g10_ok,
    }
    return {
        "meta": {
            "what": "T0 — the FULL-FUNNEL nomic baseline + the aperture sweep (one arm, product lane set ON)",
            "arm": f"{cfg.qdrant_collection} / {cfg.dense_model} / {cfg.dense_dim} / low {cfg.dense_dim_low}",
            "qdrant_host": cfg.qdrant_host, "collection": cfg.qdrant_collection,
            "dense_model": cfg.dense_model, "dense_dim": cfg.dense_dim,
            "dense_lane": dense_name, "low_lane": low_name, "low_size": low_size,
            "document_prefix": cfg.document_prefix, "query_instruction": cfg.query_instruction,
            "da_enabled": bool(cfg.da_enabled), "da_collection": cfg.da_collection,
            "splade_enabled": bool(cfg.splade_enabled), "colbert_enabled": bool(cfg.colbert_enabled),
            "graph_lane": "ON", "hyde": "ON, frozen (data/hyde_cache)",
            "raptor": "ABSENT from v3 and NOT on the eval path (B1/B2 unbuilt)",
            "visual_lane": "not measured (no ColPali data for the new doc; vis-* carry no labels)",
            "N": N, "L": L, "fetch_k": FETCH_K, "top_k": TOP_K, "K_aperture": K_APERTURE,
            "tau_grid": list(TAUS),
            "fusion": {"mmr_variant": "RRF-score relevance + Jaccard diversity",
                       "mmr_lambda": cfg.mmr_lambda, "W": cfg.mmr_candidates,
                       "threshold": 0.0, "rrf_k": 1},
            "units": {"coverage_reachable": "§I66's unit — coverage of a query's REACHABLE labelled pages",
                      "product_metrics": "pages of the top-k CHUNKS (product convention, evaluate_rag:333-341)",
                      "ranked_unit": "the PAGE at every boundary; boundaries 1-2 are exact brute force",
                      "aperture_unit": f"pages; K={K_APERTURE} (the product's page-deduped pool width)",
                      "boundary_5": ("the product's dense lane THROUGH QDRANT (real ANN) at the same "
                                     "limit as boundary 2 and the SAME raw query vector, so B2 vs B5 "
                                     "isolates the approximation loss; query_text=None keeps it "
                                     "dense-only so .score stays a COSINE")},
            "n_chunks": n_chunks, "n_pages": n_pages, "n_queries": n, "n_errors": len(errors),
            # The reachable-label denominator, recorded so a verifier can re-derive `reach`
            # (relevant_pages ∩ coll_pages) INDEPENDENTLY of the harness.
            "coll_pages": coll_pages,
            "n_reranker_fallbacks": fallbacks, "da_live_queries": da_live,
            "graph_live_queries": graph_live, "wall_seconds": round(wall, 1),
            "population": "data/eval_queries_v2.json — gold-* + ovw-*, 133 labelled (NOT vis-*, NOT neg-*)",
        },
        "guards": guards, "guard_detail": {"G1_fields": g1,
            "G8_n_negative_cosines_in_topK": n_neg_in_topk,
            "G3_target": {"base": I89_BASE, "cut": I89_CUT, "tol": I89_TOL,
                          "measured": {"base": g3_base, "cut": g3_cut}},
            "G4_mismatched_queries": g4_bad,
            "G9_b5_mean_scale_gap_top20": b5_gap,
            "G10_b5_mean_overlap_with_exact": _mean(r["b5_overlap_with_cut"] for r in ok)},
        "aggregate": aggregate,
        "aperture": aperture,
        "aperture_scoop": {lb: aperture[lb]["scoop_recall_at_K"] for lb in aperture},
        "errors": errors,
        "per_query": per_query,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="logs/p1/step10/t0_baseline.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    return run(Path(args.out), limit=args.limit, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
