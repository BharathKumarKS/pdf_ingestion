"""Lane plan S5 — LANE INCLUSION: does making a lane a first-class RRF participant change its sign?

Pre-registration: `.hermes/plans/2026-10-29-p1-lane-inclusion-preregistration.md` (§1-§11, committed
ALONE before this run per D6.1). Implements §2/§4/§5 as AMENDED by §11, and nothing else.

THE QUESTION. Three lanes are wired so they cannot displace a fused hit (plan §0): the DA lane is
appended AFTER the vector fusion; the graph lane is appended by the caller after dedup/MMR with a
fabricated `score` that passes any threshold; RAPTOR was absent from the index AND never called on
the eval path. Measured today: DA is a HARM (−0.0262, §I56); the graph lane lowers MRR 0.781 → 0.667;
overview is the worst type (R@20 0.1882 against its ceiling 0.3992).

⚠️ The registered question is NOT "does this improve things" — it is *"does making a lane a
first-class RRF participant change its sign and ordering, versus appending it?"* For DA and graph a
null, or a continued harm, is a real and recordable outcome.

THE ARMS (§2 + §11c). `run_retrieval(lanes=…)` replaces the pool's composition:
  F0  — TODAY'S WIRING (`lanes=None`): DA appended post-fusion, graph appended post-MMR, no RAPTOR.
        The product reference; anchored (§4 G2).
  F0f — `search_fused(lanes=())`: the vector lanes only, fused. **The control every treatment arm is
        compared against**, because the arms REPLACE the composition rather than add to it (§11c).
  F1  — `lanes=("da",)`     → isolates the DA lane's PLACEMENT      (F1 − F0f)
  F2  — `lanes=("graph",)`  → isolates the graph lane's PLACEMENT   (F2 − F0f)
  F3  — `lanes=("raptor",)` → isolates the RAPTOR lane              (F3 − F0f)
  F4  — all three fused + the DA lane; EXPLORATORY, ships nothing.

⚠️ §11b — a RAPTOR summary carries NO `page_number`, so at the page-level unit the lane can only
DISPLACE a page, never add one. Its effect is read through nDCG/MAP/MRR and the DISPLACEMENT COUNT,
with coverage reported as a predicted non-increase. Reading a coverage null as "RAPTOR does not
help" would be reading a property of the unit as a finding about the lane.

READ-ONLY. No writes to any collection, no re-ingest, no re-embed of the corpus. HyDE ON and frozen
(a cache miss RAISES). DA ON, graph lane ON, RAPTOR now present in the index (S2).
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
POLICY_CONFIRM = "logs/p1/step10/policy_confirm.json"   # the live shipped-product run (§4 G2)
T0_ARTIFACT = "logs/p1/step10/t0_baseline.json"          # for the reachable-page anchor (G7)
BASE = Path("logs/p1/step10")
ANCHOR_TOL = 1e-4

ARMS: dict[str, tuple[str, ...] | None] = {
    "F0": None,
    "F0f": (),
    "F1": ("da",),
    "F2": ("graph",),
    "F3": ("raptor",),
    "F4": ("da", "graph", "raptor"),
}
TREATMENTS = ("F1", "F2", "F3", "F4")

# ⚠️ Lane-contribution markers. A candidate's ORIGIN is read off its payload, because the pool is a
# fused, page-deduped list by the time the harness sees it:
#   DA     — `source_type == "da_parent"` (`store._resolve_da_parents`)
#   RAPTOR — `source_type == "raptor_summary"` (the node's own payload)
#   graph  — NO `source_type` key at all: `graph_search` returns `page_num`/`text_preview`/`chunk_id`
#            from Cypher and `search_fused` normalises only `page_number`/`text`.
# G5 fails if an arm's own lane contributed ZERO candidates — such an arm is a copy of F0f.
LANE_MARKER = {"da": lambda h: h.get("source_type") == "da_parent",
               "raptor": lambda h: h.get("source_type") == "raptor_summary",
               "graph": lambda h: "source_type" not in h}

ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20",
                 "precision_at_20", "f1_at_20")
# the six `compute_retrieval_metrics` keys that are computed from `reranked` alone (endpoint)
RERANKED_KEYS = ("ndcg_at_20", "map", "recall_at_20", "hit_at_20", "precision_at_20", "f1_at_20")

socket.setdefaulttimeout(90)
RETRIES = 3
LANE_RETRIES = 3

_COLBERT_DROP: dict[str, int] = {"n": 0}


def _install_colbert_watch() -> None:
    """Count ColBERT query failures — the store swallows them and fuses from a REDUCED lane set."""
    from src.pdf_ingestion import colbert_embedder as ce

    for cls in (ce.StubColBERTEmbedder, ce.ClusterColBERTEmbedder, ce.FastembedColBERTEmbedder):
        orig = cls.embed_query

        def wrap(self, text, _o=orig):
            try:
                return _o(self, text)
            except Exception:
                _COLBERT_DROP["n"] += 1
                raise

        cls.embed_query = wrap


def _load_queries() -> list[dict]:
    raw = json.loads(Path(QUERIES).read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-"))
         and (x.get("relevant_pages") or [])]
    q.sort(key=lambda x: x["id"])
    return q


def _reachable_pages(store, cfg) -> set[int]:
    """T0's `coll_pages`: every in-window content page the product filter can reach (read-only)."""
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
            limit=1000, offset=offset, with_payload=["page_number"], with_vectors=False)
        for r in recs:
            p = (r.payload or {}).get("page_number")
            if p is not None:
                pages.add(int(p))
        if offset is None:
            break
    return pages


