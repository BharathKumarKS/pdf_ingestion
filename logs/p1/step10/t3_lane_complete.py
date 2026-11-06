"""T3 — the LANE-COMPLETE v2-vs-v3 A/B: the full-funnel ship test.

Pre-registration: `.hermes/plans/2026-11-02-p1-t3-lane-complete-preregistration.md` (committed ALONE
per D6.1). This file implements §3/§4/§5/§7 of that document and nothing else.

WHAT MAKES THIS THE PRODUCT PATH (inherited verbatim from `stageF_product_endpoint.py`). Each arm
calls the PRODUCT's own `evaluate_rag.run_retrieval` — `embed_query` -> (HyDE) ->
`store.search_with_das` -> the graph lane for multihop -> the shipped cluster cross-encoder — and
scores with the PRODUCT's own `evaluate_rag.compute_retrieval_metrics`. The ONE substitution is HyDE:
`run_retrieval` calls `src.core.llm.call_llm` directly (temperature 0.3), so every arm would embed a
different hypothetical for the same query. §4 mandates HyDE be ON and FROZEN, so `call_llm` is
monkeypatched to return the cached hypothetical for the query's own prompt. A cache miss RAISES.

THE TWO AXES. `--lanes off` = base lanes only (DA and graph monkeypatched OFF) — this reproduces
§I85 and is the INSTRUMENT ANCHOR (G8). `--lanes on` = every lane ON (DA enabled, graph lane live) —
the treatment. §A (the per-space query-vector fix, §I104) makes arm A's derived lanes reachable, so
both arms are now lane-complete.

PER-ARM PROCESS. `get_settings` / `get_cluster_embedder` / `get_reranker` are process-global
singletons and the arm's embedder/dim/collection come from the ENVIRONMENT. So each arm runs in its
OWN process, launched by `run_t3.sh`. `--arm A|B --lanes off|on --rep N` writes one per-arm JSON;
`--combine` reads them and writes the run artifact.

READ-ONLY: no writes to any collection, no re-ingest, no `src/` change. The only LLM traffic is the
shared cluster embedder + cross-encoder (HyDE is served from the cache).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from loguru import logger

from src.core.config import get_settings
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
from src.pdf_ingestion.hyde_cache import load as load_hyde, prompt_for
from src.pdf_ingestion.reranker import get_reranker
from src.pdf_ingestion.store import DocumentStore

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from evaluate_rag import compute_retrieval_metrics, run_retrieval  # noqa: E402

TOP_K = 20
FETCH_K = 100
QUERIES = "data/eval_queries_v2.json"

# §3 — the per-arm config each arm MUST resolve to. `doc_prefix`/`instr` are asserted, not assumed.
EXPECT = {
    "A": dict(collection="knowledge_base_v2", model="Qwen/Qwen3-Embedding-0.6B", dim=1024,
              dim_low=64, doc_prefix="", instr_kind="qwen3", role="control / incumbent"),
    "B": dict(collection="knowledge_base_v3", model="nomic-ai/nomic-embed-text-v1.5", dim=768,
              dim_low=64, doc_prefix="search_document: ", instr_kind="nomic", role="treatment"),
}

# §I85's recorded arm aggregates — the G8 anchor. ⚠️ ONLY the six keys §I85's artifact actually
# carries are compared (precision_at_20 / precision_ceiling_at_20 / map / f1_at_20 were added to
# `compute_retrieval_metrics` on 2026-10-27, AFTER §I85 ran — a whole-record equality would fail on
# correct data).
I85 = {
    "A": {"recall_at_20": 0.4474954887218045, "recall_at_100": 0.6468984962406015,
          "hit_at_20": 0.9172932330827067, "mrr": 0.7515187969924813,
          "ndcg_at_20": 0.5017593984962406, "context_precision": None},
    "B": {"recall_at_20": 0.4463105263157895, "recall_at_100": 0.6114954887218045,
          "hit_at_20": 0.924812030075188, "mrr": 0.7273360902255639,
          "ndcg_at_20": 0.4980225563909774, "context_precision": None},
}
ANCHOR_KEYS = ("recall_at_20", "recall_at_100", "hit_at_20", "mrr", "ndcg_at_20")
ANCHOR_TOL = 0.020   # the n=133 resolution floor (§0's doctrine), NOT a fit

# Per-query lane-liveness counters, set by the wrappers and read right after `run_retrieval`.
_LANE: dict = {"da_hits": None, "graph_hits": None}


def _load_queries() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _reachable_pages(store, cfg) -> set[int]:
    """Pages a retriever can EVER reach under the live content filter (§I58's achievable max)."""
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


def _full_precision(retrieval: dict, rel_pages: list[int]) -> dict:
    """R@20 / R@100 at FULL precision (the product metric rounds each query to 4dp)."""
    rel = set(rel_pages)
    seen: set[int] = set()
    n20 = 0
    for h in retrieval["reranked"]:
        p = h.get("page_number")
        if p in rel and p not in seen:
            n20 += 1
            seen.add(p)
    pages_above = {h.get("page_number") for h in retrieval["hits_above"] if h.get("page_number")}
    return {
        "r20_full": n20 / len(rel) if rel else None,
        "r100_full": len(rel & pages_above) / len(rel) if rel else None,
    }


def _install_lane_counters(store, lanes: str):
    """Wrap the DA lane (and, when ON, the graph lane) so each query's lane-hit count is recorded.

    `run_retrieval`'s returned dict exposes only hits/hits_above/reranked/reranker_fallback, so G5/G6
    (arm A's derived lanes are LIVE) have nothing to assert on unless the harness counts them itself.
    The wrapper increments and calls through — it changes no behaviour.
    """
    import src.pdf_ingestion.graph_builder as gb_mod

    # DA lane: `search_with_das` calls `self.search_da(...)`, so wrap the INSTANCE attribute.
    _real_da = store.search_da

    def _counted_da(*a, **kw):
        hits = _real_da(*a, **kw)
        _LANE["da_hits"] = len(hits)
        return hits

    store.search_da = _counted_da

    _real_get_graph = gb_mod.get_graph_builder

    if lanes == "off":
        class _NoGraphLane:
            def graph_search(self, *a, **kw):
                _LANE["graph_hits"] = 0
                return []

        gb_mod.get_graph_builder = lambda settings=None: _NoGraphLane()

        def _restore():
            gb_mod.get_graph_builder = _real_get_graph
    else:
        def _counting_get(settings=None):
            real = _real_get_graph(settings)

            class _CountingGraphLane:
                def graph_search(self, *a, **kw):
                    hits = real.graph_search(*a, **kw)
                    _LANE["graph_hits"] = len(hits)
                    return hits

            return _CountingGraphLane()

        gb_mod.get_graph_builder = _counting_get

        def _restore():
            gb_mod.get_graph_builder = _real_get_graph

    return _restore


def run_arm(arm: str, lanes: str, rep: int, out: Path, limit: int = 0) -> int:
    exp = EXPECT[arm]
    cfg = get_settings()

    # ── E1/E2 — the resolved config is asserted, not assumed (forget the exports and the run
    #    silently uses Qwen3/1024 against the wrong collection). ────────────────────────────────
    problems = []
    if not cfg.qdrant_host:
        problems.append(f"QDRANT_HOST is blank (resolved local store at {cfg.qdrant_local_path})")
    if cfg.qdrant_collection != exp["collection"]:
        problems.append(f"collection {cfg.qdrant_collection!r} != {exp['collection']!r}")
    if cfg.dense_model != exp["model"]:
        problems.append(f"dense_model {cfg.dense_model!r} != {exp['model']!r}")
    if cfg.dense_dim != exp["dim"]:
        problems.append(f"dense_dim {cfg.dense_dim} != {exp['dim']}")
    if cfg.dense_dim_low != exp["dim_low"]:
        problems.append(f"dense_dim_low {cfg.dense_dim_low} != {exp['dim_low']}")
    if cfg.document_prefix != exp["doc_prefix"]:
        problems.append(f"document_prefix {cfg.document_prefix!r} != {exp['doc_prefix']!r}")
    instr = cfg.query_instruction or ""
    if exp["instr_kind"] == "nomic" and instr != "search_query: ":
        problems.append(f"query_instruction {instr!r} != 'search_query: ' (nomic)")
    if exp["instr_kind"] == "qwen3" and "Instruct:" not in instr:
        problems.append(f"query_instruction {instr!r} is not Qwen3's instruction")
    if cfg.reranker_top_k != TOP_K or cfg.reranker_fetch_k != FETCH_K:
        problems.append(f"top_k/fetch_k {cfg.reranker_top_k}/{cfg.reranker_fetch_k} != {TOP_K}/{FETCH_K}")
    # The lanes axis is asserted, not assumed: `on` requires DA enabled; `off` requires it disabled.
    if lanes == "on" and not cfg.da_enabled:
        problems.append("lanes=on requires DA_ENABLED=true (the DA lane is off)")
    if lanes == "off" and cfg.da_enabled:
        problems.append("lanes=off requires DA_ENABLED=false (the DA lane is on)")
    if problems:
        for p in problems:
            logger.error("E1/E2 FAIL: {}", p)
        print(json.dumps({"arm": arm, "lanes": lanes, "e1_e2_ok": False, "problems": problems}, indent=2))
        return 2

    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)

    # ── §4 — HyDE ON and FROZEN. Patch the product's call_llm to serve the cache by prompt text. ──
    queries = _load_queries()
    if limit:
        queries = queries[:limit]
    cache = load_hyde(Path(QUERIES), cfg=cfg)
    prompt_map: dict[str, str] = {}
    n_hyde_used = 0
    for q in queries:
        if q.get("query_type") in ("factual", "overview"):
            hyp = cache.get(q["id"])          # raises HydeCacheMiss — never a live call (§4)
            prompt_map[prompt_for(q["query"])] = hyp
            n_hyde_used += 1

    import src.core.llm as llm_mod
    _real_call_llm = llm_mod.call_llm

    def _frozen_llm(prompt=None, system=None, settings=None, **kw):
        if prompt in prompt_map:
            return prompt_map[prompt]
        raise RuntimeError(
            f"HyDE cache miss mid-run for prompt {str(prompt)[:90]!r} — refusing a live LLM call (§4)"
        )

    llm_mod.call_llm = _frozen_llm

    # ── the lanes axis: wrap DA + graph so liveness is COUNTED (G5/G6). ──────────────────────────
    _restore_lanes = _install_lane_counters(store, lanes)

    logger.info(
        "ARM {} lanes={} rep {} — collection={} host={} model={} dim={} low={} doc_prefix={!r} "
        "instr={!r} da_enabled={} hyde_entries_used={} queries={}",
        arm, lanes, rep, cfg.qdrant_collection, cfg.qdrant_host, cfg.dense_model, cfg.dense_dim,
        cfg.dense_dim_low, cfg.document_prefix, instr[:30], cfg.da_enabled, n_hyde_used, len(queries),
    )

    reachable = _reachable_pages(store, cfg)
    logger.info("reachable content pages: {}", len(reachable))

    per_query: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        qid, text = q["id"], q["query"]
        rel = list(q["relevant_pages"])
        qtype = q.get("query_type", "factual")
        rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel)}
        _LANE["da_hits"] = None
        _LANE["graph_hits"] = None
        try:
            retrieval = run_retrieval(
                text, store, embedder, reranker, cfg, "global", 0.0, query_type=qtype,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
            logger.error("[{}] retrieval FAILED: {}", qid, exc)
            per_query.append({**rec, "error": str(exc)})
            continue
        m = compute_retrieval_metrics(retrieval, rel, cfg)
        fp = _full_precision(retrieval, rel)
        reach_q = len(set(rel) & reachable)
        rec.update({
            "metrics": m,
            "r20_full": fp["r20_full"],
            "r100_full": fp["r100_full"],
            "achievable_max": reach_q / len(rel) if rel else None,
            "pool_size": len(retrieval["hits"]),
            "reranked_size": len(retrieval["reranked"]),
            "reranker_fallback": bool(retrieval.get("reranker_fallback", False)),
            "n_relevant_reachable": reach_q,
            "da_hits": _LANE["da_hits"],
            "graph_hits": _LANE["graph_hits"],
        })
        per_query.append(rec)
        if i % 20 == 0:
            logger.info("  {}/{} queries", i, len(queries))
    wall = time.time() - t0

    llm_mod.call_llm = _real_call_llm  # restore
    _restore_lanes()

    artifact = {
        "meta": {
            "arm": arm, "lanes": lanes, "rep": rep, "role": exp["role"],
            "collection": cfg.qdrant_collection, "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model, "dense_dim": cfg.dense_dim,
            "dense_dim_low": cfg.dense_dim_low, "document_prefix": cfg.document_prefix,
            "query_instruction": instr,
            "splade": cfg.splade_enabled, "colbert": cfg.colbert_enabled,
            "da_enabled": cfg.da_enabled, "mmr_enabled": cfg.mmr_enabled,
            "mmr_candidates": cfg.mmr_candidates, "reranker_fetch_k": cfg.reranker_fetch_k,
            "reranker_top_k": cfg.reranker_top_k, "reranker_model": cfg.reranker_model,
            "dense_prefetch_limit": cfg.dense_prefetch_limit,
            "dense_rescore_limit": cfg.dense_rescore_limit,
            "hyde": cfg.hyde_enabled, "hyde_cache": cache.path.name,
            "n_hyde_used": n_hyde_used, "n_queries": len(queries),
            "n_errors": len(errors), "wall_seconds": round(wall, 1),
            "reachable_pages": len(reachable), "reachable_pages_set_sha": hashlib.sha256(
                ",".join(str(p) for p in sorted(reachable)).encode()).hexdigest()[:16],
        },
        "guards": {
            "E1_host_and_collection_resolved": True,   # we returned 2 above otherwise
            "E2_arm_config_matches": True,
            "E3_all_queries_scored": (len(per_query) == len(queries) and len(errors) == 0),
        },
        "errors": errors,
        "per_query": per_query,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    logger.info("arm {} lanes={} rep {} -> {} ({}s) sha256 {}", arm, lanes, rep, out,
                round(wall, 1), sha[:16])
    print(f"ARM {arm} lanes={lanes} rep {rep}: {len(per_query)} queries, {len(errors)} errors, "
          f"{round(wall,1)}s -> {out}")
    return 0


# ── combine ──────────────────────────────────────────────────────────────────────────────────────

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def _ci(diffs):
    n = len(diffs)
    if n < 2:
        return [float("nan"), float("nan")]
    half = 1.96 * statistics.stdev(diffs) / (n ** 0.5)
    m = statistics.mean(diffs)
    return [m - half, m + half]


def _paired(a: dict, b: dict, key) -> dict:
    diffs, ids = [], []
    for qid in sorted(set(a) & set(b)):
        va, vb = key(a[qid]), key(b[qid])
        if va is None or vb is None:
            continue
        diffs.append(vb - va)
        ids.append(qid)
    lo, hi = _ci(diffs)
    return {
        "n": len(diffs), "mean_delta": _mean(diffs), "ci": [lo, hi],
        "resolved": (lo > 0 or hi < 0) if len(diffs) > 1 else False,
        "wins": sum(1 for d in diffs if d > 0), "losses": sum(1 for d in diffs if d < 0),
        "ties": sum(1 for d in diffs if d == 0),
        "sd": statistics.stdev(diffs) if len(diffs) > 1 else None,
        "per_query": diffs, "ids": ids,
    }


def _rows(arm_obj: dict) -> dict:
    return {r["id"]: r for r in arm_obj["per_query"] if "error" not in r}


def combine(paths: dict[str, Path], out: Path) -> int:
    arms = {k: json.loads(p.read_text()) for k, p in paths.items()}
    a_off, b_off = _rows(arms["A_off_r1"]), _rows(arms["B_off_r1"])
    a_on, b_on = _rows(arms["A_on_r1"]), _rows(arms["B_on_r1"])
    a_on2, b_on2 = _rows(arms["A_on_r2"]), _rows(arms["B_on_r2"])

    r20 = lambda r: r["metrics"].get("recall_at_20")             # noqa: E731
    r100 = lambda r: r["metrics"].get("recall_at_100")           # noqa: E731
    hit = lambda r: r["metrics"].get("hit_at_20")                # noqa: E731
    mrr = lambda r: r["metrics"].get("mrr")                      # noqa: E731
    cp = lambda r: r["metrics"].get("context_precision")         # noqa: E731
    ndcg = lambda r: r["metrics"].get("ndcg_at_20")              # noqa: E731
    prec = lambda r: r["metrics"].get("precision_at_20")         # noqa: E731
    pceil = lambda r: r["metrics"].get("precision_ceiling_at_20")  # noqa: E731
    mp = lambda r: r["metrics"].get("map")                       # noqa: E731

    # §I58 ceiling-normalised: cR@k = mean(R@k) / mean(achievable_max). The divisor is a property of
    # the CORPUS (identical across arms by construction — v3 is v2's chunks re-embedded) — asserted.
    D = {k: _mean([r["achievable_max"] for r in d.values()])
         for k, d in (("A_off", a_off), ("B_off", b_off), ("A_on", a_on), ("B_on", b_on))}
    D_A = D["A_on"]

    P1 = _paired(a_on, b_on, lambda r: (r20(r) / D_A) if r20(r) is not None else None)   # cR@20
    P2 = _paired(a_on, b_on, r20)                                                         # raw R@20

    per_type = {}
    for qt in ("factual", "multihop", "overview"):
        aa = {k: v for k, v in a_on.items() if v["query_type"] == qt}
        bb = {k: v for k, v in b_on.items() if v["query_type"] == qt}
        per_type[qt] = {"n": len(aa), "cr20": _paired(aa, bb,
                        lambda r: (r20(r) / D_A) if r20(r) is not None else None)}

    # lane deltas — the derived layer's contribution, per arm (on − off)
    lane_delta = {
        "A_on_minus_A_off_cR20": _paired(a_off, a_on, lambda r: (r20(r) / D_A) if r20(r) is not None else None),
        "B_on_minus_B_off_cR20": _paired(b_off, b_on, lambda r: (r20(r) / D_A) if r20(r) is not None else None),
    }

    # ── guards ───────────────────────────────────────────────────────────────────────────────────
    def _bit_exact(x, y):
        return [qid for qid in sorted(set(x) & set(y)) if x[qid]["metrics"] != y[qid]["metrics"]]

    det = {"A_on_r1_vs_r2": _bit_exact(a_on, a_on2), "B_on_r1_vs_r2": _bit_exact(b_on, b_on2)}

    def _agg(d):
        return {"recall_at_20": _mean([r20(r) for r in d.values()]),
                "recall_at_100": _mean([r100(r) for r in d.values()]),
                "hit_at_20": _mean([hit(r) for r in d.values()]),
                "mrr": _mean([mrr(r) for r in d.values()]),
                "ndcg_at_20": _mean([ndcg(r) for r in d.values()])}

    a_off_agg, b_off_agg = _agg(a_off), _agg(b_off)
    anchor = {}
    for arm, agg in (("A", a_off_agg), ("B", b_off_agg)):
        anchor[arm] = {k: agg[k] - I85[arm][k] for k in ANCHOR_KEYS}
    anchor_ok = {arm: all(abs(v) <= ANCHOR_TOL for v in gaps.values()) for arm, gaps in anchor.items()}

    def _lane_live(d, key):
        return sum(1 for r in d.values() if (r.get(key) or 0) > 0)

    liveness = {
        "A_on_da_live_queries": _lane_live(a_on, "da_hits"),
        "B_on_da_live_queries": _lane_live(b_on, "da_hits"),
        "A_on_graph_live_queries": _lane_live(a_on, "graph_hits"),
        "B_on_graph_live_queries": _lane_live(b_on, "graph_hits"),
        "A_off_da_live_queries": _lane_live(a_off, "da_hits"),
    }

    pools_on_A = [r["pool_size"] for r in a_on.values()]
    pools_on_B = [r["pool_size"] for r in b_on.values()]
    fb_A = sorted(q for q, r in a_on.items() if r["reranker_fallback"])
    fb_B = sorted(q for q, r in b_on.items() if r["reranker_fallback"])

    guards = {
        "G1_population_133": all(len(d) == 133 for d in (a_off, b_off, a_on, b_on, a_on2, b_on2)),
        "G1b_per_type_53_40_40": (
            sum(1 for r in a_on.values() if r["query_type"] == "factual") == 53
            and sum(1 for r in a_on.values() if r["query_type"] == "overview") == 40
            and sum(1 for r in a_on.values() if r["query_type"] == "multihop") == 40),
        "G2_reachable_pages_888": all(
            arms[k]["meta"]["reachable_pages"] == 888 for k in arms),
        "G3_zero_errors": all(arms[k]["meta"]["n_errors"] == 0 for k in arms),
        "G4_zero_reranker_fallbacks": (len(fb_A) == 0 and len(fb_B) == 0),
        "G5_armA_DA_lane_live": liveness["A_on_da_live_queries"] > 0,
        "G6_armA_graph_lane_live": liveness["A_on_graph_live_queries"] > 0,
        "G7_hyde_frozen": all(arms[k]["meta"]["n_hyde_used"] == 93 for k in arms),
        "G8_off_arms_reproduce_I85": (anchor_ok["A"] and anchor_ok["B"]),
        "G10_on_arms_deterministic": (len(det["A_on_r1_vs_r2"]) == 0 and len(det["B_on_r1_vs_r2"]) == 0),
        "G_divisor_identical_across_arms": (
            len([v for v in D.values() if v is not None]) == len(D)
            and (max(v for v in D.values() if v is not None)
                 - min(v for v in D.values() if v is not None)) < 1e-9),
    }

    artifact = {
        "meta": {
            "question": "lane-complete v2-vs-v3 at the product endpoint (full funnel), 133 queries",
            "prereg": ".hermes/plans/2026-11-02-p1-t3-lane-complete-preregistration.md",
            "lanes_on": "DA enabled + graph lane live (the product's real wiring, lanes=None)",
            "lanes_off": "DA + graph OFF — reproduces §I85 (the instrument anchor, G8)",
            "hyde": "ON and frozen (data/hyde_cache)",
            "page_convention": "pages of the top-k CHUNKS (evaluate_rag.py:333-341) — NOT top-k PAGES",
            "ceiling_convention": "§I58: cR@k = mean(R@k) / mean(achievable_max); global divisor",
            "arms": {k: arms[k]["meta"] for k in arms},
            "divisor_achievable_max": D,
            "I85_anchor_target": I85,
            "I85_anchor_keys_compared": list(ANCHOR_KEYS),
            "I85_anchor_tolerance": ANCHOR_TOL,
            "wall_seconds": {k: arms[k]["meta"]["wall_seconds"] for k in arms},
        },
        "endpoints": {
            "P1_cR20": P1, "P2_R20_raw": P2,
            "S1_secondary": {
                "R100": _paired(a_on, b_on, r100), "Hit20": _paired(a_on, b_on, hit),
                "MRR": _paired(a_on, b_on, mrr), "CtxPrec": _paired(a_on, b_on, cp),
                "NDCG20": _paired(a_on, b_on, ndcg), "MAP": _paired(a_on, b_on, mp),
                "Precision20": _paired(a_on, b_on, prec),
                "PrecisionCeil20": _paired(a_on, b_on, pceil),
            },
            "S2_by_type_cR20": per_type,
            "S3_lane_deltas": lane_delta,
        },
        "guards": guards,
        "diagnostics": {
            "liveness": liveness,
            "determinism_mismatch_ids": det,
            "anchor_gaps_off_minus_I85": anchor,
            "anchor_ok": anchor_ok,
            "aggregates_off": {"A": a_off_agg, "B": b_off_agg},
            "aggregates_on": {"A": _agg(a_on), "B": _agg(b_on)},
            "fallback_ids_A_on": fb_A, "fallback_ids_B_on": fb_B,
            "pool_min_max_A_on": [min(pools_on_A), max(pools_on_A)],
            "pool_min_max_B_on": [min(pools_on_B), max(pools_on_B)],
        },
        "power": {
            "n": P1["n"], "sd_d_cR20": P1["sd"], "sd_d_R20": P2["sd"],
            "resolution_floor_cR20": (1.96 * P1["sd"] / (P1["n"] ** 0.5)) if P1["sd"] else None,
            "n_required_for_delta_0.05_cR20": ((1.96 * P1["sd"] / 0.05) ** 2) if P1["sd"] else None,
        },
        "verdict": {
            "ships": bool(P1["resolved"] and (P1["mean_delta"] or 0) > 0),
            "P1_resolved": P1["resolved"], "P1_positive": (P1["mean_delta"] or 0) > 0,
            "reading": ("RESOLVED POSITIVE — v3 ships" if (P1["resolved"] and (P1["mean_delta"] or 0) > 0)
                        else "RESOLVED NEGATIVE — nothing ships" if P1["resolved"]
                        else "MEASURED-AND-UNRESOLVED — nothing ships on this evidence"),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()

    print(json.dumps({k: artifact[k] for k in ("endpoints", "guards", "power", "verdict", "diagnostics")},
                     indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["A", "B"])
    ap.add_argument("--lanes", choices=["off", "on"])
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--combine", action="store_true")
    args = ap.parse_args()

    base = Path("logs/p1/step10")
    if args.combine:
        return combine({
            "A_off_r1": base / "t3_arm_A_off_r1.json", "B_off_r1": base / "t3_arm_B_off_r1.json",
            "A_on_r1": base / "t3_arm_A_on_r1.json", "A_on_r2": base / "t3_arm_A_on_r2.json",
            "B_on_r1": base / "t3_arm_B_on_r1.json", "B_on_r2": base / "t3_arm_B_on_r2.json",
        }, base / "t3_lane_complete.json")
    if not args.arm or not args.lanes:
        ap.error("--arm and --lanes required (or --combine)")
    out = Path(args.out) if args.out else base / f"t3_arm_{args.arm}_{args.lanes}_r{args.rep}.json"
    return run_arm(args.arm, args.lanes, args.rep, out, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
