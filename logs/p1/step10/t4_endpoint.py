"""T4 — the ENDPOINT ATTRIBUTION: is the pool → top-20 loss the cross-encoder, the 20-slot cut, or the
CE's query text?

Pre-registration: `.hermes/plans/2026-10-27-p1-endpoint-attribution-preregistration.md` (committed ALONE
before this run, D6.1). Implements §2/§3/§4 of that document and nothing else.

THE QUESTION. T0 (§I90) measured the funnel's largest single loss at the pool → top-20 step (coverage
0.6845 → 0.4553). Its artifact already implies the cross-encoder makes the top-20 WORSE than doing
nothing: the `fusion` row is the pool's own RRF order and the `ce` row is the CE's order, and nDCG
0.5506 → 0.4946, MAP 0.3421 → 0.2789, MRR 0.7687 → 0.6668. Three causes, different fixes, never separated:
  (1) the CE reorders badly      → arm N (no CE at all)
  (2) the 20-slot cut discards   → arm W50 (the CE, cut at 50)
  (3) ⚠️ the CE is fed the HyDE HYPOTHETICAL as its query, not the question (`evaluate_rag.py:206`) → arm Q

THE TWO EXACT ANCHORS (§4). Arm C is T0's `ce` boundary and arm N is T0's `fusion` boundary, so each must
reproduce that row field by field at 1e-4 (the metrics are `round(..., 4)`). Both are T0's OWN metric
function: `t0_baseline._metrics_from_pages` calls `compute_retrieval_metrics` with hits = hits_above = the
boundary's page list and reranked = that list[:cfg.reranker_top_k] — which is exactly what the product's
`run_retrieval` produces for these two arms. With no CE the top-20 IS the pool's top-20, and the pool is
page-deduped, so the page conventions coincide.

⚠️ §11 — `recall_at_100` is EXCLUDED from arm C's anchor: T0's `ce` row computes it over the 20-page ce
list (so it equals its R@20 by construction), while the product's metric computes it over the POOL. Arm C,
N and Q must all show the POOL figure, 0.6706.

READ-ONLY. No writes to any collection, no re-ingest, no `src/` change. DA ON and the graph lane ON (T0's
lane set). HyDE ON and frozen (a cache miss RAISES). The ONE instrumentation is a wrapper around the
reranker instance's `rerank` that substitutes the raw query for arm Q — needed because the product feeds it
the hypothetical; it changes nothing else, and G5 proves it took effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
from evaluate_rag import compute_retrieval_metrics, run_retrieval  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
T0_ARTIFACT = "logs/p1/step10/t0_baseline.json"
BASE = Path("logs/p1/step10")

ANCHOR_TOL = 1e-4          # the metrics are round(..., 4)

# §2 — the arms. Only the product's own knobs move, plus the Q wrapper.
ARMS = {
    "C":   dict(reranker_enabled=True,  reranker_top_k=20, rerank_query="product"),
    "N":   dict(reranker_enabled=False, reranker_top_k=20, rerank_query="product"),
    "Q":   dict(reranker_enabled=True,  reranker_top_k=20, rerank_query="raw"),
    "W50": dict(reranker_enabled=True,  reranker_top_k=50, rerank_query="product"),
}
# §4 G1 — arm C vs T0's `ce` row; G2 — arm N vs T0's `fusion` row.
# ⚠️ §12 — T0's `ce` row scores the ce LIST alone, so every field of it is an ENDPOINT metric (its
# `recall_at_100` equals its `recall_at_20` by construction, and its `mrr` is the ce list's). T0's
# `fusion` row scores the full pool for `hits`, so its `mrr` and `recall_at_100` are POOL metrics while
# the rest are endpoint metrics. Hence the two key sets differ.
ENDPOINT_KEYS = ("coverage_reachable", "recall_at_20", "precision_at_20", "f1_at_20",
                 "ndcg_at_20", "map", "hit_at_20", "mrr_at_20")
G1_KEYS = ENDPOINT_KEYS
G2_KEYS = ENDPOINT_KEYS + ("mrr", "recall_at_100")   # the two POOL fields, valid only for arm N
# The metric fields the harness computes, keyed by the arm's own k.
def _mkeys(k: int) -> tuple[str, ...]:
    return (f"recall_at_{k}", f"precision_at_{k}", f"precision_ceiling_at_{k}", f"f1_at_{k}",
            f"ndcg_at_{k}", f"hit_at_{k}", f"mrr_at_{k}", "map", "mrr")

socket.setdefaulttimeout(90)
RETRIES = 3

# The ONE instrumentation: substitute the raw query at the reranker call (arm Q only).
_RERANK_OVERRIDE: dict[str, str | None] = {"text": None}
# ⚠️ G5's DIRECT proof (independent review, item 1): count the calls where the substitution actually
# FIRED. Testing "arm Q differs from arm C somewhere" is not the same as proving the override was read on
# every call — at n=133 a coincidence is implausible, but a counter is strictly better.
_OVERRIDE_HITS: dict[str, int] = {"n": 0}


def _install_rerank_wrapper(reranker):
    orig = reranker.rerank

    def _wrapped(query, chunks, top_k):
        if _RERANK_OVERRIDE["text"] is not None:
            _OVERRIDE_HITS["n"] += 1        # the override was READ and USED, not merely set
            return orig(_RERANK_OVERRIDE["text"], chunks, top_k)
        return orig(query, chunks, top_k)

    reranker.rerank = _wrapped          # instance attribute shadows the class method
    return orig


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


def _endpoint_mrr(pages: list[int], rel: set[int]) -> float:
    """⚠️ MRR over the ENDPOINT list — the product's own `mrr` is a POOL metric (see §12).

    `compute_retrieval_metrics` computes `mrr` from `retrieval["hits"]`, which is the POOL, so it is
    identical in every arm and cannot answer this run's MRR question. T0's `ce` row's MRR is an endpoint
    MRR (it scores the ce list alone), which is why this exists and why arm C must reproduce it.
    """
    for rank, p in enumerate(pages, start=1):
        if p in rel:
            return round(1.0 / rank, 4)
    return 0.0


def _ci(deltas: list[float]) -> dict:
    """Normal-approximation CI on a paired mean — stated, not assumed to be exact at these n."""
    n = len(deltas)
    if n < 2:
        return {"n": n, "mean": statistics.mean(deltas) if deltas else None, "sd": None, "ci95": None}
    m = statistics.mean(deltas)
    sd = statistics.stdev(deltas)
    half = 1.96 * sd / math.sqrt(n)
    return {"n": n, "mean": m, "sd": sd, "ci95": [m - half, m + half]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(BASE / "t4_endpoint.json"))
    args = ap.parse_args()

    cfg = get_settings()
    if not cfg.da_enabled:
        logger.error("G-lane: da_enabled is False — this run needs T0's lane set (DA ON)")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    _install_rerank_wrapper(reranker)

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

    # One store + one cfg per arm, built ONCE (a DocumentStore opens a Qdrant client and a SQLite engine).
    ARM_CFGS = {a: cfg.model_copy(update={"reranker_enabled": o["reranker_enabled"],
                                          "reranker_top_k": o["reranker_top_k"]})
                for a, o in ARMS.items()}
    ARM_STORES = {a: DocumentStore(c) for a, c in ARM_CFGS.items()}

    per_query: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()
    try:
        for i, q in enumerate(queries, 1):
            qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
            rel = {int(p) for p in q["relevant_pages"]}
            rq = rel & reach
            rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel), "n_reachable": len(rq),
                         "relevant_pages": sorted(rel)}
            try:
                for arm, spec in ARMS.items():
                    cfg_arm, store_arm = ARM_CFGS[arm], ARM_STORES[arm]
                    # ⚠️ set the override BEFORE the call: arm Q reranks against the raw query
                    _RERANK_OVERRIDE["text"] = text if spec["rerank_query"] == "raw" else None
                    ret = _retry(run_retrieval, text, store_arm, embedder, reranker, cfg_arm,
                                 "global", 0.0, query_type=qtype)
                    pages = _pages_of(ret["reranked"])          # the ENDPOINT list (top-k), page-deduped
                    pool_pages = _pages_of(ret["hits"])          # the POOL (unchanged by the CE)
                    rec[f"{arm}_pages"] = pages
                    rec[f"{arm}_pool_size"] = len(pool_pages)
                    # ⚠️ G6b — a hash of the pool's PAGE LIST, so the guard can compare pool CONTENT and
                    # not merely its length (independent review, item 3). Compact: 16 hex chars per arm.
                    rec[f"{arm}_pool_sha"] = hashlib.sha256(
                        ",".join(map(str, pool_pages)).encode()).hexdigest()[:16]
                    rec[f"{arm}_cov"] = _cov(pages, rq)
                    # ⚠️ §12 — the product's `mrr` is a POOL metric; inject the ENDPOINT MRR explicitly
                    m = compute_retrieval_metrics(ret, sorted(rel), cfg_arm)
                    m[f"mrr_at_{cfg_arm.reranker_top_k}"] = _endpoint_mrr(pages, rel)
                    rec[f"{arm}_metrics"] = m
                    if arm == "C":
                        # determinism (G4) — arm C run a SECOND time
                        _RERANK_OVERRIDE["text"] = None
                        ret2 = _retry(run_retrieval, text, store_arm, embedder, reranker, cfg_arm,
                                      "global", 0.0, query_type=qtype)
                        rec["C2_pages"] = _pages_of(ret2["reranked"])
                        m2 = compute_retrieval_metrics(ret2, sorted(rel), cfg_arm)
                        m2[f"mrr_at_{cfg_arm.reranker_top_k}"] = _endpoint_mrr(rec["C2_pages"], rel)
                        rec["C2_metrics"] = m2
                _RERANK_OVERRIDE["text"] = None
                per_query.append(rec)
            except Exception as exc:  # noqa: BLE001
                _RERANK_OVERRIDE["text"] = None
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
        out: dict = {"n": len(rows)}
        k = ARM_CFGS[arm].reranker_top_k
        covs = [r[f"{arm}_cov"] for r in rows if r.get(f"{arm}_cov") is not None]
        out["coverage_reachable"] = statistics.mean(covs) if covs else None
        out["pool_mean"] = statistics.mean([r[f"{arm}_pool_size"] for r in rows]) if rows else None
        for key in _mkeys(k) + (f"recall_at_{ARM_CFGS[arm].reranker_fetch_k}",):
            vals = [r[f"{arm}_metrics"][key] for r in rows
                    if r.get(f"{arm}_metrics") and r[f"{arm}_metrics"].get(key) is not None]
            out[key] = statistics.mean(vals) if vals else None
        return out

    aggregate = {arm: {"overall": agg(arm),
                       "by_type": {qt: agg(arm, [r for r in ok if r["query_type"] == qt])
                                   for qt in ("factual", "multihop", "overview")}}
                 for arm in ARMS}

    # ── paired deltas (the predictions) ───────────────────────────────────────────────────────────
    def delta(a_arm: str, b_arm: str, key: str) -> dict:
        d = [(r[f"{b_arm}_metrics"][key] - r[f"{a_arm}_metrics"][key])
             for r in ok if r.get(f"{a_arm}_metrics") and r.get(f"{b_arm}_metrics")
             and r[f"{a_arm}_metrics"].get(key) is not None and r[f"{b_arm}_metrics"].get(key) is not None]
        return _ci(d)

    # ⚠️ §12 — endpoint metrics only. The product's `mrr` is a POOL metric and is deliberately NOT here;
    # `mrr_at_20` is the endpoint MRR, and it is the one T0's `ce` row reports.
    P_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20")
    deltas = {
        "P1_N_minus_C":  {k: delta("C", "N", k) for k in P_KEYS},
        "P2_Q_minus_C":  {k: delta("C", "Q", k) for k in P_KEYS},
        "P3_W50_cov_minus_C_cov": _ci([(r["W50_cov"] - r["C_cov"]) for r in ok
                                       if r.get("W50_cov") is not None and r.get("C_cov") is not None]),
    }

    # ── guards ────────────────────────────────────────────────────────────────────────────────────
    t0_art = json.loads(Path(T0_ARTIFACT).read_text())
    t0_ce, t0_fus = t0_art["aggregate"]["ce"]["overall"], t0_art["aggregate"]["fusion"]["overall"]
    t0_pages = {int(p) for p in t0_art["meta"]["coll_pages"]}

    def near(a, b, tol=ANCHOR_TOL):
        return a is not None and b is not None and abs(a - b) <= tol

    g1_detail = {k: {"got": aggregate["C"]["overall"].get(k), "want": t0_ce.get(k)}
                 for k in G1_KEYS}
    g2_detail = {k: {"got": aggregate["N"]["overall"].get(k), "want": t0_fus.get(k)}
                 for k in G2_KEYS}
    g1_ok = all(near(v["got"], v["want"]) for v in g1_detail.values())
    g2_ok = all(near(v["got"], v["want"]) for v in g2_detail.values())

    c_vs_c2 = [r["id"] for r in ok if r.get("C2_pages") != r.get("C_pages")]
    # ⚠️ G4b — the pre-registration says "bit-exact on every METRIC of every query", so compare the metric
    # dicts too, not just the page lists (independent review, item 2). Page equality implies metric
    # equality only if the metric function is deterministic — which is the thing being asserted.
    c2_metric_mismatch = [r["id"] for r in ok if r.get("C2_metrics") != r.get("C_metrics")]
    q_vs_c = [r["id"] for r in ok if r.get("Q_pages") != r.get("C_pages")]
    pool_size_mismatch = {a: [r["id"] for r in ok if r[f"{a}_pool_size"] != r["C_pool_size"]] for a in ARMS}
    # ⚠️ G6b — pool CONTENT, not merely its length: two arms could return different pools of equal size.
    pool_sha_mismatch = {a: [r["id"] for r in ok if r[f"{a}_pool_sha"] != r["C_pool_sha"]] for a in ("N", "Q")}
    reach_identical = (reach == t0_pages)
    fetch_ks = {a: ARM_CFGS[a].reranker_fetch_k for a in ARMS}

    guards = {
        "G1_C_reproduces_T0_ce_row": g1_ok,
        "G2_N_reproduces_T0_fusion_row": g2_ok,
        "G3_133_scored_0_errors": (len(ok) == len(queries) and not errors),
        "G4_arm_C_bit_exact_on_repeat": not c_vs_c2,
        "G4b_arm_C_METRICS_bit_exact_on_repeat": not c2_metric_mismatch,
        "G5_arm_Q_instrumentation_took_effect": bool(q_vs_c),
        "G5b_Q_override_fired_on_every_Q_call": _OVERRIDE_HITS["n"] == len(ok),
        "G6_pools_identical_across_C_N_Q": all(not pool_size_mismatch[a] for a in ("N", "Q")),
        "G6b_pool_CONTENT_identical_across_C_N_Q": all(not pool_sha_mismatch[a] for a in ("N", "Q")),
        "G7_reachable_set_matches_T0": reach_identical,
        "G8_fetch_k_is_100_in_every_arm": all(v == 100 for v in fetch_ks.values()),
    }

    artifact = {
        "meta": {
            "question": "is the pool -> top-20 loss the cross-encoder, the 20-slot cut, or the CE's query text?",
            "prereg": ".hermes/plans/2026-10-27-p1-endpoint-attribution-preregistration.md",
            "collection": cfg.qdrant_collection, "dense_model": cfg.dense_model,
            "dense_dim": cfg.dense_dim, "qdrant_host": cfg.qdrant_host,
            "da_enabled": bool(cfg.da_enabled), "graph_lane": "ON",
            "hyde": "ON and frozen", "hyde_cache": cache.path.name,
            "arms": ARMS,
            "anchors": {"tol": ANCHOR_TOL, "G1_arm": "C vs T0 aggregate.ce.overall (R@100 excluded, §11)",
                        "G2_arm": "N vs T0 aggregate.fusion.overall"},
            "reachable_pages": len(reach),
            "reachable_pages_set_sha": hashlib.sha256(",".join(str(p) for p in sorted(reach)).encode()).hexdigest()[:16],
            "t0_reachable_pages_set_sha": hashlib.sha256(",".join(str(p) for p in sorted(t0_pages)).encode()).hexdigest()[:16],
            "n_queries": len(queries), "n_errors": len(errors), "wall_seconds": round(wall, 1),
            "unit": "coverage of a query's REACHABLE labelled pages (T0's §I66 unit)",
            "note_ndcg_scale": "nDCG's IDCG uses min(n, reranker_top_k), so nDCG_at_50 is NOT comparable to nDCG_at_20; coverage and R@k-with-ceiling are the cut's honest comparisons",
            "fetch_k": fetch_ks,
            "override_hits": _OVERRIDE_HITS["n"],
            # ⚠️ Which of these fields describe the ENDPOINT and which describe the POOL (independent
            # review, item 6). Without this a reader takes `mrr` for the endpoint's — see §I95.
            "field_conventions": {
                "ENDPOINT": ["recall_at_k", "precision_at_k", "precision_ceiling_at_k", "f1_at_k",
                             "ndcg_at_k", "hit_at_k", "mrr_at_k", "map", "coverage_reachable"],
                "POOL": ["mrr", "recall_at_100"],
                "warning": "`mrr` is MRR@fetch_k over the POOL (the product's own field); the ENDPOINT MRR "
                           "is `mrr_at_k`. On T0's rows they are 0.7687 and 0.6668 — a ~0.10 gap. §I95.",
            },
        },
        "aggregate": aggregate,
        "deltas": deltas,
        "guards": guards,
        "guard_detail": {"G1": g1_detail, "G2": g2_detail,
                         "C_vs_C2_page_mismatch_ids": c_vs_c2,
                         "C_vs_C2_metric_mismatch_ids": c2_metric_mismatch,
                         "Q_vs_C_page_mismatch_ids": q_vs_c,
                         "pool_size_mismatch_ids": pool_size_mismatch,
                         "pool_sha_mismatch_ids": pool_sha_mismatch},
        "errors": errors,
        "per_query": per_query,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()

    print(json.dumps({"aggregate": {a: aggregate[a]["overall"] for a in ARMS},
                      "deltas": deltas, "guards": guards}, indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
