#!/usr/bin/env python3
"""Independent stdlib verifier for the router-in-the-loop run (§I116 / prereg 2026-11-05).

Re-derives EVERY aggregate, the paired CI, the confusion matrix and the guards from the artifact's
raw per-query arrays. Importable: ``verify(d) -> list[(name, ok)]`` so the mutation proof can drive
it. Needs no cluster — it reads only the artifact.

Run:  .venv/bin/python logs/p1/step10/router_in_loop_verifier.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / "logs/p1/step10/router_in_loop.json"

F0_R20, F0_NDCG, ANCHOR_TOL = 0.4563, 0.5503, 0.02
METRICS = ("recall_at_20", "ndcg_at_20", "map", "mrr", "hit_at_20", "coverage_reachable")


def _paired(deltas: list[float]) -> dict:
    if len(deltas) < 2:
        return {"n": len(deltas), "mean": None, "ci": None, "resolved": False}
    m = st.mean(deltas)
    half = 1.96 * st.stdev(deltas) / (len(deltas) ** 0.5)
    return {"n": len(deltas), "mean": m, "ci": [m - half, m + half],
            "resolved": (m - half > 0 or m + half < 0),
            "wins": sum(1 for d in deltas if d > 0), "losses": sum(1 for d in deltas if d < 0)}


def verify(d: dict) -> list[tuple[str, bool]]:
    per, meta, agg, deltas = d["per_query"], d["meta"], d["aggregates"], d["deltas"]
    n = len(per)
    c: list[tuple[str, bool]] = []
    add = lambda name, cond: c.append((name, bool(cond)))  # noqa: E731

    def _mean(arm, key):
        v = [r[arm][key] for r in per if r[arm].get(key) is not None]
        return st.mean(v) if v else None

    # V1-V4: population, errors, the two anchors
    add("V1  population is the registered 133", n == 133)
    add("V2  zero errors", len(d.get("errors", [])) == 0)
    add("V3  G3 the router differs from the gold on >=1 query",
        any(r["differs"] for r in per))
    a_r20, a_ndcg = _mean("A", "recall_at_20"), _mean("A", "ndcg_at_20")
    add("V4  G4 arm A reproduces F0 (R@20 0.4563, nDCG 0.5503) within +/-0.02",
        a_r20 is not None and a_ndcg is not None
        and abs(a_r20 - F0_R20) <= ANCHOR_TOL and abs(a_ndcg - F0_NDCG) <= ANCHOR_TOL)

    # V5: aggregates re-derived
    agg_ok = all(agg.get(f"{arm}_{k}") == _mean(arm, k) for arm in ("A", "B") for k in METRICS)
    add("V5  every A_*/B_* aggregate re-derived from per_query", agg_ok)

    # V6: deltas re-derived (mean, CI, resolved)
    deltas_ok = True
    for k in METRICS:
        ds = [r["B"][k] - r["A"][k] for r in per
              if r["A"].get(k) is not None and r["B"].get(k) is not None]
        exp = _paired(ds)
        got = deltas.get(k, {})
        if not (got.get("n") == exp["n"] and got.get("mean") == exp["mean"]
                and got.get("ci") == exp["ci"] and got.get("resolved") == exp["resolved"]):
            deltas_ok = False
    add("V6  every paired delta (n/mean/CI/resolved) re-derived", deltas_ok)

    # V7-V8: confusion + prediction distribution
    conf: dict[str, dict[str, int]] = {}
    for r in per:
        conf.setdefault(r["gold"], {})
        conf[r["gold"]][r["router"]] = conf[r["gold"]].get(r["router"], 0) + 1
    add("V7  confusion matrix re-derived", meta.get("confusion_gold_to_router") == conf)
    dist: dict[str, int] = {}
    for r in per:
        dist[r["router"]] = dist.get(r["router"], 0) + 1
    add("V8  router prediction distribution re-derived",
        meta.get("router_prediction_distribution") == dist)

    # V9-V10: agreement + the differs flag
    add("V9  router_agreement re-derived",
        meta.get("router_agreement") == round(sum(1 for r in per if not r["differs"]) / n, 4))
    add("V10 differs == (gold != router) for every query",
        all(r["differs"] == (r["gold"] != r["router"]) for r in per))

    # V11: G7 the HyDE misses are exactly the expected set
    exp_miss = sum(1 for r in per if r["gold"] not in ("factual", "overview")
                   and r["router"] in ("factual", "overview"))
    add("V11 G7 HyDE misses equal the expected set",
        meta.get("n_hyde_misses") == exp_miss and meta.get("expected_hyde_miss") == exp_miss)

    # V12: every per_query carries both arms' metrics
    add("V12 every per_query carries both arms' metrics",
        all(all(r[a].get(k) is not None for a in ("A", "B") for k in ("recall_at_20", "ndcg_at_20"))
            for r in per))
    return c


def main() -> int:
    if not ART.exists():
        print(f"no artifact at {ART} — the run has not landed (or was blocked). Nothing to verify.")
        return 2
    checks = verify(json.loads(ART.read_text()))
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
    n_ok = sum(1 for _, ok in checks if ok)
    print(f"\n{n_ok}/{len(checks)} checks PASS")
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
