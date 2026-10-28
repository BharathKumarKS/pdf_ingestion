"""Fusion attribution — which part of `RRF → page dedup → MMR` eats the pages.

Pre-registration: `.hermes/plans/2026-10-27-p1-fusion-attribution-preregistration.md` (committed ALONE
before the run). Implements §3/§4/§6 of that document and nothing else.

THE QUESTION. T0 (§I90) measured the funnel's two big losses: the fusion (−0.1537 coverage) and the
cross-encoder (−0.2292). The fusion does three things in sequence — RRF merge → page dedup → MMR — and
the split has never been attributed. This run separates them by moving ONLY the product's own config
knobs, never by re-implementing the funnel.

WHAT THE CODE SAYS (store.py:848-918), and why the arms are what they are:
  1. `dense_hits = search(qv, limit=mmr_candidates)`   — the fused (dense+sparse+colbert, RRF) list, capped
  2. DA lane appends resolved parents                  — can push len(dense_hits) above the cap
  3. page dedup                                        — keeps the best chunk per page
  4. `if mmr_enabled and len(deduped) > reranker_fetch_k: _mmr_select(deduped, top_k=fetch_k)`
     `else: deduped[:reranker_fetch_k]`
So MMR can only fire when deduped > reranker_fetch_k, and the pool is re-capped at reranker_fetch_k — which
is why the width arm must move BOTH knobs (T0's product pool averages 86.47 pages, i.e. below 100).

THE ANCHORS (guards G1/G2/G2b). Arm C is T0's fusion boundary, so it must reproduce T0's coverage
(0.684486) AND T0's mean pool size (86.466165); D500_raw is T0's boundary 5, so it must reproduce
0.838136. Three anchors on two boundaries — "this is T0's instrument" becomes a measurement.

READ-ONLY. No writes to any collection, no re-ingest, no `src/` change. DA ON and the graph lane ON (T0's
lane set). HyDE ON and frozen (a cache miss RAISES). The ONE instrumentation is a RECORDING wrapper around
`search_with_das` that captures the query vector it was called with — needed so the dense-only reference
arm uses arm C's own (HyDE-augmented) vector rather than the raw one; it changes no behaviour.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
from loguru import logger

from src.core.config import get_settings
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for
from src.pdf_ingestion.reranker import get_reranker
from src.pdf_ingestion.store import DocumentStore

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from evaluate_rag import run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
T0_ARTIFACT = "logs/p1/step10/t0_baseline.json"
BASE = Path("logs/p1/step10")

# §6 — the three anchors, read from T0's registered artifact.
T0_FUSION_COVERAGE = 0.684486
T0_FUSION_POOL_MEAN = 86.466165
T0_B5_COVERAGE = 0.838136
ANCHOR_TOL = 1e-6

# §3 — the product arms. Only the product's own config knobs move.
PRODUCT_ARMS = {
    "C":          dict(mmr_enabled=True,  mmr_candidates=100, reranker_fetch_k=100),
    "C_nommr":    dict(mmr_enabled=False, mmr_candidates=100, reranker_fetch_k=100),
    "W500":       dict(mmr_enabled=True,  mmr_candidates=500, reranker_fetch_k=500),
    "W500_nommr": dict(mmr_enabled=False, mmr_candidates=500, reranker_fetch_k=500),
}
# §3 — the dense-only references: (limit, which captured vector). `D100` uses arm C's own vector.
DENSE_ARMS = {"D100": (100, "hyde"), "D100_raw": (100, "raw"), "D500_raw": (500, "raw")}

socket.setdefaulttimeout(90)
RETRIES = 3

# The ONE instrumentation: record the vector `search_with_das` was called with. Changes no behaviour.
_CAPTURED: dict[str, np.ndarray] = {}
_orig_search_with_das = DocumentStore.search_with_das


def _recording_search_with_das(self, query_vector, *a, **kw):
    _CAPTURED["vec"] = np.array(query_vector, dtype=np.float32)
    return _orig_search_with_das(self, query_vector, *a, **kw)


DocumentStore.search_with_das = _recording_search_with_das


def _load_queries() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _reachable_pages(store, cfg) -> set[int]:
    """T0's `coll_pages`: every in-window content page the product filter can reach (read-only scroll)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    must_not = [FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
    if cfg.min_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(lt=cfg.min_content_page)))
    if cfg.max_content_page > 0:
        must_not.append(FieldCondition(key="page_number", range=Range(gt=cfg.max_content_page)))
    must_not.append(FieldCondition(key="is_content", match=MatchValue(value=False)))
    flt = Filter(must_not=must_not)

    pages: set[int] = set()
    offset = None
    while True:
        recs, offset = store._qdrant.scroll(
            collection_name=cfg.qdrant_collection, scroll_filter=flt,
            limit=1000, offset=offset, with_payload=["page_number"], with_vectors=False,
        )
        for r in recs:
            p = (r.payload or {}).get("page_number")
            if p is not None:
                pages.add(int(p))
        if offset is None:
            break
    return pages


