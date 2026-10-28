"""Build the query-level CSVs and the aggregate tables for the nomic runs (reporting only, read-only).

Reads the three registered artifacts and writes:
  logs/p1/step10/report_query_level_t0.csv                  — 133 queries x 5 boundaries x all metrics
  logs/p1/step10/report_query_level_t1.csv                  — 133 queries x arm A / arm B x all metrics
  logs/p1/step10/report_query_level_fusion_attribution.csv  — 133 queries x 7 arms x coverage
and prints the aggregate tables in the slide's shape. NO CI, no W/L/T, no floors (as requested).
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

BASE = Path("logs/p1/step10")
METRICS = ["recall_at_20", "recall_at_100", "hit_at_20", "mrr", "ndcg_at_20", "map",
           "context_precision", "precision_at_20", "precision_ceiling_at_20", "f1_at_20"]
TYPES = ("factual", "overview", "multihop")


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else float("nan")


def _fmt(v):
    return "  n/a" if v is None else f"{v:.4f}"


# ── T0 ────────────────────────────────────────────────────────────────────────────────────────────
def t0():
    a = json.loads((BASE / "t0_baseline.json").read_text())
    rows = [r for r in a["per_query"] if "error" not in r]
    bounds = [("base", "m_base", "cov_base"), ("cut", "m_cut", "cov_cut"), ("b5", "m_b5", "cov_b5"),
              ("fusion", "m_fusion", "cov_fusion"), ("ce", "m_ce", "cov_ce")]

    with (BASE / "report_query_level_t0.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        hdr = ["query_id", "query_type", "n_relevant", "n_reachable"]
        for b, mk, ck in bounds:
            hdr += [f"{b}_coverage"] + [f"{b}_{m}" for m in METRICS] + [f"{b}_pool_pages"]
        w.writerow(hdr)
        for r in sorted(rows, key=lambda x: x["id"]):
            line = [r["id"], r["query_type"], r["n_relevant"], r["n_reachable"]]
            for b, mk, ck in bounds:
                mm = r.get(mk, {})
                pages = len({p for p, _ in r.get(f"{b}_ranked", [])})
                line += [r.get(ck)] + [mm.get(m) for m in METRICS] + [pages]
            w.writerow(line)

    print("=" * 118)
    print("T0 — the FULL-FUNNEL nomic baseline (one arm: knowledge_base_v3 / nomic-768 POOLED; DA ON, graph ON)")
    print("   coverage = share of a query's REACHABLE labelled pages present at that boundary; pool = distinct pages")
    print("=" * 118)
    head = f"{'boundary':10s} {'coverage':>8s} {'pool':>6s} {'R@20':>7s} {'R@100':>7s} {'Hit@20':>7s} {'MRR':>7s} {'nDCG@20':>8s} {'MAP':>7s} {'CtxPrec':>8s} {'P@20':>7s} {'Pceil':>7s} {'F1@20':>7s}"
    print(head)
    for b, mk, ck in bounds:
        m = {k: mean(r.get(mk, {}).get(k) for r in rows) for k in METRICS}
        pool = mean(len({p for p, _ in r.get(f"{b}_ranked", [])}) for r in rows)
        print(f"{b:10s} {mean(r.get(ck) for r in rows):8.4f} {pool:6.1f} "
              + " ".join(f"{m[k]:7.4f}" if k in ("recall_at_20", "recall_at_100", "hit_at_20", "mrr", "map", "precision_at_20", "precision_ceiling_at_20", "f1_at_20") else f"{m[k]:8.4f}" if k == "context_precision" else f"{m[k]:8.4f}" if k == "ndcg_at_20" else "" for k in METRICS))
    print()
    print("T0 per query type (R@20 / R@100 / nDCG@20 / MAP / coverage):")
    print(f"  {'type':9s} {'n':>4s} " + " ".join(f"{x:>10s}" for x in ("R@20", "R@100", "nDCG@20", "MAP", "coverage")))
    for qt in TYPES:
        sub = [r for r in rows if r["query_type"] == qt]
        print(f"  {qt:9s} {len(sub):4d} "
              f"{mean(r['m_ce'].get('recall_at_20') for r in sub):10.4f} "
              f"{mean(r['m_ce'].get('recall_at_100') for r in sub):10.4f} "
              f"{mean(r['m_ce'].get('ndcg_at_20') for r in sub):10.4f} "
              f"{mean(r['m_ce'].get('map') for r in sub):10.4f} "
              f"{mean(r.get('cov_ce') for r in sub):10.4f}")
    print()
    print("T0 per query type at EACH boundary — coverage / R@20 / nDCG@20:")
    for b, mk, ck in bounds:
        print(f"  {b:8s} " + " | ".join(
            f"{qt}: cov {mean(r.get(ck) for r in rows if r['query_type']==qt):.4f} "
            f"R@20 {mean(r.get(mk,{}).get('recall_at_20') for r in rows if r['query_type']==qt):.4f} "
            f"nDCG {mean(r.get(mk,{}).get('ndcg_at_20') for r in rows if r['query_type']==qt):.4f}"
            for qt in TYPES))
    return rows


# ── T1 ────────────────────────────────────────────────────────────────────────────────────────────
def t1():
    arms = {k: json.loads((BASE / f"t1_arm_{k}.json").read_text()) for k in ("A1", "B1")}
    S = {k: {r["id"]: r for r in v["per_query"] if "error" not in r} for k, v in arms.items()}
    ids = sorted(S["A1"])

    with (BASE / "report_query_level_t1.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["query_id", "query_type", "n_relevant", "n_reachable"]
                   + [f"A_{m}" for m in METRICS] + [f"B_{m}" for m in METRICS]
                   + ["A_pool_size", "B_pool_size"])
        for q in ids:
            a, b = S["A1"][q], S["B1"][q]
            w.writerow([q, a["query_type"], a["n_relevant"], a.get("n_relevant_reachable")]
                       + [a["metrics"].get(m) for m in METRICS]
                       + [b["metrics"].get(m) for m in METRICS]
                       + [a["pool_size"], b["pool_size"]])

    print("=" * 118)
    print("T1 — the BASE-LANE ship test (arm A = knowledge_base_v2 / qwen3-1024; arm B = knowledge_base_v3 / nomic-768 POOLED)")
    print("   ⚠️ DA lane OFF and GRAPH lane OFF in BOTH arms; HyDE ON; the product's own metric function; page-deduped")
    print("=" * 118)
    print(f"{'arm':34s} " + " ".join(f"{m:>10s}" for m in METRICS))
    for lab, k in (("A — qwen3-1024 / v2 (incumbent)", "A1"), ("B — nomic-768 pooled / v3", "B1")):
        print(f"{lab:34s} " + " ".join(f"{mean(r['metrics'].get(m) for r in S[k].values()):10.4f}" for m in METRICS))
    print()
    print(f"{'arm':34s} " + " ".join(f"{qt:>10s}" for qt in TYPES) + "   (R@20 by query type)")
    for lab, k in (("A — qwen3-1024 / v2", "A1"), ("B — nomic-768 pooled / v3", "B1")):
        print(f"{lab:34s} " + " ".join(
            f"{mean(r['metrics'].get('recall_at_20') for r in S[k].values() if r['query_type']==qt):10.4f}"
            for qt in TYPES))
    print()
    print("per query type, BOTH arms — n / R@20 / R@100 / nDCG@20 / MAP / MRR / Hit@20:")
    for qt in TYPES:
        for lab, k in (("A", "A1"), ("B", "B1")):
            sub = [r for r in S[k].values() if r["query_type"] == qt]
            print(f"  {qt:9s} {lab} n={len(sub):3d} " + " ".join(
                f"{mean(r['metrics'].get(m) for r in sub):.4f}"
                for m in ("recall_at_20", "recall_at_100", "ndcg_at_20", "map", "mrr", "hit_at_20")))
    return S


# ── fusion attribution ────────────────────────────────────────────────────────────────────────────
def attrib():
    a = json.loads((BASE / "fusion_attribution.json").read_text())
    rows = [r for r in a["per_query"] if "error" not in r]
    arms = ["C", "C_nommr", "W500", "W500_nommr", "D100", "D100_raw", "D500_raw"]

    with (BASE / "report_query_level_fusion_attribution.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["query_id", "query_type", "n_relevant", "n_reachable"]
                   + [f"{x}_coverage" for x in arms] + [f"{x}_pool_size" for x in arms]
                   + [f"{x}_n_pages" for x in arms])
        for r in sorted(rows, key=lambda x: x["id"]):
            w.writerow([r["id"], r["query_type"], r["n_relevant"], r["n_reachable"]]
                       + [r.get(f"{x}_cov") for x in arms] + [r.get(f"{x}_pool_size") for x in arms]
                       + [len(r.get(f"{x}_pages", [])) for x in arms])

    print("=" * 118)
    print("THE FUSION ATTRIBUTION (one index: knowledge_base_v3 / nomic-768 POOLED; DA ON, graph ON — T0's lane set)")
    print("   unit = coverage of a query's REACHABLE labelled pages; ⚠️ NO fixed-k metric was recorded in this run")
    print("=" * 118)
    labels = {
        "C": "C  the product as shipped (cap 100, MMR on)",
        "C_nommr": "C_nommr  cap 100, MMR OFF",
        "W500": "W500  cap 500 (both knobs), MMR on",
        "W500_nommr": "W500_nommr  cap 500, MMR OFF",
        "D100": "D100  dense lane alone @100, arm C's own vector",
        "D100_raw": "D100_raw  dense lane alone @100, raw vector",
        "D500_raw": "D500_raw  dense lane alone @500, raw vector (= T0 b5)",
    }
    print(f"{'arm':50s} {'coverage':>9s} {'pool':>7s} " + " ".join(f"{qt:>10s}" for qt in TYPES))
    for x in arms:
        print(f"{labels[x]:50s} {a['aggregate'][x]['overall']['coverage']:9.4f} "
              f"{a['aggregate'][x]['overall']['pool_mean']:7.1f} "
              + " ".join(f"{a['aggregate'][x]['by_type'][qt]['coverage']:10.4f}" for qt in TYPES))
    return rows


if __name__ == "__main__":
    t0()
    print()
    t1()
    print()
    attrib()
    print()
    for f in ("report_query_level_t0.csv", "report_query_level_t1.csv",
              "report_query_level_fusion_attribution.csv"):
        p = BASE / f
        print(f"{p}  ({p.stat().st_size:,} bytes, {sum(1 for _ in p.open())} lines)")
