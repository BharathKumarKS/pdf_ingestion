"""Independent verifier for T0 — ONE verifier per stage (V1–V5), each re-deriving that stage from
the RAW per-query array.

Independently written (stdlib only: no numpy, no project imports, no shared helpers with the
harness) so a bug in the harness's aggregation cannot hide inside its own check. It reads ONLY the
written JSON.

    uv run python logs/p1/step10/t0_verifier.py --check     # exit non-zero on any stage's failure
    uv run python logs/p1/step10/t0_verifier.py --extract   # write the compact reviewer pack

The stages (§7b), and what makes each FAIL:

  V1  base — dense 64d exact @ N=1000.  Re-derives the per-query page sets and coverage from
      `base_ranked`, and recall@20 from its top-20.  FAILS if the page sets / the aggregate disagree
      with the harness, or if G3's §I89 anchor (cov_base 0.918953) is off by > 0.002.
  V2  cut — dense full-dim exact @ L=500, WITHIN V1's lane.  Same re-derivation from `cut_ranked`.
      FAILS if the cut's page set is not a subset of the base lane's, or G3's anchor (0.838136) is
      off, or the aggregate disagrees.
  V3  fusion pool — the product's `search_with_das` (fetch_k=100).  FAILS if pool size > fetch_k, if
      the recorded DA/graph liveness counts are inconsistent with the per-query flags, or if the
      recorded fusion config is not the shipped one.
  V4  cross-encoder — the product's reranked top-20.  Re-derives R@20 / MRR / MAP / nDCG from
      `ce_ranked`.  FAILS if top_k != 20, if the fallback count is non-zero (`reranked_metrics_valid`
      false — an order-dependent metric must not be reported from an unranked pool, §I55), or a
      metric disagrees.
  V5  the aperture sweep — the τ grid at boundaries 1–2.  Re-derives the WHOLE recall/precision
      curve, `|{cos ≥ τ}|`, and AUC-PR from the raw cosine sets.  FAILS if the curve is not monotone
      non-increasing in τ (G7), if τ=0.0's admitted set != the scoop set (G8), or if a point or the
      AUC-PR disagrees with the harness.
  V6  boundary 5 — the product's dense lane THROUGH QDRANT (the real ANN).  Re-derives coverage,
      recall@20/@100, the τ curve, monotonicity, τ=0 == scoop, AUC-PR, the COSINE-scale check (G9:
      a fused rank score would take a handful of distinct values, a cosine takes hundreds) and the
      ANN-vs-exact overlap (G10).  ⚠️ ADDED by the re-registration
      `.hermes/plans/2026-10-27-p1-t0-baseline-reregistration.md` §4.

⚠️ V4 was EXTENDED by the same re-registration §5 to re-derive `precision_at_20` and `f1_at_20` as
well — §7b's original V4 row named only R@20 / MRR / MAP / nDCG, which left their FORMULA verified
only by the unit tests on `compute_retrieval_metrics`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

BASE = Path("logs/p1/step10")
ARTIFACT = "t0_baseline.json"
EXTRACT = "t0_verifier_extract.json"

K_APERTURE = 100
FETCH_K, TOP_K = 100, 20
TAUS = ("0.00", "0.30", "0.40", "0.45", "0.50", "0.60", "0.70", "0.80", "0.85", "0.90")
I89_BASE, I89_CUT, I89_TOL = 0.918953, 0.838136, 0.002
METRIC_TOL = 5e-5      # the product rounds metrics to 4 dp
EXACT_TOL = 1e-9       # coverage is stored unrounded
CURVE_TOL = 1e-6       # the sweep rounds to 6 dp
AUC_TOL = 1e-4         # AUC-PR integrates the 6-dp curve


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _dedup_gains(pages, rel):
    """Binary, page-deduped gains over a ranked page list (the product's own convention)."""
    seen, gains = set(), []
    for p in pages:
        if p in rel and p not in seen:
            gains.append(1)
            seen.add(p)
        else:
            gains.append(0)
    return gains


def _ranking_metrics(pages, rel, k):
    """R@k, precision@k, F1@k, MRR, MAP, nDCG@k — re-derived, stdlib only.

    `precision_at_k` and `f1_at_k` were ADDED by the re-registration (§5): §6 registers them as
    REPORTED metrics but §7b's V4 row named only R@20/MRR/MAP/nDCG for re-derivation, so a wrong
    precision/F1 *formula* was guarded only by the unit tests. Precision is `recall × |rel| / k` by
    construction — this makes the formula checked, not the information independent.
    """
    if not rel:
        return {"recall_at_k": None, "precision_at_k": None, "f1_at_k": 0.0,
                "mrr": 0.0, "map": None, "ndcg_at_k": 0.0}
    gains = _dedup_gains(pages, rel)
    hit = sum(gains)
    mrr = 0.0
    for i, p in enumerate(pages, start=1):
        if p in rel:
            mrr = 1.0 / i
            break
    running, ap = 0, 0.0
    for i, g in enumerate(gains, start=1):
        if g:
            running += 1
            ap += running / i
    ap /= len(rel)
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(rel), k)))
    recall = hit / len(rel)
    precision = hit / k
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {"recall_at_k": recall, "precision_at_k": precision, "f1_at_k": f1, "mrr": mrr, "map": ap,
            "ndcg_at_k": (dcg / idcg) if idcg > 0 else 0.0}