def _pages_of(hits) -> list[int]:
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
    for rank, p in enumerate(pages, start=1):
        if p in rel:
            return round(1.0 / rank, 4)
    return 0.0


def _metrics_from_pages(pages: list[int], rel: list[int], cfg) -> dict:
    """Endpoint metrics for a page list alone — the same synthesis T4 used for its anchors.

    `compute_retrieval_metrics` derives ndcg/map/recall_at_k/hit_at_k/precision_at_k/f1_at_k from
    `reranked` ONLY, so scoring `reranked = hits = hits_above = the page list` reproduces the
    endpoint metrics exactly; `mrr` (a pool field) is deliberately not read from here.
    """
    synth = [{"page_number": p} for p in pages]
    m = compute_retrieval_metrics({"hits": synth, "hits_above": synth, "reranked": synth}, rel, cfg)
    m["mrr_at_20"] = _endpoint_mrr(pages, set(rel))
    return m


def _ci(deltas: list[float]) -> dict:
    # ⚠️ §I69 — the metric function returns np.float64, which does NOT survive JSON. Every aggregate
    # is cast to a plain float at the source rather than relying on a dumps default.
    n = len(deltas)
    if n < 2:
        return {"n": n,
                "mean": float(statistics.mean(deltas)) if deltas else None,
                "sd": None, "ci95": None}
    m = float(statistics.mean(deltas))
    sd = float(statistics.stdev(deltas))
    half = float(1.96 * sd / math.sqrt(n))
    return {"n": n, "mean": m, "sd": sd, "ci95": [m - half, m + half]}


