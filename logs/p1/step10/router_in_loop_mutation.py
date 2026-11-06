#!/usr/bin/env python3
"""Mutation proof for the router-in-the-loop verifier — every check reddened by >=1 mutation.

⚠️ The full run is BLOCKED on the cluster (sparse/colbert/rerank down, 2026-11-05), so no real
artifact exists yet. This drives the verifier with a **synthetic fixture** shaped like the real
artifact to prove the checks discriminate; re-run it against the real artifact when the run lands.

Run:  .venv/bin/python logs/p1/step10/router_in_loop_mutation.py
"""
from __future__ import annotations

import copy
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from router_in_loop_verifier import METRICS, _paired, verify  # noqa: E402

ART = HERE / "router_in_loop.json"


def _fixture() -> dict:
    """A minimal but internally-consistent artifact: A reproduces F0, B differs per query."""
    pairs = [("factual", "factual"), ("factual", "multihop"), ("multihop", "multihop"),
             ("multihop", "overview"), ("overview", "overview"), ("overview", "multihop")]
    per = []
    for i in range(133):
        g, r = pairs[i % len(pairs)]
        A = {"recall_at_20": 0.4563, "ndcg_at_20": 0.5503, "map": 0.34, "mrr": 0.77,
             "hit_at_20": 0.93, "coverage_reachable": 0.46}
        B = dict(A, recall_at_20=round(0.4563 - 0.001 * (i % 20), 4),
                 ndcg_at_20=round(0.5503 - 0.001 * (i % 20), 4))
        per.append({"id": f"q{i:03d}", "gold": g, "router": r, "differs": g != r, "A": A, "B": B})

    def mean(arm, key):
        v = [x[arm][key] for x in per if x[arm].get(key) is not None]
        return st.mean(v) if v else None

    agg = {f"{a}_{k}": mean(a, k) for a in ("A", "B") for k in METRICS}
    deltas = {k: _paired([x["B"][k] - x["A"][k] for x in per
                          if x["A"].get(k) is not None and x["B"].get(k) is not None]) for k in METRICS}
    conf: dict[str, dict[str, int]] = {}
    for x in per:
        conf.setdefault(x["gold"], {})
        conf[x["gold"]][x["router"]] = conf[x["gold"]].get(x["router"], 0) + 1
    dist: dict[str, int] = {}
    for x in per:
        dist[x["router"]] = dist.get(x["router"], 0) + 1
    exp_miss = sum(1 for x in per if x["gold"] not in ("factual", "overview")
                   and x["router"] in ("factual", "overview"))
    return {"meta": {"n_queries": len(per), "router_agreement":
                     round(sum(1 for x in per if not x["differs"]) / len(per), 4),
                     "router_prediction_distribution": dist, "confusion_gold_to_router": conf,
                     "n_hyde_misses": exp_miss, "expected_hyde_miss": exp_miss},
            "aggregates": agg, "deltas": deltas, "guards": {}, "errors": [], "per_query": per}


def main() -> int:
    base = json.loads(ART.read_text()) if ART.exists() else _fixture()
    src = "real artifact" if ART.exists() else "SYNTHETIC fixture (run is blocked)"
    baseline = dict(verify(base))
    if not all(baseline.values()):
        print("BASELINE NOT GREEN:", [k for k, v in baseline.items() if not v])
        return 1
    print(f"baseline green on the {src}\n")

    def m(path, val):
        d = copy.deepcopy(base)
        cur = d
        for k in path[:-1]:
            cur = cur[k]
        cur[path[-1]] = val
        return d

    mutations = {
        "MV01 n_queries +1": m(["meta", "n_queries"], 999),
        "MV02 an error row added": m(["errors"], [{"id": "x", "error": "boom"}]),
        "MV03 differs all False (identity by construction)":
            {**copy.deepcopy(base), "per_query": [dict(x, differs=False) for x in base["per_query"]]},
        "MV04 arm A R@20 moved off F0": m(["aggregates", "A_recall_at_20"], 0.30),
        "MV05 an aggregate falsified": m(["aggregates", "B_ndcg_at_20"], 0.999),
        "MV06 a delta mean falsified": m(["deltas", "recall_at_20", "mean"], 0.5),
        "MV07 a delta CI falsified": m(["deltas", "ndcg_at_20", "ci"], [0.0, 0.0]),
        "MV08 a delta resolved flag flipped": m(["deltas", "map", "resolved"],
                                                not base["deltas"]["map"]["resolved"]),
        "MV09 confusion matrix falsified": m(["meta", "confusion_gold_to_router"], {"x": {"y": 1}}),
        "MV10 prediction distribution falsified": m(["meta", "router_prediction_distribution"], {"x": 1}),
        "MV11 router_agreement falsified": m(["meta", "router_agreement"], 0.0),
        "MV12 a differs flag desynced from gold/router": m(["per_query", 0, "differs"],
                                                           not base["per_query"][0]["differs"]),
        "MV13 hyde-miss count falsified": m(["meta", "n_hyde_misses"], 999),
        "MV14 an arm metric nulled": m(["per_query", 0, "B", "recall_at_20"], None),
        "MV15 a per_query entry dropped (population != 133)":
            {**copy.deepcopy(base), "per_query": base["per_query"][:-1]},
        "MV16 arm A's per-query R@20 moved off F0 (bulk)":
            {**copy.deepcopy(base), "per_query": [
                {**x, "A": {**x["A"], "recall_at_20": 0.10}} for x in base["per_query"]]},
    }

    reddened = {k: 0 for k in baseline}
    for label, d in mutations.items():
        red = [k for k, ok in verify(d) if not ok]
        for k in red:
            reddened[k] += 1
        print(f"  {label:<48} -> reddened {len(red)}: {', '.join(s.split()[0] for s in red) or 'NONE'}")

    inert = [k for k, v in reddened.items() if v == 0]
    print(f"\nchecks reddened by >=1 mutation: {sum(1 for v in reddened.values() if v)}/{len(reddened)}")
    if inert:
        print("INERT CHECK(S):", inert)
        return 1
    print("MUTATION PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
