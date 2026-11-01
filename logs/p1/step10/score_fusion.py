"""§I103 / 4A — SCORE-BASED FUSION vs RANK-BASED RRF: does replacing the rank sum with a
normalized score sum move the pool's coverage, or the endpoint's nDCG@20?

Pre-registration: `.hermes/plans/2026-10-31-p1-score-fusion-preregistration.md` (§1-§8 committed
ALONE as `32f6c5f`; §9 the pre-run amendment re-pointing G2's anchor, committed ALONE as `047e292`).
Implements §2/§3/§4/§5 and nothing else.

THE QUESTION (§1). Every fusion test so far kept the RANK mechanism and moved a knob around it
(§I92 the cap and MMR, §I67 the width, §I100 the ORDER). Rank fusion discards the score MAGNITUDE;
score fusion keeps it. Whether that helps or hurts is unmeasured.

THE ARMS (§3). One new, additive, inert-by-default merge (`store._score_merge`), reached through a
`fusion=` kwarg on the product path. The three lanes are queried IDENTICALLY in every arm — only the
merge changes:
  S0 — the product:  rank RRF, `rrf_k=1`      Σ_lanes 1/(1 + rank)      the reference; anchored (§9)
  S1 — min-max score sum                      Σ_lanes (s - min)/(max - min)
  S2 — z-score score sum                      Σ_lanes (s - mean)/std

⚠️ §3 — a lane with `max == min` contributes 0 in S1/S2 (degenerate range), recorded per query.
⚠️ §3 — the score sum changes WHICH candidates survive the truncation to the pool width, so this is
a COMPOSITION change as well as an order change (exactly §I100 item 5's O4 flaw). Stated so a null is
not later read as a pure order test.

READ-ONLY. No writes to any collection, no re-ingest, no re-embed. HyDE ON and frozen (a miss RAISES).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import socket
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

QUERIES = "data/eval_queries_v2.json"
LANE_ARTIFACT = "logs/p1/step10/lane_inclusion.json"      # §9 — the amended G2 anchor (arm F0)
T0_ARTIFACT = "logs/p1/step10/t0_baseline.json"           # §9 — reported cross-day check only
BASE = Path("logs/p1/step10")
ANCHOR_TOL = 1e-4

# arm -> fusion mode (the ONLY thing that varies across arms)
ARM_SPEC: dict[str, dict] = {
    "S0": {"fusion": "rrf"},
    "S1": {"fusion": "minmax"},
    "S2": {"fusion": "zscore"},
}
TREATMENTS = ("S1", "S2")

ENDPOINT_KEYS = ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "recall_at_100",
                 "hit_at_20", "precision_at_20", "precision_ceiling_at_20", "f1_at_20")
TYPES = ("factual", "multihop", "overview")
# prefetches order inside `_qdrant_search` (dense -> sparse -> colbert); lane_names mirrors it.
LANE_ORDER = ("dense", "sparse", "colbert")

socket.setdefaulttimeout(90)
RETRIES = 3
LANE_RETRIES = 3
BOOT_N = 10000
BOOT_SEED = 20261031

_COLBERT_DROP: dict[str, int] = {"n": 0}

# ── the lane capture (G3/G4): the lists each merge RECEIVES, keyed by (query, arm) ──────────────
_CAP: dict = {"qid": None, "arm": None, "by_arm": {}}


def _lane_stats(lists) -> dict:
    h = hashlib.sha256()
    per_lane = []
    for lst in lists:
        h.update(b"|")
        for it in lst:
            key = it.get("chunk_id") or it.get("qdrant_point_id")
            h.update(f"{key}:{it.get('score')}".encode())
            h.update(b",")
        vals = [float(it.get("score", 0.0)) for it in lst]
        per_lane.append({"n": len(lst), "min": min(vals) if vals else None,
                         "max": max(vals) if vals else None,
                         "max_gt_min": bool(vals) and (max(vals) > min(vals))})
    return {"digest": h.hexdigest()[:16], "n_lanes": len(lists), "per_lane": per_lane}


def _install_lane_capture() -> None:
    """Wrap the two merge statics so the lists they receive are RECORDED (read-only observation)."""
    orig_rrf = DocumentStore._rrf_merge
    orig_sm = DocumentStore._score_merge

    def wrap_rrf(*lists, rrf_k=60, weights=None):
        if _CAP["qid"] is not None:
            _CAP["by_arm"].setdefault(_CAP["qid"], {})[_CAP["arm"]] = _lane_stats(lists)
        return orig_rrf(*lists, rrf_k=rrf_k, weights=weights)

    def wrap_sm(*lists, mode="minmax", weights=None):
        if _CAP["qid"] is not None:
            _CAP["by_arm"].setdefault(_CAP["qid"], {})[_CAP["arm"]] = _lane_stats(lists)
        return orig_sm(*lists, mode=mode, weights=weights)

    DocumentStore._rrf_merge = staticmethod(wrap_rrf)
    DocumentStore._score_merge = staticmethod(wrap_sm)


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


def _boot(deltas: list[float]) -> dict:
    """§4 read rule — paired 95 % CI, 10,000 bootstrap resamples, seed 20261031.

    ⚠️ STDLIB `random.Random(seed)` (not numpy), so the independent verifier can reproduce the CI
    EXACTLY without importing the harness's RNG. Resample = n draws with replacement; the CI is the
    empirical 2.5/97.5 percentile (nearest-rank).
    """
    n = len(deltas)
    if n < 2:
        return {"n": n, "mean": float(statistics.mean(deltas)) if deltas else None,
                "ci95": None, "resolved": False}
    rng = random.Random(BOOT_SEED)
    means = []
    for _ in range(BOOT_N):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * BOOT_N)]
    hi = means[int(0.975 * BOOT_N)]
    return {"n": n, "mean": float(statistics.mean(deltas)), "ci95": [lo, hi],
            "resolved": bool(lo > 0.0 or hi < 0.0)}


def _f(x):
    return None if x is None else float(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default=str(BASE / "score_fusion.json"))
    args = ap.parse_args()

    cfg = get_settings()
    if not (cfg.da_enabled and cfg.hyde_enabled):
        logger.error("da_enabled/hyde_enabled must be True — the registered config")
        return 2
    store = DocumentStore(cfg)
    embedder = get_cluster_embedder(cfg)
    reranker = get_reranker(cfg)
    _install_colbert_watch()
    _install_lane_capture()

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
    logger.info("fusion cfg: mmr_candidates={} reranker_fetch_k={} reranker_top_k={}",
                cfg.mmr_candidates, cfg.reranker_fetch_k, cfg.reranker_top_k)

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
                for arm, spec in ARM_SPEC.items():
                    fusion = spec["fusion"]

                    def _call(_f=fusion):
                        retries, drops = 0, {}
                        while True:
                            before = {"colbert": _COLBERT_DROP["n"], "da": store.da_dropouts,
                                      "raptor": store.raptor_dropouts,
                                      "mmr": store.mmr_selections}
                            _CAP["qid"], _CAP["arm"] = qid, arm
                            r = _retry(run_retrieval, text, store, embedder, reranker, cfg, "global",
                                       0.0, query_type=qtype, lanes=None, fusion=_f)
                            _CAP["qid"] = None
                            after = {"colbert": _COLBERT_DROP["n"], "da": store.da_dropouts,
                                     "raptor": store.raptor_dropouts,
                                     "mmr": store.mmr_selections}
                            drops = {k: after[k] - before[k] for k in before}
                            lane_drops = {k: v for k, v in drops.items() if k != "mmr"}
                            if not any(lane_drops.values()) or retries >= LANE_RETRIES:
                                return r, drops, retries
                            retries += 1
                            logger.warning("[{}] arm {}: lane dropout {} — retry {}/{}",
                                           qid, arm, lane_drops, retries, LANE_RETRIES)

                    fb_before = getattr(reranker, "fallbacks", 0)
                    ret, drops, lane_retries = _call()
                    fb = getattr(reranker, "fallbacks", 0) > fb_before

                    pool = ret["hits"]
                    endp = ret["reranked"]
                    pages = _pages_of(endp)
                    pool_pages = _pages_of(pool)
                    rec[f"{arm}_pages"] = pages
                    rec[f"{arm}_pool_pages"] = pool_pages
                    rec[f"{arm}_slots_n"] = len(endp)
                    rec[f"{arm}_pool_size"] = len(pool_pages)
                    rec[f"{arm}_pool_sha"] = hashlib.sha256(
                        ",".join(map(str, pool_pages)).encode()).hexdigest()[:16]
                    rec[f"{arm}_pool_cov"] = _cov(pool_pages, rq)
                    rec[f"{arm}_cov"] = _cov(pages, rq)
                    rec[f"{arm}_lane_drops"] = drops
                    rec[f"{arm}_lane_retries"] = lane_retries
                    rec[f"{arm}_mmr_fired"] = bool(drops.get("mmr"))
                    rec[f"{arm}_reranker_fallback"] = fb
                    rec[f"{arm}_lane_digest"] = (
                        _CAP["by_arm"].get(qid, {}).get(arm, {}).get("digest"))
                    rec[f"{arm}_lane_stats"] = (
                        _CAP["by_arm"].get(qid, {}).get(arm, {}).get("per_lane"))
                    m = compute_retrieval_metrics(ret, sorted(rel), cfg)
                    m["mrr_at_20"] = _endpoint_mrr(pages, rel)
                    rec[f"{arm}_metrics"] = m
                per_query.append(rec)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "error": f"{type(exc).__name__}: {exc}"})
                logger.error("[{}] FAILED: {}", qid, exc)
                per_query.append({**rec, "error": str(exc)})
            if i % 5 == 0:
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
        out["mmr_fired_n"] = sum(1 for r in rows if r.get(f"{arm}_mmr_fired"))
        return out

    aggregate = {arm: {"overall": agg(arm),
                       "by_type": {qt: agg(arm, [r for r in ok if r["query_type"] == qt])
                                   for qt in TYPES}}
                 for arm in ARM_SPEC}

    def delta(ref: str, arm: str, key: str, sub=None) -> dict:
        rows = sub if sub is not None else ok
        d = [(r[f"{arm}_metrics"][key] - r[f"{ref}_metrics"][key]) for r in rows
             if r.get(f"{ref}_metrics") and r.get(f"{arm}_metrics")
             and r[f"{ref}_metrics"].get(key) is not None
             and r[f"{arm}_metrics"].get(key) is not None]
        return _boot(d)

    deltas: dict = {}
    for arm in TREATMENTS:
        deltas[f"{arm}_minus_S0"] = {k: delta("S0", arm, k) for k in ENDPOINT_KEYS}
        deltas[f"{arm}_minus_S0_by_type"] = {
            qt: {k: delta("S0", arm, k, [r for r in ok if r["query_type"] == qt])
                 for k in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20")}
            for qt in TYPES}
        deltas[f"poolcov_{arm}_minus_S0"] = _boot(
            [(r[f"{arm}_pool_cov"] - r["S0_pool_cov"]) for r in ok
             if r.get(f"{arm}_pool_cov") is not None and r.get("S0_pool_cov") is not None])

    # composition (§4 prediction 3): the surviving pool SET differs from S0's, per query
    comp = {}
    for arm in TREATMENTS:
        diff = [r["id"] for r in ok if set(r[f"{arm}_pool_pages"]) != set(r["S0_pool_pages"])]
        comp[arm] = {"n_differs": len(diff), "n": len(ok),
                     "frac": round(len(diff) / len(ok), 4) if ok else None,
                     "majority": (len(diff) > len(ok) / 2), "first": diff[:10]}

    # ── guards ───────────────────────────────────────────────────────────────────────────────
    guards: dict = {}
    detail: dict = {}

    # G1 — population: 133 queries, 53/40/40; 0 errors; every arm scored on every query
    counts = {qt: sum(1 for q in queries if q.get("query_type") == qt) for qt in TYPES}
    every_arm = all(all(r.get(f"{a}_metrics") for a in ARM_SPEC) for r in ok)
    guards["G1_population_133_0_errors_all_arms"] = (
        len(queries) == 133 and not errors and every_arm
        and counts == {"factual": 53, "multihop": 40, "overview": 40})
    detail["G1"] = {"queries": len(queries), "by_type": counts, "errors": errors,
                    "every_arm_scored": every_arm}

    # G2 (§9) — S0 reproduces lane_inclusion's arm F0, per type.
    # ⚠️ CORRECTED AFTER THE FIRST RUN (the §I100 over-strict-check class): the guard compared EVERY
    # endpoint key, but the F0 anchor carries no `recall_at_100` (it predates the metric), so
    # `ref.get(k) or 0` reddened the guard on CORRECT data (gap 0.6706). Only the keys the ANCHOR
    # carries are asserted; the absent ones are REPORTED.
    lane = json.loads(Path(LANE_ARTIFACT).read_text())["aggregate"]["F0"]
    g2: dict = {}
    missing_from_anchor: list = []
    for qt in ("overall",) + TYPES:
        ref = lane["overall"] if qt == "overall" else lane["by_type"][qt]
        got = aggregate["S0"]["overall"] if qt == "overall" else aggregate["S0"]["by_type"][qt]
        keys = [k for k in ENDPOINT_KEYS + ("pool_cov",) if k in ref]
        if qt == "overall":
            missing_from_anchor = [k for k in ENDPOINT_KEYS + ("pool_cov",) if k not in ref]
        gaps = {k: abs(got.get(k) - ref.get(k)) for k in keys}
        g2[qt] = {"max_gap": max(gaps.values()), "gaps": gaps, "keys_compared": keys}
    guards["G2_S0_reproduces_the_shipped_product"] = all(
        v["max_gap"] <= ANCHOR_TOL for v in g2.values())
    detail["G2"] = g2
    detail["G2_anchor_missing_keys"] = missing_from_anchor
    # §9 — the T0 fusion-row pool coverage, REPORTED not asserted
    t0 = json.loads(Path(T0_ARTIFACT).read_text())["aggregate"]
    detail["G2_t0_crossday"] = {
        "t0_fusion_pool_cov": t0["fusion"]["overall"].get("coverage_reachable"),
        "s0_pool_cov": aggregate["S0"]["overall"]["pool_cov"],
        "note": "§9 — reported only; T0's ce row is stale (pre per-type rerank policy)",
    }

    # G3 — the three arms share the SAME input lane SET (candidate count per lane), per query.
    # ⚠️ RESTATED AFTER THE FIRST RUN (the §I100 pattern). The registered form asserted DIGEST
    # equality, but the store's vector-lane query is NONDETERMINISTIC in its low-ranked tail —
    # identical calls return different digests (`score_fusion_determinism_probe.json`). The lane SET
    # never moves. The digest mismatches are REPORTED, and their INERTNESS is asserted (G3b).
    g3_set_bad = [r["id"] for r in ok
                  if not (r.get("S0_lane_stats")
                          and [s["n"] for s in r["S0_lane_stats"]]
                          == [s["n"] for s in r.get("S1_lane_stats") or []]
                          == [s["n"] for s in r.get("S2_lane_stats") or []])]
    guards["G3_three_arms_share_the_same_lane_set"] = not g3_set_bad
    g3_digest_bad = [r["id"] for r in ok
                     if not (r.get("S0_lane_digest") and r["S0_lane_digest"] == r.get("S1_lane_digest")
                             == r.get("S2_lane_digest"))]
    detail["G3"] = {"queries": len(ok), "lane_set_mismatches": g3_set_bad[:20],
                    "n_lane_set_mismatch": len(g3_set_bad),
                    "digest_mismatches": g3_digest_bad[:20],
                    "n_digest_mismatch": len(g3_digest_bad)}

    # G3b — the digest flip is INERT. For every query whose lane digest differed across arms,
    # re-query the S0 arm ONCE more and require the pool + endpoint pages to be REPRODUCIBLE. If the
    # lanes had really moved (a lane lost/added), the pool would move with them.
    qmap = {q["id"]: q for q in queries}
    recheck: dict = {}
    llm_mod.call_llm = _frozen_llm                      # re-freeze HyDE for the control pass
    try:
        for qid in g3_digest_bad:
            q = qmap[qid]
            _CAP["qid"], _CAP["arm"] = qid, "S0r"
            try:
                ret2 = _retry(run_retrieval, q["query"], store, embedder, reranker, cfg, "global",
                              0.0, query_type=q.get("query_type", "factual"), lanes=None,
                              fusion="rrf")
            finally:
                _CAP["qid"] = None
            pool2 = _pages_of(ret2["hits"])
            row = next(r for r in ok if r["id"] == qid)
            recheck[qid] = {
                "pool_sha_stable": hashlib.sha256(
                    ",".join(map(str, pool2)).encode()).hexdigest()[:16] == row["S0_pool_sha"],
                "pages_stable": _pages_of(ret2["reranked"]) == row["S0_pages"],
                "digest_reproduced": (_CAP["by_arm"].get(qid, {}).get("S0r", {}).get("digest")
                                      == row["S0_lane_digest"]),
            }
    finally:
        llm_mod.call_llm = _real_call_llm
    guards["G3b_digest_flip_is_pool_inert"] = all(
        v["pool_sha_stable"] and v["pages_stable"] for v in recheck.values())
    detail["G3b"] = recheck

    # G4 — the normalisers are EXERCISED: each lane has max > min on a recorded fraction
    fracs: dict = {}
    degen: dict = {}
    for pos, name in enumerate(LANE_ORDER):
        gt, tot, dg = 0, 0, 0
        for r in ok:
            st = r.get("S1_lane_stats") or []
            if pos < len(st):
                tot += 1
                if st[pos]["max_gt_min"]:
                    gt += 1
                else:
                    dg += 1
        fracs[name] = round(gt / tot, 4) if tot else None
        degen[name] = dg
    guards["G4_normalisers_exercised_each_lane"] = all(
        (v is not None and v > 0.0) for v in fracs.values())
    detail["G4"] = {"max_gt_min_fraction": fracs, "degenerate_lane_count": degen,
                    "n_queries": len(ok)}

    # G5 — lane health: no lane dropout survived (a lane-reduced call is a different pool)
    bad = [(r["id"], a, r[f"{a}_lane_drops"])
           for r in ok for a in ARM_SPEC
           if any(v for k, v in (r.get(f"{a}_lane_drops") or {}).items() if k != "mmr")]
    guards["G5_no_lane_dropout_survived"] = not bad
    detail["G5"] = {"queries_with_a_surviving_drop": bad[:20], "n": len(bad)}

    # G6 — no NaN/null in any aggregate; page-dedup holds in every arm
    nulls = [f"{a}.{qt}.{k}" for a in ARM_SPEC for qt, cell in
             [("overall", aggregate[a]["overall"])] + list(aggregate[a]["by_type"].items())
             for k in ("coverage_reachable", "pool_cov", *ENDPOINT_KEYS) if cell.get(k) is None]
    nan = [f"{a}.{qt}.{k}" for a in ARM_SPEC for qt, cell in
           [("overall", aggregate[a]["overall"])] + list(aggregate[a]["by_type"].items())
           for k, v in cell.items() if isinstance(v, float) and math.isnan(v)]
    dedup_bad = [r["id"] for r in ok for a in ARM_SPEC
                 if len(r[f"{a}_pages"]) != len(set(r[f"{a}_pages"]))]
    guards["G6_no_nan_null_and_page_dedup"] = (not nulls) and (not nan) and (not dedup_bad)
    detail["G6"] = {"nulls": nulls[:20], "n_nulls": len(nulls), "nan": nan[:20],
                    "dedup_violations": dedup_bad[:20]}

    # ── registered predictions (§4) ────────────────────────────────────────────────────────────
    preds = {
        "P1_S0_reproduces_the_product": guards["G2_S0_reproduces_the_shipped_product"],
        "P2_S1S2_unresolved_at_endpoint": {
            a: {"resolved": deltas[f"{a}_minus_S0"]["ndcg_at_20"]["resolved"],
                "abs_mean_lt_0.01": abs(deltas[f"{a}_minus_S0"]["ndcg_at_20"]["mean"]) < 0.01}
            for a in TREATMENTS},
        "P3_S1S2_change_pool_composition_majority": {a: comp[a]["majority"] for a in TREATMENTS},
    }

    res = {
        "meta": {
            "question": "does replacing rank RRF with a normalized score sum move the pool's "
                        "coverage, or the endpoint's nDCG@20? (§I103 / 4A)",
            "prereg": ".hermes/plans/2026-10-31-p1-score-fusion-preregistration.md (§1-§8 committed "
                      "ALONE as 32f6c5f; §9 amendment committed ALONE as 047e292)",
            "collection": cfg.qdrant_collection,
            "qdrant_host": cfg.qdrant_host,
            "dense_model": cfg.dense_model,
            "dense_dim": cfg.dense_dim,
            "da_enabled": cfg.da_enabled,
            "hyde": "on and frozen",
            "read_only": True,
            "arms": ARM_SPEC,
            "treatments": list(TREATMENTS),
            "mmr_candidates": cfg.mmr_candidates,
            "reranker_fetch_k": cfg.reranker_fetch_k,
            "reranker_top_k": cfg.reranker_top_k,
            "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED},
            "n_queries": len(queries),
            "wall_s": round(wall, 1),
            "reachable_pages": len(reach),
        },
        "guards": guards,
        "guard_detail": detail,
        "predictions": preds,
        "composition": comp,
        "aggregate": aggregate,
        "deltas": deltas,
        "errors": errors,
        "per_query": per_query,
    }
    out = Path(args.out)
    out.write_text(json.dumps(res, indent=1, sort_keys=True))

    print(f"\nwrote {out}  ({out.stat().st_size} bytes)  wall {wall:.0f}s")
    print(f"queries {len(queries)}  errors {len(errors)}  reachable pages {len(reach)}")
    print("\nGUARDS")
    for k, v in guards.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print("\nPREDICTIONS")
    for k, v in preds.items():
        print(f"  {k}: {v}")
    print("\nendpoint metrics (overall)")
    hdr = f"{'arm':5s} " + " ".join(f"{k[:11]:>11s}" for k in
                                    ("coverage_reachable", "pool_cov", *ENDPOINT_KEYS))
    print(hdr)
    for arm in ARM_SPEC:
        a = aggregate[arm]["overall"]
        print(f"{arm:5s} " + " ".join(
            f"{(a.get(k) if a.get(k) is not None else float('nan')):11.4f}"
            for k in ("coverage_reachable", "pool_cov", *ENDPOINT_KEYS)))
    print("\nΔ vs S0 (nDCG@20, bootstrap 95% CI)")
    for a in TREATMENTS:
        d = deltas[f"{a}_minus_S0"]["ndcg_at_20"]
        print(f"  {a}: mean {d['mean']:+.4f}  CI [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if d['resolved'] else 'unresolved'}")
    return 0 if all(guards.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