def _f(x):
    """np.float64 -> float, None-preserving."""
    return None if x is None else float(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="", help="comma-separated query ids (a targeted smoke)")
    ap.add_argument("--out", default=str(BASE / "lane_inclusion.json"))
    args = ap.parse_args()

    cfg = get_settings()
    if not cfg.da_enabled:
        logger.error("da_enabled is False — this run needs the registered lane set (DA ON)")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    _install_colbert_watch()

    queries = _load_queries()
    if args.ids:
        want = {s.strip() for s in args.ids.split(",") if s.strip()}
        queries = [q for q in queries if q["id"] in want]
    if args.limit:
        queries = queries[: args.limit]

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

    # one store per arm (a DocumentStore opens a Qdrant client and a SQLite engine)
    ARM_STORES = {a: DocumentStore(cfg) for a in ARMS}

    per_query: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()
    try:
        for i, q in enumerate(queries, 1):
            qid, text, qtype = q["id"], q["query"], q.get("query_type", "factual")
            rel = {int(p) for p in q["relevant_pages"]}
            rq = rel & reach
            rec: dict = {"id": qid, "query_type": qtype, "n_relevant": len(rel),
                         "n_reachable": len(rq), "relevant_pages": sorted(rel)}
            try:
                for arm, lanes in ARMS.items():
                    st = ARM_STORES[arm]

                    def _call():
                        """One retrieval, retried when a lane SILENTLY dropped.

                        A call whose lane failed is fused from a reduced lane set, so it is not the
                        treatment. The counters are read per call (§I96) and the call retried.
                        """
                        retries, drops = 0, {}
                        while True:
                            before = {"colbert": _COLBERT_DROP["n"], "da": st.da_dropouts,
                                      "raptor": st.raptor_dropouts}
                            r = _retry(run_retrieval, text, st, embedder, reranker, cfg, "global",
                                       0.0, query_type=qtype, lanes=lanes)
                            drops = {k: getattr(st, f"{k}_dropouts") - v
                                     for k, v in before.items() if k != "colbert"}
                            drops["colbert"] = _COLBERT_DROP["n"] - before["colbert"]
                            if not any(drops.values()) or retries >= LANE_RETRIES:
                                return r, drops, retries
                            retries += 1
                            logger.warning("[{}] arm {}: lane dropout {} — retry {}/{}",
                                           qid, arm, drops, retries, LANE_RETRIES)

                    fb_before = getattr(reranker, "fallbacks", 0)
                    ret, drops, lane_retries = _call()
                    fb = getattr(reranker, "fallbacks", 0) > fb_before

                    pool = ret["hits"]
                    endp = ret["reranked"]
                    pages = _pages_of(endp)
                    pool_pages = _pages_of(pool)
                    rec[f"{arm}_pages"] = pages
                    rec[f"{arm}_slots"] = [h.get("page_number") for h in endp]
                    rec[f"{arm}_pool_size"] = len(pool_pages)
                    rec[f"{arm}_pool_pages"] = pool_pages
                    rec[f"{arm}_pool_sha"] = hashlib.sha256(
                        ",".join(map(str, pool_pages)).encode()).hexdigest()[:16]
                    rec[f"{arm}_pool_cov"] = _cov(pool_pages, rq)
                    rec[f"{arm}_cov"] = _cov(pages, rq)
                    rec[f"{arm}_lane_drops"] = drops
                    rec[f"{arm}_lane_retries"] = lane_retries
                    rec[f"{arm}_reranker_fallback"] = fb
                    # §4 G5 — how many candidates each lane actually CONTRIBUTED, and how many
                    # page-less candidates (the RAPTOR displacement channel, §11b) reached the pool
                    # and the endpoint.
                    rec[f"{arm}_contrib"] = {ln: sum(1 for h in pool if mk(h))
                                             for ln, mk in LANE_MARKER.items()}
                    rec[f"{arm}_pool_pageless"] = sum(1 for h in pool
                                                      if h.get("page_number") is None)
                    rec[f"{arm}_endp_pageless"] = sum(1 for h in endp
                                                      if h.get("page_number") is None)
                    m = compute_retrieval_metrics(ret, sorted(rel), cfg)
                    m["mrr_at_20"] = _endpoint_mrr(pages, rel)
                    rec[f"{arm}_metrics"] = m
                per_query.append(rec)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
                logger.error("[{}] FAILED: {}", qid, exc)
                per_query.append({**rec, "error": str(exc)})
            if i % 10 == 0:
                logger.info("  {}/{} queries ({:.0f}s)", i, len(queries), time.time() - t0)
    finally:
        llm_mod.call_llm = _real_call_llm
    wall = time.time() - t0

    ok = [r for r in per_query if "error" not in r]

    def agg(arm: str, sub=None):
        rows = sub if sub is not None else ok
        out: dict = {"n": len(rows)}
        covs = [r[f"{arm}_cov"] for r in rows if r.get(f"{arm}_cov") is not None]
        out["coverage_reachable"] = _f(statistics.mean(covs)) if covs else None
        pcovs = [r[f"{arm}_pool_cov"] for r in rows if r.get(f"{arm}_pool_cov") is not None]
        out["pool_cov"] = _f(statistics.mean(pcovs)) if pcovs else None
        out["pool_mean"] = _f(statistics.mean([r[f"{arm}_pool_size"] for r in rows])) if rows else None
        for key in ENDPOINT_KEYS:
            vals = [r[f"{arm}_metrics"][key] for r in rows
                    if r.get(f"{arm}_metrics") and r[f"{arm}_metrics"].get(key) is not None]
            out[key] = _f(statistics.mean(vals)) if vals else None
        out["precision_ceiling_at_20"] = _f(statistics.mean(
            [r[f"{arm}_metrics"]["precision_ceiling_at_20"] for r in rows
             if r.get(f"{arm}_metrics")])) if rows else None
        for ln in LANE_MARKER:
            out[f"contrib_{ln}_mean"] = _f(statistics.mean(
                [r[f"{arm}_contrib"][ln] for r in rows])) if rows else None
        out["pool_pageless_mean"] = _f(statistics.mean(
            [r[f"{arm}_pool_pageless"] for r in rows])) if rows else None
        out["endp_pageless_mean"] = _f(statistics.mean(
            [r[f"{arm}_endp_pageless"] for r in rows])) if rows else None
        return out

    aggregate = {arm: {"overall": agg(arm),
                       "by_type": {qt: agg(arm, [r for r in ok if r["query_type"] == qt])
                                   for qt in ("factual", "multihop", "overview")}}
                 for arm in ARMS}

    def delta(a_arm: str, b_arm: str, key: str, sub=None) -> dict:
        rows = sub if sub is not None else ok
        d = [(r[f"{b_arm}_metrics"][key] - r[f"{a_arm}_metrics"][key]) for r in rows
             if r.get(f"{a_arm}_metrics") and r.get(f"{b_arm}_metrics")
             and r[f"{a_arm}_metrics"].get(key) is not None
             and r[f"{b_arm}_metrics"].get(key) is not None]
        return _ci(d)

    deltas: dict = {}
    for arm in TREATMENTS:
        deltas[f"{arm}_minus_F0f"] = {k: delta("F0f", arm, k) for k in ENDPOINT_KEYS}
        deltas[f"{arm}_minus_F0"] = {k: delta("F0", arm, k) for k in ENDPOINT_KEYS}
        deltas[f"{arm}_minus_F0f_by_type"] = {
            qt: {k: delta("F0f", arm, k, [r for r in ok if r["query_type"] == qt])
                 for k in ("ndcg_at_20", "map", "mrr_at_20")}
            for qt in ("factual", "multihop", "overview")}
    deltas["F0_minus_F0f"] = {k: delta("F0f", "F0", k) for k in ENDPOINT_KEYS}
    deltas["cov_F3_minus_F0f"] = _ci([(r["F3_cov"] - r["F0f_cov"]) for r in ok
                                      if r.get("F3_cov") is not None
                                      and r.get("F0f_cov") is not None])

    # ── guards ───────────────────────────────────────────────────────────────────────────────────
    # G2 — F0 must reproduce the SHIPPED product endpoint. The reference is the live run of the
    # shipped code (`policy_confirm.json`, one day earlier, same env), re-derived from ITS OWN
    # per-query page lists through the harness's metric function, so the anchor cannot be satisfied
    # by the harness agreeing with itself.
    pc = json.loads(Path(POLICY_CONFIRM).read_text())
    pc_rows = {r["id"]: r for r in pc["per_query"] if "pages" in r}
    pc_vals: dict[str, list[float]] = {k: [] for k in ENDPOINT_KEYS}
    pc_by_type: dict[str, dict[str, list[float]]] = {
        qt: {k: [] for k in ENDPOINT_KEYS} for qt in ("factual", "multihop", "overview")}
    for r in ok:
        row = pc_rows.get(r["id"])
        if not row:
            continue
        m = _metrics_from_pages([int(p) for p in row["pages"]],
                                sorted({int(p) for p in r["relevant_pages"]}), cfg)
        for k in ENDPOINT_KEYS:
            if m.get(k) is not None:
                pc_vals[k].append(m[k])
                pc_by_type[r["query_type"]][k].append(m[k])
    pc_agg = {k: _f(statistics.mean(v)) if v else None for k, v in pc_vals.items()}
    pc_agg_by_type = {qt: {k: _f(statistics.mean(v)) if v else None for k, v in d.items()}
                      for qt, d in pc_by_type.items()}
    # ⚠️ §11g — the anchor is asserted PER TYPE, and ONLY on the two types where the smoke found F0
    # reproducing the shipped run. OVERVIEW is reported, never asserted: S2 wrote 73 RAPTOR points
    # into the very collection these queries search, so the pool that yesterday's run saw is not the
    # pool that exists today — the smoke measured divergence in BOTH directions (ovw-001 nDCG
    # 0.4068 vs 0.5909; ovw-003 0.4583 vs 0.2669), which is what a perturbed pool looks like rather
    # than a systematic offset. Asserting it would be a check that fails on correct data.
    g2_detail: dict = {}
    g2_ok = True
    for qt in ("factual", "multihop"):
        for k in ENDPOINT_KEYS:
            got = aggregate["F0"]["by_type"][qt].get(k)
            want = pc_agg_by_type[qt].get(k)
            hit = bool(got is not None and want is not None and abs(got - want) <= ANCHOR_TOL)
            g2_ok = g2_ok and hit
            g2_detail[f"{qt}.{k}"] = {"got": got, "want": want, "within_tol": hit}
    g2_overview_report = {k: {"got": aggregate["F0"]["by_type"]["overview"].get(k),
                              "want": pc_agg_by_type["overview"].get(k)}
                          for k in ENDPOINT_KEYS}
    pc_pages_mismatch = [r["id"] for r in ok
                         if r["id"] in pc_rows
                         and r["F0_pages"] != [int(p) for p in pc_rows[r["id"]]["pages"]]]
    pc_pages_mismatch_by_type: dict[str, int] = {}
    for qid in pc_pages_mismatch:
        qt = next(r["query_type"] for r in ok if r["id"] == qid)
        pc_pages_mismatch_by_type[qt] = pc_pages_mismatch_by_type.get(qt, 0) + 1

    # G3 — against F0f (the vector-only fused control), each treatment arm's pool is a SUPERSET.
    # ⚠️ NOT against F0: the arms REPLACE the composition (§11c), so a smaller pool is legitimate.
    # ⚠️ §11e — asserted ONLY for the GRAPH-FREE arms (F1, F3) and only where the 100-slot cut does
    # not bind. `search_fused` calls `_mmr_select` only when `len(deduped) > fetch_k` (=100) and it
    # DROPS candidates; and the GRAPH lane's Cypher has NO stable ORDER BY, measured this session as
    # pool sizes [90, 88, 90] across three IDENTICAL calls in one process — so F2/F4's pool is not
    # reproducible and a superset assertion on them is a check that fails on correct data. F2/F4 are
    # REPORTED (`G3_pool_superset_violations`), never asserted.
    g3_missing: dict[str, list[str]] = {a: [] for a in TREATMENTS}
    g3_cut_affected: list[str] = []
    for r in ok:
        if r.get("F0f_pool_pages") is None:
            continue
        base = set(r["F0f_pool_pages"])
        if any((r.get(f"{a}_pool_size") or 0) >= 100 for a in ARMS):
            g3_cut_affected.append(r["id"])
            continue
        for arm in TREATMENTS:
            pp = r.get(f"{arm}_pool_pages")
            if pp is None:
                continue
            if not base <= set(pp):
                g3_missing[arm].append(r["id"])
    g3_ok = not g3_missing["F1"] and not g3_missing["F3"]

    drops = [f"{r['id']}/{a}" for r in ok for a in ARMS
             if r.get(f"{a}_lane_drops") and r[f"{a}_lane_drops"].get("colbert")]
    raptor_drops = [f"{r['id']}/{a}" for r in ok for a in ARMS
                    if r.get(f"{a}_lane_drops") and r[f"{a}_lane_drops"].get("raptor")]
    falls = [f"{r['id']}/{a}" for r in ok for a in ARMS if r.get(f"{a}_reranker_fallback")]
    retried = [f"{r['id']}/{a}" for r in ok for a in ARMS if r.get(f"{a}_lane_retries")]

    # G5 — each treatment arm's OWN lane must have contributed at least one candidate, overall and
    # on the type the lane targets. An arm whose lane returned nothing is a copy of F0f.
    def _contrib_total(arm, lane, qtypes=None):
        rows = [r for r in ok if qtypes is None or r["query_type"] in qtypes]
        return sum(r[f"{arm}_contrib"][lane] for r in rows)

    g5_detail = {
        "F1_da_total": _contrib_total("F1", "da"),
        "F2_graph_total": _contrib_total("F2", "graph"),
        "F2_graph_total_multihop": _contrib_total("F2", "graph", ("multihop",)),
        "F3_raptor_total": _contrib_total("F3", "raptor"),
        "F3_raptor_total_overview": _contrib_total("F3", "raptor", ("overview",)),
        "F4_all_three_total": {ln: _contrib_total("F4", ln) for ln in LANE_MARKER},
    }
    g5_ok = (g5_detail["F1_da_total"] > 0 and g5_detail["F2_graph_total"] > 0
             and g5_detail["F3_raptor_total"] > 0
             and g5_detail["F3_raptor_total_overview"] > 0)

    t0_pages = {int(p) for p in json.loads(Path(T0_ARTIFACT).read_text())["meta"]["coll_pages"]}

    guards = {
        "G1_133_queries_0_errors": (len(ok) == len(queries) and not errors),
        "G2_F0_reproduces_the_shipped_product_endpoint": g2_ok,
        "G3_F0f_subset_each_treatment_pool": g3_ok,
        "G4_no_reranker_fallback_in_any_arm": not falls,
        "G5_each_treatment_lane_contributed_candidates": g5_ok,
        "G6_no_colbert_lane_dropout_in_accepted_calls": not drops,
        "G6b_no_raptor_lane_dropout_in_accepted_calls": not raptor_drops,
        "G7_reachable_set_matches_T0": (reach == t0_pages),
    }

    artifact = {
        "meta": {
            "question": "does making a lane a first-class RRF participant change its sign/ordering?",
            "prereg": ".hermes/plans/2026-10-29-p1-lane-inclusion-preregistration.md",
            "collection": cfg.qdrant_collection, "dense_model": cfg.dense_model,
            "dense_dim": cfg.dense_dim, "qdrant_host": cfg.qdrant_host,
            "da_enabled": bool(cfg.da_enabled), "graph_lane": "ON",
            "raptor_lane": "PRESENT IN THE INDEX (S2 carry-over, 73 nodes) and wired (S3)",
            "hyde": "ON and frozen", "hyde_cache": cache.path.name,
            "arms": {a: (None if v is None else list(v)) for a, v in ARMS.items()},
            "anchor": {"G2": f"F0 vs the live shipped-product run {POLICY_CONFIRM}, re-derived from "
                             f"its own per-query page lists, asserted PER TYPE on FACTUAL and "
                             f"MULTIHOP only (§11g); OVERVIEW is reported, not asserted",
                       "tol": ANCHOR_TOL,
                       "why_overview_is_not_asserted": "S2 wrote 73 RAPTOR points into the collection "
                                                       "these queries search, so yesterday's pool is "
                                                       "not today's; the smoke measured divergence in "
                                                       "BOTH directions",
                       "G2c_determinism": "F0 bit-stable across two smoke runs "
                                          "(lane_inclusion_smoke.json vs lane_inclusion_smoke2.json)"},
            "reachable_pages": len(reach),
            "reachable_pages_set_sha": hashlib.sha256(
                ",".join(str(p) for p in sorted(reach)).encode()).hexdigest()[:16],
            "t0_reachable_pages_set_sha": hashlib.sha256(
                ",".join(str(p) for p in sorted(t0_pages)).encode()).hexdigest()[:16],
            "n_queries": len(queries), "n_errors": len(errors), "wall_seconds": round(wall, 1),
            "unit": "page-level, the product's convention (pages of the top-k chunks)",
            "lane_marker_convention": {
                "da": 'payload source_type == "da_parent"',
                "raptor": 'payload source_type == "raptor_summary"',
                "graph": "NO source_type key (graph_search returns page_num/text_preview/chunk_id)",
            },
            "note_raptor_pageless": "⚠️ §11b — a RAPTOR summary has no page_number, so the lane can "
                                    "only DISPLACE a page at this unit; read coverage as a predicted "
                                    "non-increase and the effect through nDCG/MAP/MRR + the "
                                    "displacement counts.",
            "note_ndcg_scale": "nDCG's IDCG uses min(n, reranker_top_k) — comparable across arms "
                               "(all k=20).",
            "field_conventions": {
                "ENDPOINT": list(ENDPOINT_KEYS) + ["coverage_reachable"],
                "POOL": ["mrr", "recall_at_100", "pool_cov"],
            },
            "lane_health": {"colbert_dropouts_total": _COLBERT_DROP["n"],
                            "lane_retries_used": len(retried),
                            "lane_retries_allowed_per_call": LANE_RETRIES},
        },
        "aggregate": aggregate,
        "deltas": deltas,
        "guards": guards,
        "guard_detail": {"G2": g2_detail, "G2_policy_confirm_aggregate": pc_agg,
                         "G2_policy_confirm_aggregate_by_type": pc_agg_by_type,
                         "G2_overview_REPORTED_not_asserted": g2_overview_report,
                         "G2_per_query_page_mismatch_ids": pc_pages_mismatch,
                         "G2_per_query_page_mismatch_by_type": pc_pages_mismatch_by_type,
                         "G3_pool_superset_violations": g3_missing,
                         "G3_cut_affected_ids": g3_cut_affected,
                         "G5": g5_detail,
                         "colbert_drop_ids": drops, "raptor_drop_ids": raptor_drops,
                         "reranker_fallback_ids": falls, "lane_retried_ids": retried},
        "errors": errors,
        "per_query": per_query,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, default=float))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()

    print(json.dumps({"aggregate": {a: aggregate[a]["overall"] for a in ARMS},
                      "deltas": {k: {kk: (vv.get("mean") if isinstance(vv, dict) else vv)
                                     for kk, vv in v.items()}
                                 for k, v in deltas.items() if isinstance(v, dict)},
                      "guards": guards}, indent=2))
    print(f"\nartifact: {out}\nsha256: {sha}")
    failed = [k for k, v in guards.items() if v is False]
    print("ALL GUARDS PASS" if not failed else "GUARD FAILURE: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
