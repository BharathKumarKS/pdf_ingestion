"""T4 verifier — INDEPENDENT, stdlib only, reads ONLY the written artifact and T0's.

Pre-registration §7. It does not import the harness and shares no code with it. Its job is to re-derive
every number T4 reports from the **raw per-query page lists and labels**, and to re-run all seven guards.

⚠️ THE CENTRAL IDEA: the artifact stores, per query per arm, the ENDPOINT PAGE LIST (`{arm}_pages`) and the
LABELS (`relevant_pages`). Every metric T4 reports is a function of exactly those two things, so the
verifier recomputes ALL of them — recall, precision, precision-ceiling, f1, nDCG, MAP, hit, and the
endpoint MRR — from scratch, and compares. It never trusts a recorded metric.

The two things it CANNOT recompute from the artifact are (a) the reachable-pages SET, which it takes from
T0's `meta.coll_pages` and cross-checks per query against T0's `n_reachable`, and (b) the product's POOL
`mrr`, which needs the pool list. For (b) it instead asserts the property §I95 claims: the pool `mrr` is
IDENTICAL across arms C, N and Q — i.e. it is a pool metric and cannot answer a ranking question.

Usage:  python logs/p1/step10/t4_verifier.py [--check]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ART = Path("logs/p1/step10/t4_endpoint.json")
T0 = Path("logs/p1/step10/t0_baseline.json")
ANCHOR_TOL = 1e-4
FAIL: list[str] = []
NOTE: list[str] = []


def bad(msg: str) -> None:
    FAIL.append(msg)


def metrics_from_pages(pages: list[int], rel: set[int], k: int) -> dict:
    """Re-derive the product's metric set from a page list — written from the definition, not imported."""
    gains = [1 if p in rel else 0 for p in pages]          # `pages` is page-deduped, so no repeats
    hits = sum(gains)
    n = len(rel)
    recall = (hits / n) if n else None
    precision = (hits / k) if k else None
    ceiling = (min(n, k) / k) if k else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else 0.0
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n, k)))
    ndcg = dcg / idcg if idcg > 0 else 0.0
    ap = 0.0
    if n:
        running = 0
        for i, g in enumerate(gains, start=1):
            if g:
                running += 1
                ap += running / i
        ap /= n
    mrr = 0.0
    for rank, p in enumerate(pages, start=1):
        if p in rel:
            mrr = 1.0 / rank
            break
    r4 = lambda x: round(x, 4) if x is not None else None      # noqa: E731
    return {f"recall_at_{k}": r4(recall), f"precision_at_{k}": r4(precision),
            f"precision_ceiling_at_{k}": r4(ceiling), f"f1_at_{k}": r4(f1),
            f"ndcg_at_{k}": r4(ndcg), f"hit_at_{k}": 1.0 if hits > 0 else 0.0,
            f"mrr_at_{k}": r4(mrr), "map": r4(ap) if n else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--art", default=str(ART))
    args = ap.parse_args()

    art = json.loads(Path(args.art).read_text())
    t0 = json.loads(T0.read_text())
    t0q = {r["id"]: r for r in t0["per_query"] if "error" not in r}
    reach = {int(p) for p in t0["meta"]["coll_pages"]}
    arms = art["meta"]["arms"]
    rows = [r for r in art["per_query"] if "error" not in r]
    K = {a: arms[a]["reranker_top_k"] for a in arms}

    # ── 1. every metric, re-derived from the page lists and labels ────────────────────────────────
    n_metric_checks = 0
    for r in rows:
        rel = set(r["relevant_pages"])
        for a in arms:
            want = metrics_from_pages(r[f"{a}_pages"], rel, K[a])
            got = r[f"{a}_metrics"]
            for key, w in want.items():
                n_metric_checks += 1
                if got.get(key) != w:
                    bad(f"{r['id']}.{a}.{key}: recorded {got.get(key)} != re-derived {w}")
            # coverage — ⚠️ the unit is §I66's: the share of the query's REACHABLE LABELLED pages
            # returned (|pages ∩ (rel ∩ reach)| / |rel ∩ reach|), NOT the corpus-wide share. The
            # denominator is per query, which is why it is 0.0/1.0 on 1-3-label queries.
            rq = rel & reach
            cov = (len(set(r[f"{a}_pages"]) & rq) / len(rq)) if rq else None
            n_metric_checks += 1
            if r.get(f"{a}_cov") != cov:
                bad(f"{r['id']}.{a}.coverage: recorded {r.get(f'{a}_cov')} != re-derived {cov}")
            n_metric_checks += 1
            if r.get("n_reachable") != len(rq):
                bad(f"{r['id']}: n_reachable {r.get('n_reachable')} != |rel ∩ reach| {len(rq)}")
            # pool size
            n_metric_checks += 1
            if r[f"{a}_pool_size"] < len(r[f"{a}_pages"]):
                bad(f"{r['id']}.{a}: pool smaller than the endpoint list")

    # ── 2. the aggregates, recomputed ─────────────────────────────────────────────────────────────
    for a in arms:
        for key in [f"recall_at_{K[a]}", f"precision_at_{K[a]}", f"precision_ceiling_at_{K[a]}",
                    f"f1_at_{K[a]}", f"ndcg_at_{K[a]}", f"hit_at_{K[a]}", f"mrr_at_{K[a]}", "map"]:
            vals = [r[f"{a}_metrics"][key] for r in rows if r[f"{a}_metrics"].get(key) is not None]
            want = statistics.mean(vals) if vals else None
            got = art["aggregate"][a]["overall"].get(key)
            if got is None or want is None or abs(got - want) > 1e-9:
                bad(f"aggregate.{a}.{key}: artifact {got} != recomputed {want}")
        covs = [r[f"{a}_cov"] for r in rows]
        if abs(art["aggregate"][a]["overall"]["coverage_reachable"] - statistics.mean(covs)) > 1e-9:
            bad(f"aggregate.{a}.coverage mismatch")

    # ── 3. G1 / G2 — the two exact anchors ────────────────────────────────────────────────────────
    EP = ("recall_at_20", "precision_at_20", "f1_at_20", "ndcg_at_20", "map", "hit_at_20", "mrr_at_20")
    # ⚠️ T0's `ce` row names its ENDPOINT MRR `mrr` (its own list is both hits and reranked). Ours is
    # `mrr_at_20`. Same quantity, different key — mapped here, not silently skipped.
    T0_KEY = {"mrr_at_20": "mrr"}
    for field, t0row, arm in (("G1", t0["aggregate"]["ce"]["overall"], "C"),
                              ("G2", t0["aggregate"]["fusion"]["overall"], "N")):
        for key in EP + ("coverage_reachable",):
            got = art["aggregate"][arm]["overall"].get(key)
            want = t0row.get(T0_KEY.get(key, key))
            if got is None or want is None or abs(got - want) > ANCHOR_TOL:
                bad(f"{field}: arm {arm} {key}: {got} != T0 {want}")
        if field == "G2":     # the two POOL fields, valid only where the pool is T0's fusion pool
            for key in ("mrr", "recall_at_100"):
                got = art["aggregate"]["N"]["overall"].get(key)
                if got is None or t0row.get(key) is None or abs(got - t0row[key]) > ANCHOR_TOL:
                    bad(f"G2: arm N {key}: {got} != T0 {t0row.get(key)}")

    # ── 4. G3–G7, recomputed from the per-query arrays ────────────────────────────────────────────
    if not (len(rows) == art["meta"]["n_queries"] and not art["errors"]):
        bad(f"G3: {len(rows)} scored / {len(art['errors'])} errors")
    c2 = [r["id"] for r in rows if r.get("C2_pages") != r.get("C_pages")]
    if c2:
        bad(f"G4: arm C not bit-exact on the repeat: {c2[:5]}")
    qd = [r["id"] for r in rows if r.get("Q_pages") != r.get("C_pages")]
    if not qd:
        bad("G5: arm Q's instrumentation did NOT take effect — Q is a copy of C")
    else:
        NOTE.append(f"G5: arm Q differs from C on {len(qd)}/{len(rows)} queries")
    for a in ("N", "Q"):
        mm = [r["id"] for r in rows if r[f"{a}_pool_size"] != r["C_pool_size"]]
        if mm:
            bad(f"G6: arm {a} pool differs from C on {len(mm)} queries")
    # G7 — the denominator, per query, against T0's own n_reachable
    g7 = [r["id"] for r in rows if r.get("n_reachable") != t0q.get(r["id"], {}).get("n_reachable")]
    if g7:
        bad(f"G7: n_reachable differs from T0 on {len(g7)} queries: {g7[:5]}")

    # ── 5. the deltas, recomputed ─────────────────────────────────────────────────────────────────
    def ci(ds: list[float]) -> dict:
        n = len(ds)
        if n < 2:
            return {"n": n, "mean": statistics.mean(ds) if ds else None, "sd": None, "ci95": None}
        m, sd = statistics.mean(ds), statistics.stdev(ds)
        h = 1.96 * sd / math.sqrt(n)
        return {"n": n, "mean": m, "sd": sd, "ci95": [m - h, m + h]}

    for name, (a1, a2) in (("P1_N_minus_C", ("C", "N")), ("P2_Q_minus_C", ("C", "Q"))):
        for key in ("ndcg_at_20", "map", "mrr_at_20", "recall_at_20", "hit_at_20"):
            ds = [r[f"{a2}_metrics"][key] - r[f"{a1}_metrics"][key] for r in rows
                  if r[f"{a1}_metrics"].get(key) is not None and r[f"{a2}_metrics"].get(key) is not None]
            want = ci(ds)
            got = art["deltas"][name][key]
            if abs((got["mean"] or 0) - (want["mean"] or 0)) > 1e-9 or got["n"] != want["n"]:
                bad(f"deltas.{name}.{key}: artifact {got['mean']} != recomputed {want['mean']}")
    ds = [r["W50_cov"] - r["C_cov"] for r in rows]
    if abs((art["deltas"]["P3_W50_cov_minus_C_cov"]["mean"] or 0) - (ci(ds)["mean"] or 0)) > 1e-9:
        bad("deltas.P3 mismatch")

    # ── 6. §I95 — the pool `mrr` must be IDENTICAL across arms (it is a pool metric) ──────────────
    for key in ("mrr",):
        vals = {a: art["aggregate"][a]["overall"].get(key) for a in ("C", "N", "Q")}
        if len(set(vals.values())) != 1:
            bad(f"§I95: the pool `{key}` is NOT identical across arms: {vals}")
        else:
            NOTE.append(f"§I95 confirmed: the pool `{key}` = {list(vals.values())[0]} in C, N and Q — "
                        f"a pool metric cannot answer a ranking question")

    # ── report ────────────────────────────────────────────────────────────────────────────────────
    print(f"artifact      : {args.art}")
    print(f"queries scored: {len(rows)}   errors: {len(art['errors'])}")
    print(f"metric fields re-derived and compared: {n_metric_checks}")
    for n in NOTE:
        print(f"  note: {n}")
    if FAIL:
        print(f"\n*** {len(FAIL)} VERIFICATION FAILURES ***")
        for f in FAIL[:40]:
            print("  -", f)
        if len(FAIL) > 40:
            print(f"  ... and {len(FAIL) - 40} more")
        return 1
    print("\nVERIFIER: ALL CHECKS PASS — every metric, aggregate, delta and guard re-derived independently")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
