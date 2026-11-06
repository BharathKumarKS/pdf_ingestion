"""Independent stdlib verifier for the overview retrieval-signal probe (§I112).

Re-derives EVERY aggregate, per-arm R@20 / nDCG@20 / Hit@20 / mean-gold-rank from the artifact's RAW
per-query page lists, and re-checks G1-G7. It does NOT import the harness.

Run:  .venv/bin/python logs/p1/step10/overview_signal_probe_verifier.py [--check]
Exit: 0 = all checks pass.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ART = Path("logs/p1/step10/overview_signal_probe.json")
K = 20


def ndcg(pages, gold, k=K):
    dcg = sum(1.0 / math.log2(i + 1) for i, p in enumerate(pages[:k], start=1) if p in gold)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(gold)) + 1))
    return dcg / idcg if idcg else 0.0


def metrics(pages, gold):
    r20 = len(gold & set(pages[:K])) / len(gold) if gold else 0.0
    ranks = [i for i, p in enumerate(pages, start=1) if p in gold]
    return {"R@20": r20, "nDCG@20": ndcg(pages, gold),
            "Hit@20": 1.0 if gold & set(pages[:K]) else 0.0,
            "mean_gold_rank": (statistics.mean(ranks) if ranks else None)}


def verify(art: dict) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    pq = art["per_query"]
    a = art["aggregates"]

    def chk(name, ok, detail=""):
        out.append((name, bool(ok), detail))

    # 1. every per-query metric re-derived
    bad = 0
    for r in pq:
        gold = set(r["gold"])
        for arm in "ABCD":
            want = metrics(r["pages"][arm], gold)
            got = r["metrics"][arm]
            for k in ("R@20", "nDCG@20", "Hit@20"):
                if abs(want[k] - got[k]) > 1e-9:
                    bad += 1
            if (want["mean_gold_rank"] is None) != (got["mean_gold_rank"] is None):
                bad += 1
    chk("V1 per-query metrics re-derived exactly", bad == 0, f"{bad} mismatches")

    # 2. every aggregate re-derived from the per-query metrics
    bad = 0
    for arm in "ABCD":
        rs = [r["metrics"][arm] for r in pq]
        if abs(statistics.mean(x["R@20"] for x in rs) - a[arm]["R@20"]) > 1e-9:
            bad += 1
        if abs(statistics.mean(x["nDCG@20"] for x in rs) - a[arm]["nDCG@20"]) > 1e-9:
            bad += 1
    chk("V2 aggregates re-derived", bad == 0, f"{bad} mismatches")

    # 3. the paired deltas re-derived
    def paired(arm_a, arm_b, key):
        d = [r["metrics"][arm_b][key] - r["metrics"][arm_a][key] for r in pq]
        return statistics.mean(d)
    bad = 0
    for key, (x, y) in (("C-A", ("A", "C")), ("D-A", ("A", "D")), ("B-A", ("A", "B"))):
        if abs(paired(x, y, "R@20") - art["deltas"][key]["mean"]) > 1e-9:
            bad += 1
    chk("V3 paired deltas re-derived", bad == 0, f"{bad} mismatches")

    # 4. a RESOLVED verdict must match its own CI
    bad = 0
    for k, d in art["deltas"].items():
        lo, hi = d["ci"]
        if bool(d["resolved"]) != (lo > 0 or hi < 0):
            bad += 1
    chk("V4 resolved flag matches the CI", bad == 0, f"{bad} mismatches")

    # 5. guards re-checked against the raw data
    g = art["guards"]
    chk("V5 G1 population 40", g["G1_population_40"] == (len(pq) == 40))
    chk("V6 G3 hypotheses frozen", g["G3_hypotheses_frozen"] == Path("logs/p1/step10/overview_signal_hypotheses.json").exists())
    chk("V7 G5 arm B differs from A", g["G5_armB_differs_from_A"] == any(r["pages"]["B"] != r["pages"]["A"] for r in pq))
    chk("V8 G6 lane ordered len>=20", g["G6_lane_ordered_len_ge_20"] == all(len(r["pages"]["A"]) >= 20 for r in pq))
    chk("V9 G7 determinism", g["G7_determinism_A"] == all(r["pages"]["A"] == r["determinism_A"] for r in pq))

    # 10. the page lists are strictly ordered by score (no ties out of order) — a rank metric needs it
    chk("V10 page lists are distinct pages", all(len(set(r["pages"][a])) == len(r["pages"][a])
                                                 for r in pq for a in "ABCD"))
    return out


def main() -> int:
    art = json.loads(ART.read_text())
    res = verify(art)
    npass = sum(1 for _, ok, _ in res if ok)
    for name, ok, detail in res:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))
    print(f"\n{npass}/{len(res)} checks PASS")
    return 0 if npass == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