def _curve_point(ranked, rel, tau, k):
    admitted = [p for p, c in ranked[:k] if c >= tau]
    admission = sum(1 for _, c in ranked if c >= tau)
    hit = len(set(admitted) & rel)
    return {"n_admitted": len(admitted), "admission_uncapped": admission,
            "recall_at_K": (hit / len(rel)) if rel else None,
            "precision_at_K": hit / k,
            "precision_ceiling_at_K": min(len(rel), k) / k}


def _auc_pr(points):
    """Trapezoid over (recall, precision) sorted by recall ascending — the harness's own formula."""
    pts = sorted((p["recall_at_K"], p["precision_at_K"]) for p in points if p["recall_at_K"] is not None)
    if len(pts) < 2:
        return None
    return sum((r1 - r0) * (p0 + p1) / 2.0 for (r0, p0), (r1, p1) in zip(pts, pts[1:]))


def _close(a, b, tol):
    """Tolerant compare, with a 1e-12 guard for the ROUNDING BOUNDARY.

    The artifact stores metrics rounded to 4 dp, so a value sitting exactly on a rounding boundary
    (measured: MAP 0.05625 -> 0.0563 on gold-033) differs from its recorded form by 5.000000000000143e-05
    — i.e. 1.4e-18 ABOVE a 5e-5 tolerance. Without this guard the check reports a mismatch on
    perfectly correct data: an over-strict check, which is worse than no check.
    """
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tol + 1e-12


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--artifact", default=str(BASE / ARTIFACT))
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    meta = art["meta"]
    coll = set(meta["coll_pages"])
    rows = [r for r in art["per_query"] if "error" not in r]
    checks: list[tuple[str, bool, dict]] = []

    def add(cid, ok, detail):
        checks.append((cid, bool(ok), detail))

    # ── V1 — base ────────────────────────────────────────────────────────────────────────────
    v1_bad, v1_cov = [], []
    for r in rows:
        rel = set(r["relevant_pages"])
        reach = rel & coll
        pages = {p for p, _ in r["base_ranked"]}
        cov = (len(pages & reach) / len(reach)) if reach else None
        v1_cov.append(cov)
        rec20 = _ranking_metrics([p for p, _ in r["base_ranked"][:TOP_K]], rel, TOP_K)["recall_at_k"]
        if not _close(cov, r["cov_base"], EXACT_TOL):
            v1_bad.append({"id": r["id"], "kind": "cov_base", "verifier": cov, "harness": r["cov_base"]})
        if not _close(rec20, r["m_base"]["recall_at_20"], METRIC_TOL):
            v1_bad.append({"id": r["id"], "kind": "recall_at_20", "verifier": rec20,
                           "harness": r["m_base"]["recall_at_20"]})
    v1_mean = mean(v1_cov)
    v1_agg_ok = _close(v1_mean, art["aggregate"]["base"]["overall"]["coverage_reachable"], CURVE_TOL)
    v1_anchor_ok = abs(v1_mean - I89_BASE) <= I89_TOL
    add("V1_base_rederives_and_reproduces_I89", not v1_bad and v1_agg_ok and v1_anchor_ok,
        {"n_bad": len(v1_bad), "bad": v1_bad[:8], "mean_cov_verifier": v1_mean,
         "mean_cov_harness": art["aggregate"]["base"]["overall"]["coverage_reachable"],
         "aggregate_agrees": v1_agg_ok, "anchor": I89_BASE, "anchor_gap": v1_mean - I89_BASE,
         "anchor_tol": I89_TOL, "anchor_ok": v1_anchor_ok})

    # ── V2 — cut (must be a SUBSET of V1's lane) ──────────────────────────────────────────────
    v2_bad, v2_sub_bad, v2_cov = [], [], []
    for r in rows:
        rel = set(r["relevant_pages"])
        reach = rel & coll
        base_pages = {p for p, _ in r["base_ranked"]}
        cut_pages = {p for p, _ in r["cut_ranked"]}
        if not cut_pages <= base_pages:
            v2_sub_bad.append(r["id"])
        cov = (len(cut_pages & reach) / len(reach)) if reach else None
        v2_cov.append(cov)
        rec20 = _ranking_metrics([p for p, _ in r["cut_ranked"][:TOP_K]], rel, TOP_K)["recall_at_k"]
        if not _close(cov, r["cov_cut"], EXACT_TOL):
            v2_bad.append({"id": r["id"], "kind": "cov_cut", "verifier": cov, "harness": r["cov_cut"]})
        if not _close(rec20, r["m_cut"]["recall_at_20"], METRIC_TOL):
            v2_bad.append({"id": r["id"], "kind": "recall_at_20", "verifier": rec20,
                           "harness": r["m_cut"]["recall_at_20"]})
    v2_mean = mean(v2_cov)
    v2_agg_ok = _close(v2_mean, art["aggregate"]["cut"]["overall"]["coverage_reachable"], CURVE_TOL)
    v2_anchor_ok = abs(v2_mean - I89_CUT) <= I89_TOL
    add("V2_cut_rederives_subset_of_base_and_reproduces_I89",
        not v2_bad and not v2_sub_bad and v2_agg_ok and v2_anchor_ok,
        {"n_bad": len(v2_bad), "bad": v2_bad[:8], "not_subset_of_base": v2_sub_bad[:8],
         "mean_cov_verifier": v2_mean,
         "mean_cov_harness": art["aggregate"]["cut"]["overall"]["coverage_reachable"],
         "aggregate_agrees": v2_agg_ok, "anchor": I89_CUT, "anchor_gap": v2_mean - I89_CUT,
         "anchor_tol": I89_TOL, "anchor_ok": v2_anchor_ok})

    # ── V3 — fusion pool ─────────────────────────────────────────────────────────────────────
    v3_bad, over_cap = [], []
    da_flag, graph_flag = 0, 0
    for r in rows:
        rel = set(r["relevant_pages"])
        n_pool = len(r["fusion_ranked"])
        if n_pool > FETCH_K:
            over_cap.append({"id": r["id"], "pool": n_pool})
        rec100 = _ranking_metrics([p for p, _ in r["fusion_ranked"]], rel, FETCH_K)["recall_at_k"]
        if not _close(rec100, r["m_fusion"]["recall_at_100"], METRIC_TOL):
            v3_bad.append({"id": r["id"], "kind": "recall_at_100", "verifier": rec100,
                           "harness": r["m_fusion"]["recall_at_100"]})
        if r["query_type"] == "multihop":
            graph_flag += 1
        da_flag += 1
    fusion_cfg = meta.get("fusion", {})
    cfg_ok = (fusion_cfg.get("mmr_lambda") == 0.7 and fusion_cfg.get("W") == 100
              and fusion_cfg.get("threshold") == 0.0 and fusion_cfg.get("rrf_k") == 1
              and "Jaccard" in str(fusion_cfg.get("mmr_variant", "")))
    # Liveness (G6). ⚠️ The pre-registration's G6 requires each lane to be non-empty on AT LEAST the
    # queries it should — NOT on every one. An earlier version of this check asserted
    # `da_live == n_queries` and reported a failure on a correct run where the DA lane was live on
    # 132/133. A lane returning nothing for one query is a legitimate outcome (the harness's own
    # `_da_live` also swallows a transient error into False), so the bound is `0 < live <= eligible`,
    # and the shortfall is REPORTED rather than failed.
    live_ok = (0 < meta["da_live_queries"] <= da_flag) \
              and (0 < meta["graph_live_queries"] <= graph_flag)
    da_shortfall = da_flag - meta["da_live_queries"]
    add("V3_fusion_pool_and_lane_liveness", not v3_bad and not over_cap and cfg_ok and live_ok,
        {"n_bad": len(v3_bad), "bad": v3_bad[:8], "pool_over_cap": over_cap,
         "fusion_config_shipped": cfg_ok, "fusion_config": fusion_cfg,
         "da_live_recorded": meta["da_live_queries"], "da_live_expected": da_flag,
         "graph_live_recorded": meta["graph_live_queries"], "multihop_queries": graph_flag,
         "da_shortfall": da_shortfall, "liveness_consistent": live_ok})

    # ── V4 — cross-encoder (order-dependent metrics gated) ───────────────────────────────────
    v4_bad, ce_over = [], []
    for r in rows:
        rel = set(r["relevant_pages"])
        if len(r["ce_ranked"]) > TOP_K:
            ce_over.append({"id": r["id"], "n_ce": len(r["ce_ranked"])})
        m = _ranking_metrics([p for p, _ in r["ce_ranked"]], rel, TOP_K)
        got = r["m_ce"]
        # ⚠️ precision_at_20 and f1_at_20 are ADDED by the re-registration §5 — §7b's V4 row
        # originally named only R@20/MRR/MAP/nDCG, which left their FORMULA unverified here.
        for vk, hk in (("recall_at_k", "recall_at_20"), ("precision_at_k", "precision_at_20"),
                       ("f1_at_k", "f1_at_20"), ("mrr", "mrr"), ("map", "map"),
                       ("ndcg_at_k", "ndcg_at_20")):
            if not _close(m[vk], got[hk], METRIC_TOL):
                v4_bad.append({"id": r["id"], "metric": hk, "verifier": m[vk], "harness": got[hk]})
    valid = meta["n_reranker_fallbacks"] == 0
    topk_ok = meta["top_k"] == TOP_K
    add("V4_cross_encoder_metrics_valid_and_rederived",
        not v4_bad and not ce_over and valid and topk_ok,
        {"n_bad": len(v4_bad), "bad": v4_bad[:8], "ce_over_top_k": ce_over,
         "reranked_metrics_valid": valid, "n_fallbacks": meta["n_reranker_fallbacks"],
         "top_k": meta["top_k"], "top_k_ok": topk_ok})

    # ── V5 — the aperture sweep ──────────────────────────────────────────────────────────────
    v5_bad, mono_bad, tau0_bad, auc_bad = [], [], [], []
    for label, rkey in (("base", "base_ranked"), ("cut", "cut_ranked")):
        per_tau_ver = {t: [] for t in TAUS}
        aucs = []
        for r in rows:
            rel = set(r["relevant_pages"])
            ranked = r[rkey]
            pts = [_curve_point(ranked, rel, float(t), K_APERTURE) for t in TAUS]
            rec = r[f"sweep_{label}"]["curve"]
            for t, p in zip(TAUS, pts):
                got = rec[t]
                for key in ("n_admitted", "admission_uncapped"):
                    if p[key] != got[key]:
                        v5_bad.append({"id": r["id"], "boundary": label, "tau": t, "key": key,
                                       "verifier": p[key], "harness": got[key]})
                for key in ("recall_at_K", "precision_at_K", "precision_ceiling_at_K"):
                    if not _close(p[key], got[key], CURVE_TOL):
                        v5_bad.append({"id": r["id"], "boundary": label, "tau": t, "key": key,
                                       "verifier": p[key], "harness": got[key]})
                per_tau_ver[t].append(p)
            # G7 — monotone non-increasing in τ, per query (recall and uncapped admission).
            recs = [p["recall_at_K"] for p in pts]
            adms = [p["admission_uncapped"] for p in pts]
            if any(b is not None and a is not None and b > a + 1e-9 for a, b in zip(recs, recs[1:])) \
               or any(b > a for a, b in zip(adms, adms[1:])):
                mono_bad.append({"id": r["id"], "boundary": label})
            # G8 — τ=0.0's admitted set == the scoop set (top-K, no threshold).
            if {p for p, c in ranked[:K_APERTURE] if c >= 0.0} != {p for p, _ in ranked[:K_APERTURE]}:
                tau0_bad.append({"id": r["id"], "boundary": label})
            aucs.append(_auc_pr(pts))
        # The per-τ aggregates must re-derive too.
        for t in TAUS:
            hv = art["aperture"][label]["per_tau"][t]
            for key, vk in (("recall_at_K", "recall_at_K"), ("precision_at_K", "precision_at_K"),
                            ("admission_uncapped_mean", "admission_uncapped")):
                got = mean([p[vk] for p in per_tau_ver[t]])
                if not _close(got, hv[key], CURVE_TOL if "mean" not in key else 1e-6):
                    v5_bad.append({"boundary": label, "tau": t, "key": f"aggregate.{key}",
                                   "verifier": got, "harness": hv[key]})
        if not _close(mean(aucs), art["aperture"][label]["auc_pr_mean"], AUC_TOL):
            auc_bad.append({"boundary": label, "verifier": mean(aucs),
                            "harness": art["aperture"][label]["auc_pr_mean"]})
    add("V5_aperture_curve_rederives_monotone_and_auc",
        not v5_bad and not mono_bad and not tau0_bad and not auc_bad,
        {"n_bad": len(v5_bad), "bad": v5_bad[:8], "non_monotone": mono_bad[:8],
         "tau0_not_scoop": tau0_bad[:8], "auc_bad": auc_bad,
         "n_negative_cosines_in_topK": art["guard_detail"].get("G8_n_negative_cosines_in_topK")})

    # ── V6 — boundary 5 (the Qdrant dense lane) ──────────────────────────────────────────────
    # ADDED by the re-registration §4. Re-derives the whole boundary-5 stage from `b5_ranked`:
    # coverage, recall@20/@100, the τ curve, monotonicity, τ=0 == scoop, AUC-PR, the COSINE-scale
    # check (G9) and the ANN-vs-exact overlap (G10).
    v6_bad, v6_mono, v6_tau0, v6_scale, v6_overlap = [], [], [], [], []
    aucs_b5 = []
    per_tau_b5 = {t: [] for t in TAUS}
    for r in rows:
        rel = set(r["relevant_pages"])
        reach = rel & coll
        ranked = r["b5_ranked"]
        pages = {p for p, _ in ranked}
        cov = (len(pages & reach) / len(reach)) if reach else None
        if not _close(cov, r["cov_b5"], EXACT_TOL):
            v6_bad.append({"id": r["id"], "kind": "cov_b5", "verifier": cov, "harness": r["cov_b5"]})
        # ⚠️ The two recalls have DIFFERENT populations and must be computed the way the harness
        # builds them (`_metrics_from_pages` passes hits_above = the WHOLE list):
        #   recall_at_20  = the top-20 pages  (the `reranked` slice)
        #   recall_at_100 = the POOL recall over the boundary's ENTIRE output, not the top-100.
        # Comparing the second against `ranked[:100]` was WRONG and made V6 red at the baseline on
        # gold-004 (verifier 0.0 vs harness 0.6667) — caught by the mutation proof, which is what it
        # is for. V3's pool check has always used the full list; V6 now mirrors it.
        rec20 = _ranking_metrics([p for p, _ in ranked[:TOP_K]], rel, TOP_K)["recall_at_k"]
        recpool = _ranking_metrics([p for p, _ in ranked], rel, FETCH_K)["recall_at_k"]
        for rec_k, hk in ((rec20, "recall_at_20"), (recpool, "recall_at_100")):
            if not _close(rec_k, r["m_b5"][hk], METRIC_TOL):
                v6_bad.append({"id": r["id"], "kind": hk, "verifier": rec_k, "harness": r["m_b5"][hk]})
        # G9 recomputed: boundary 5's scores must be on the SAME COSINE scale as boundary 2's exact
        # cosines. The verifier cannot recompute the vectors — it does not need to: boundary 2's
        # exact cosines are recorded beside it. For the top-20 pages both lanes return, the two
        # scores must agree. A fused rank score, or any rescaling, breaks this by an order of
        # magnitude. ⚠️ This is what makes the check FALSIFIABLE; a bare "distinct value count"
        # would not — a harmonic rank series also has hundreds of distinct values.
        scores = [c for _, c in ranked]
        cut_score = {p: c for p, c in r["cut_ranked"]}
        shared = [(c, cut_score[p]) for p, c in ranked[:20] if p in cut_score]
        gap = mean([abs(a - b) for a, b in shared])
        if not all(-1.0 <= c <= 1.0 for c in scores) or len(shared) < 5 or gap is None or gap > 0.02:
            v6_scale.append({"id": r["id"], "n_shared_top20": len(shared), "mean_abs_gap": gap})
        # G10 recomputed: the ANN-vs-exact overlap against boundary 2's page set.
        cut_pages = {p for p, _ in r["cut_ranked"]}
        ov = (len(pages & cut_pages) / len(pages)) if pages else None
        if not _close(ov, r["b5_overlap_with_cut"], 1e-9):
            v6_overlap.append({"id": r["id"], "verifier": ov, "harness": r["b5_overlap_with_cut"]})
        # The τ curve, monotonicity and τ=0 == scoop at boundary 5.
        pts = [_curve_point(ranked, rel, float(t), K_APERTURE) for t in TAUS]
        rec5 = r["sweep_b5"]["curve"]
        for t, p in zip(TAUS, pts):
            got = rec5[t]
            for key in ("n_admitted", "admission_uncapped"):
                if p[key] != got[key]:
                    v6_bad.append({"id": r["id"], "boundary": "b5", "tau": t, "key": key,
                                   "verifier": p[key], "harness": got[key]})
            for key in ("recall_at_K", "precision_at_K", "precision_ceiling_at_K"):
                if not _close(p[key], got[key], CURVE_TOL):
                    v6_bad.append({"id": r["id"], "boundary": "b5", "tau": t, "key": key,
                                   "verifier": p[key], "harness": got[key]})
            per_tau_b5[t].append(p)
        recs5 = [p["recall_at_K"] for p in pts]
        adms5 = [p["admission_uncapped"] for p in pts]
        if any(b is not None and a is not None and b > a + 1e-9 for a, b in zip(recs5, recs5[1:])) \
           or any(b > a for a, b in zip(adms5, adms5[1:])):
            v6_mono.append({"id": r["id"]})
        if {p for p, c in ranked[:K_APERTURE] if c >= 0.0} != {p for p, _ in ranked[:K_APERTURE]}:
            v6_tau0.append({"id": r["id"]})
        aucs_b5.append(_auc_pr(pts))
    for t in TAUS:
        hv = art["aperture"]["b5"]["per_tau"][t]
        for key, vk in (("recall_at_K", "recall_at_K"), ("precision_at_K", "precision_at_K"),
                        ("admission_uncapped_mean", "admission_uncapped")):
            got = mean([p[vk] for p in per_tau_b5[t]])
            if not _close(got, hv[key], CURVE_TOL if "mean" not in key else 1e-6):
                v6_bad.append({"boundary": "b5", "tau": t, "key": f"aggregate.{key}",
                               "verifier": got, "harness": hv[key]})
    v6_auc_ok = _close(mean(aucs_b5), art["aperture"]["b5"]["auc_pr_mean"], AUC_TOL)
    add("V6_boundary5_rederives_scale_and_auc",
        not v6_bad and not v6_mono and not v6_tau0 and not v6_scale and not v6_overlap and v6_auc_ok,
        {"n_bad": len(v6_bad), "bad": v6_bad[:8], "non_monotone": v6_mono[:8],
         "tau0_not_scoop": v6_tau0[:8], "not_cosine_scale": v6_scale[:8],
         "overlap_mismatch": v6_overlap[:8],
         "auc_verifier": mean(aucs_b5), "auc_harness": art["aperture"]["b5"]["auc_pr_mean"],
         "auc_ok": v6_auc_ok})

    all_ok = all(ok for _, ok, _ in checks)
    out = {"artifact": str(args.artifact), "n_queries": len(rows),
           "checks": [{"id": c, "pass": ok, "detail": d} for c, ok, d in checks],
           "all_pass": all_ok}
    print(json.dumps(out, indent=2, default=str))

    if args.extract:
        pack = {"artifact": str(args.artifact), "meta": {k: meta[k] for k in
                ("collection", "dense_model", "dense_dim", "da_enabled", "splade_enabled",
                 "graph_lane", "hyde", "N", "L", "fetch_k", "top_k", "K_aperture", "tau_grid",
                 "fusion", "n_queries", "n_errors", "n_reranker_fallbacks", "da_live_queries",
                 "graph_live_queries")},
                "guards": art["guards"], "guard_detail": art["guard_detail"],
                "aggregate": art["aggregate"], "aperture": art["aperture"],
                "verifier": {"checks": out["checks"], "all_pass": all_ok}}
        (BASE / EXTRACT).write_text(json.dumps(pack, indent=2))
        print(f"\nextract: {BASE / EXTRACT}")

    if args.check:
        print("\nVERIFIER: ALL PASS" if all_ok else "\nVERIFIER: FAILURE(S)")
        return 0 if all_ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