def _pages_of(hits) -> list[int]:
    """Distinct pages, in order of first appearance (the pool is already page-deduped by the product)."""
    seen, out = set(), []
    for h in hits:
        p = h.get("page_number")
        if p is None:
            continue
        p = int(p)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _retry(fn, *a, **kw):
    last = None
    for attempt in range(RETRIES):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("attempt {}/{} failed: {}", attempt + 1, RETRIES, exc)
            if attempt + 1 < RETRIES:
                time.sleep(5)
    raise last


def _cov(pages, reach: set[int]):
    if not reach:
        return None
    return len(set(pages) & reach) / len(reach)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(BASE / "fusion_attribution.json"))
    args = ap.parse_args()

    cfg = get_settings()
    if not cfg.da_enabled:
        logger.error("G-lane: da_enabled is False — this run needs T0's lane set (DA ON)")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)

    queries = _load_queries()
    if args.limit:
        queries = queries[: args.limit]

    # HyDE ON and frozen — a miss raises (§4).
    cache = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map: dict[str, str] = {}
    for q in queries:
        if q.get("query_type") in ("factual", "overview"):
            prompt_map[prompt_for(q["query"])] = cache.get(q["id"])

    import src.core.llm as llm_mod
    _real_call_llm = llm_mod.call_llm

    def _frozen_llm(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        raise RuntimeError(f"HyDE cache miss mid-run for prompt {str(prompt)[:90]!r} (§4)")

    llm_mod.call_llm = _frozen_llm

    reach = _reachable_pages(store, cfg)
    logger.info("reachable content pages: {} (T0 recorded 888)", len(reach))

    # One store + one cfg per arm, built ONCE (a DocumentStore opens a Qdrant client and a SQLite engine;
    # building one per query per arm would dominate the run's cost).
    ARM_CFGS = {a: cfg.model_copy(update=o) for a, o in PRODUCT_ARMS.items()}
    ARM_STORES = {a: DocumentStore(c) for a, c in ARM_CFGS.items()}

    per_query: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()
    try:
        for i, q in enumerate(queries, 1):
            qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
            rel = {int(p) for p in q["relevant_pages"]}
            rq = rel & reach
            # `relevant_pages` is stored so an INDEPENDENT verifier can re-derive coverage from the
            # per-query page arrays alone. Every page the product's search returns is in-window
            # (the filter is applied inside `search()`), so |pages ∩ reachable| == |pages ∩ relevant|.
            rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel), "n_reachable": len(rq),
                         "relevant_pages": sorted(rel)}
            try:
                # the raw query vector — computed once, used by the *_raw dense arms
                qv_raw = np.array(_retry(embedder.embed_query, text), dtype=np.float32)

                for arm in PRODUCT_ARMS:
                    cfg_arm, store_arm = ARM_CFGS[arm], ARM_STORES[arm]
                    ret = _retry(run_retrieval, text, store_arm, embedder, reranker, cfg_arm,
                                 "global", 0.0, query_type=qtype)
                    pages = _pages_of(ret["hits"])
                    hyde_vec = _CAPTURED.get("vec")          # the vector this arm's fusion used
                    rec[f"{arm}_pages"] = pages
                    # T0's own definition of pool size: hits carrying a page number (the graph lane can
                    # append hits with `page_number` None; T0's `fus_ranked` dropped those, so counting
                    # raw hits would disagree with T0 by a handful while the PAGE SET is identical).
                    rec[f"{arm}_pool_size"] = sum(1 for h in ret["hits"] if h.get("page_number"))
                    rec[f"{arm}_cov"] = _cov(pages, rq)
                    if arm == "C":
                        rec["_hyde_vec"] = hyde_vec         # kept in memory only; not written
                        # determinism (G5) — arm C run a SECOND time
                        ret2 = _retry(run_retrieval, text, store_arm, embedder, reranker, cfg_arm,
                                      "global", 0.0, query_type=qtype)
                        rec["C2_pages"] = _pages_of(ret2["hits"])
                        rec["C2_cov"] = _cov(rec["C2_pages"], rq)

                # the dense-only references
                hyde_vec = rec.pop("_hyde_vec", None)
                for arm, (lim, which) in DENSE_ARMS.items():
                    vec = hyde_vec if which == "hyde" else qv_raw
                    if vec is None:
                        raise RuntimeError(f"{arm}: no captured vector")
                    hits = _retry(store.search, vec, tenant_id=cfg.global_tenant_id,
                                  limit=lim, query_text=None)
                    pages = _pages_of(hits)
                    rec[f"{arm}_pages"] = pages
                    rec[f"{arm}_pool_size"] = sum(1 for h in hits if h.get("page_number"))
                    rec[f"{arm}_cov"] = _cov(pages, rq)

                per_query.append(rec)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
                logger.error("[{}] FAILED: {}", qid, exc)
                per_query.append({**rec, "error": str(exc)})
            if i % 20 == 0:
                logger.info("  {}/{} queries", i, len(queries))
    finally:
        llm_mod.call_llm = _real_call_llm
    wall = time.time() - t0

    ok = [r for r in per_query if "error" not in r]

    def agg(arm: str, sub=None):
        rows = sub if sub is not None else ok
        covs = [r[f"{arm}_cov"] for r in rows if r.get(f"{arm}_cov") is not None]
        pools = [r[f"{arm}_pool_size"] for r in rows if f"{arm}_pool_size" in r]
        return {"n": len(covs), "coverage": statistics.mean(covs) if covs else None,
                "pool_mean": statistics.mean(pools) if pools else None,
                "pool_min": min(pools) if pools else None, "pool_max": max(pools) if pools else None}

    all_arms = list(PRODUCT_ARMS) + list(DENSE_ARMS)
    aggregate = {arm: {"overall": agg(arm),
                       "by_type": {qt: agg(arm, [r for r in ok if r["query_type"] == qt])
                                   for qt in ("factual", "multihop", "overview")}}
                 for arm in all_arms}

    def delta(a_arm: str, b_arm: str, key="cov"):
        """Paired mean over queries where both arms scored."""
        d = [(r[f"{b_arm}_{key}"] - r[f"{a_arm}_{key}"])
             for r in ok if r.get(f"{a_arm}_{key}") is not None and r.get(f"{b_arm}_{key}") is not None]
        return {"n": len(d), "mean": statistics.mean(d) if d else None}

    deltas = {
        "W500_minus_C": delta("C", "W500"),
        "C_nommr_minus_C": delta("C", "C_nommr"),
        "W500_nommr_minus_W500": delta("W500", "W500_nommr"),
        "C_minus_D100": delta("D100", "C"),
        "D100_minus_D100_raw": delta("D100_raw", "D100"),
        "D500_raw_minus_D100_raw": delta("D100_raw", "D500_raw"),
    }

    # ── guards ────────────────────────────────────────────────────────────────────────────────────
    def near(a, b, tol=ANCHOR_TOL):
        return a is not None and b is not None and abs(a - b) <= tol

    c_cov = aggregate["C"]["overall"]["coverage"]
    c_pool = aggregate["C"]["overall"]["pool_mean"]
    d500_cov = aggregate["D500_raw"]["overall"]["coverage"]

    dup = {}
    for arm in PRODUCT_ARMS:
        bad = [r["id"] for r in ok if len(r[f"{arm}_pages"]) != len(set(r[f"{arm}_pages"]))]
        dup[arm] = bad
    c_vs_c2 = [r["id"] for r in ok if r.get("C2_pages") != r.get("C_pages")]
    not_nested = [r["id"] for r in ok
                  if not set(r["C_pages"]) <= set(r["W500_pages"])]

    # G7 — the denominator did not move. T0 records the corpus page SET itself (`meta.coll_pages`), so the
    # comparison is on the set, not just its size: T0 has no sha field (checked — its meta carries
    # n_pages 888 and the list coll_pages), and comparing the list is strictly stronger anyway.
    t0_meta = json.loads(Path(T0_ARTIFACT).read_text())["meta"]
    t0_pages = {int(p) for p in t0_meta["coll_pages"]}
    my_sha = hashlib.sha256(",".join(str(p) for p in sorted(reach)).encode()).hexdigest()[:16]
    t0_sha = hashlib.sha256(",".join(str(p) for p in sorted(t0_pages)).encode()).hexdigest()[:16]
    reach_set_identical = (reach == t0_pages)

    guards = {
        "G1_C_reproduces_T0_fusion_coverage": near(c_cov, T0_FUSION_COVERAGE),
        "G2_C_reproduces_T0_fusion_pool_mean": near(c_pool, T0_FUSION_POOL_MEAN),
        "G2b_D500_raw_reproduces_T0_boundary5": near(d500_cov, T0_B5_COVERAGE),
        "G3_133_scored_0_errors": (len(ok) == len(queries) and not errors),
        "G4_pools_are_page_deduped": all(not v for v in dup.values()),
        "G5_arm_C_bit_exact_on_repeat": not c_vs_c2,
        "G6_pages_C_subset_of_pages_W500": not not_nested,
        "G7_reachable_set_matches_T0": reach_set_identical,
        "G8_width_arms_moved_both_knobs": all(
            PRODUCT_ARMS[a]["mmr_candidates"] == PRODUCT_ARMS[a]["reranker_fetch_k"]
            for a in ("C", "W500", "W500_nommr")),
    }

    artifact = {
        "meta": {
            "question": "which component of the fusion (RRF -> dedup -> MMR) drops T0's pages?",
            "prereg": ".hermes/plans/2026-10-27-p1-fusion-attribution-preregistration.md",
            "collection": cfg.qdrant_collection, "dense_model": cfg.dense_model,
            "dense_dim": cfg.dense_dim, "qdrant_host": cfg.qdrant_host,
            "da_enabled": bool(cfg.da_enabled), "graph_lane": "ON",
            "hyde": "ON and frozen", "hyde_cache": cache.path.name,
            "mmr_lambda": cfg.mmr_lambda,
            "mmr_variant": "RRF-score relevance + Jaccard diversity (store.py:810-846)",
            "arms": {**PRODUCT_ARMS, **{k: {"limit": v[0], "vector": v[1]} for k, v in DENSE_ARMS.items()}},
            "anchors": {"T0_fusion_coverage": T0_FUSION_COVERAGE,
                        "T0_fusion_pool_mean": T0_FUSION_POOL_MEAN,
                        "T0_boundary5_coverage": T0_B5_COVERAGE, "tol": ANCHOR_TOL},
            "reachable_pages": len(reach), "reachable_pages_set_sha": my_sha,
            "t0_reachable_pages_set_sha": t0_sha,
            "n_queries": len(queries), "n_errors": len(errors), "wall_seconds": round(wall, 1),
            "unit": "coverage of a query's REACHABLE labelled pages (T0's §I66 unit)",
        },
        "aggregate": aggregate,
        "deltas": deltas,
        "guards": guards,
        "guard_detail": {"page_dedup_violations": dup, "C_vs_C2_page_mismatch_ids": c_vs_c2,
                         "non_nested_ids": not_nested},
        "errors": errors,
        "per_query": [{k: v for k, v in r.items() if not k.startswith("_")} for r in per_query],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()

    print(json.dumps({"aggregate": {a: aggregate[a]["overall"] for a in all_arms},
                      "deltas": deltas, "guards": guards, "guard_detail": artifact["guard_detail"]},
                     indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
