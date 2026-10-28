"""Independent verifier for T1 — re-derives every aggregate from the RAW per-query arrays.

Independently written (stdlib only: no numpy, no project imports, no shared helpers with the harness)
so a bug in the harness's aggregation cannot hide in its own check. It reads ONLY the written JSON.

    uv run python logs/p1/step10/t1_verifier.py --check
    uv run python logs/p1/step10/t1_verifier.py --extract        # compact pack for a reviewer
    uv run python logs/p1/step10/t1_verifier.py --check --base <dir>   # for the mutation proof

Checks (each must be able to fail):
  V1  every arm has 133 scored rows and 0 errored rows
  V2  the per-arm mean R@20 / R@100 / Hit@20 / MRR / NDCG@20 re-derive from the per-query arrays
  V3  the paired P2 (raw R@20) delta, CI, W/L/T re-derive from the per-query arrays
  V4  the paired P1 (cR@20) delta re-derives using the §I58 global divisor
  V5  the negative control (A1 vs A2, B1 vs B2) is BIT-EXACT on every metric of every query
  V6  E8 — arm A's aggregate R@20 is within ±0.020 of the §3d registered anchor (0.452)
  V7  no query is silently excluded from a denominator (no None metrics in a scored row)
  V8  the achievable-max divisor is identical across arms
  V9  E9 — arm A is BIT-EXACT against Stage F's recorded arm A on the six endpoint metrics
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

BASE = Path("logs/p1/step10")
E8_TARGET = 0.452
E8_TOL = 0.020
METRIC_KEYS = ("recall_at_100", "recall_at_20", "hit_at_20", "context_precision", "mrr", "ndcg_at_20")
E9_METRIC_KEYS = ("recall_at_20", "recall_at_100", "hit_at_20", "mrr", "context_precision", "ndcg_at_20")
STAGE_F_ARM_A = "stageF_arm_A1.json"


def mean(xs):
    # None values are SKIPPED, not treated as 0: a None metric is a silent exclusion (V7's subject) and
    # averaging it in as 0 would hide it. `ci()` below deliberately does NOT skip — a paired difference
    # with a None operand is dropped before it is built.
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def ci(diffs):
    n = len(diffs)
    m = mean(diffs)
    sd = math.sqrt(sum((d - m) ** 2 for d in diffs) / (n - 1))
    half = 1.96 * sd / math.sqrt(n)
    return [m - half, m + half], sd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--base", default=str(BASE))
    args = ap.parse_args()

    base = Path(args.base)

    def load(p):
        return json.loads((base / p).read_text())

    art = load("t1_base_lanes.json")
    arms = {k: load(f"t1_arm_{k}.json") for k in ("A1", "A2", "B1", "B2")}
    S = {k: {r["id"]: r for r in v["per_query"] if "error" not in r} for k, v in arms.items()}

    checks = []
    r20_of = lambda r: r["metrics"].get("recall_at_20")  # noqa: E731

    # V1 — 133 scored, 0 errored, per arm.
    v1 = all(len(S[k]) == 133 and len(arms[k]["errors"]) == 0 for k in S)
    checks.append(("V1_133_scored_0_errors", v1,
                   {k: (len(S[k]), len(arms[k]["errors"])) for k in S}))

    # V2 — per-arm means re-derive from the per-query array, against the value the artifact RECORDED
    # in meta (E5). A genuine round-trip: recompute from the rows, compare to the stored summary.
    v2 = True
    v2d = {}
    for arm_letter, arm_key in (("A", "A1"), ("B", "B1")):
        rederived = mean(r20_of(r) for r in S[arm_key].values())
        stored = art["meta"]["mean_r20"][arm_letter]
        v2d[arm_letter] = {"rederived": rederived, "stored": stored}
        if stored is None or abs(stored - rederived) > 1e-12:
            v2 = False
    # the per-arm summary block is re-derived too (R@100 / Hit@20 / MRR / NDCG@20 of arm A)
    a_agg = art["diagnostics"]["E8_arm_A_aggregate"]
    for mk, art_key in (("recall_at_100", "recall_at_100"), ("hit_at_20", "hit_at_20"),
                        ("mrr", "mrr"), ("ndcg_at_20", "ndcg_at_20")):
        red = mean(r["metrics"].get(mk) for r in S["A1"].values())
        v2d[f"A_{mk}"] = {"rederived": red, "stored": a_agg.get(art_key)}
        if a_agg.get(art_key) is None or abs(red - a_agg[art_key]) > 1e-12:
            v2 = False
    checks.append(("V2_means_rederive", v2, v2d))

    # V3 — P2 (raw R@20) paired delta / CI / W-L-T re-derive.
    def paired(a, b, key):
        diffs = []
        for qid in sorted(set(a) & set(b)):
            va, vb = key(a[qid]), key(b[qid])
            if va is None or vb is None:
                continue
            diffs.append(vb - va)
        (lo, hi), sd = ci(diffs)
        return {"n": len(diffs), "mean": mean(diffs), "ci": [lo, hi],
                "wins": sum(1 for d in diffs if d > 0),
                "losses": sum(1 for d in diffs if d < 0),
                "ties": sum(1 for d in diffs if d == 0)}

    p2 = paired(S["A1"], S["B1"], r20_of)
    art_p2 = art["endpoints"]["P2_R20_raw"]
    v3 = (p2["n"] == art_p2["n"] and abs(p2["mean"] - art_p2["mean_delta"]) < 1e-12
          and abs(p2["ci"][0] - art_p2["ci"][0]) < 1e-12
          and (p2["wins"], p2["losses"], p2["ties"]) == (art_p2["wins"], art_p2["losses"], art_p2["ties"]))
    checks.append(("V3_P2_rederives", v3, p2))

    # V4 — P1 (cR@20) re-derives using the §I58 global divisor.
    D = mean(r["achievable_max"] for r in S["A1"].values())
    p1 = paired(S["A1"], S["B1"], lambda r: (r20_of(r) / D) if r20_of(r) is not None else None)
    art_p1 = art["endpoints"]["P1_cR20"]
    v4 = (p1["n"] == art_p1["n"] and abs(p1["mean"] - art_p1["mean_delta"]) < 1e-9
          and abs(p1["ci"][0] - art_p1["ci"][0]) < 1e-9)
    checks.append(("V4_P1_rederives", v4, {"divisor": D, "p1_mean": p1["mean"],
                                           "art_p1_mean": art_p1["mean_delta"]}))

    # V5 — negative control: bit-exact on EVERY metric of EVERY query.
    def bit_exact(x, y):
        return [qid for qid in sorted(set(x) & set(y)) if x[qid]["metrics"] != y[qid]["metrics"]]
    a_mm, b_mm = bit_exact(S["A1"], S["A2"]), bit_exact(S["B1"], S["B2"])
    checks.append(("V5_negative_control_bit_exact", not a_mm and not b_mm,
                   {"A1_vs_A2_mismatches": a_mm, "B1_vs_B2_mismatches": b_mm}))

    # V6 — E8: arm A's aggregate R@20 within ±0.020 of the §3d anchor.
    a_r20 = mean(r20_of(r) for r in S["A1"].values())
    v6 = abs(a_r20 - E8_TARGET) <= E8_TOL
    checks.append(("V6_E8_reproduces_section_3d", v6,
                   {"arm_A_r20": a_r20, "target": E8_TARGET, "gap": a_r20 - E8_TARGET,
                    "tol": E8_TOL}))

    # V7 — no silently excluded denominator: every scored row has all six metrics non-None.
    v7_bad = [qid for qid, r in S["A1"].items() if any(r["metrics"].get(mk) is None for mk in METRIC_KEYS)]
    v7_bad += [qid for qid, r in S["B1"].items() if any(r["metrics"].get(mk) is None for mk in METRIC_KEYS)]
    checks.append(("V7_no_silent_exclusions", not v7_bad, {"rows_with_None_metric": v7_bad}))

    # V8 — the achievable-max divisor is identical across arms.
    D_B = mean(r["achievable_max"] for r in S["B1"].values())
    checks.append(("V8_divisor_identical_across_arms", abs(D - D_B) < 1e-12, {"D_A": D, "D_B": D_B}))

    # V9 — E9: arm A bit-exact against Stage F's recorded arm A on the six endpoint metrics.
    sf = load(STAGE_F_ARM_A)
    sf_a = {r["id"]: r for r in sf["per_query"] if "error" not in r}
    e9_bad = []
    for qid in sorted(set(S["A1"]) & set(sf_a)):
        got = {k: S["A1"][qid]["metrics"].get(k) for k in E9_METRIC_KEYS}
        want = {k: sf_a[qid]["metrics"].get(k) for k in E9_METRIC_KEYS}
        if got != want:
            e9_bad.append(qid)
    v9 = (len(set(S["A1"]) & set(sf_a)) == 133 and not e9_bad)
    checks.append(("V9_E9_arm_A_bit_exact_vs_stageF", v9,
                   {"n_compared": len(set(S["A1"]) & set(sf_a)), "mismatch_ids": e9_bad[:10],
                    "n_mismatch": len(e9_bad)}))

    allok = all(ok for _, ok, _ in checks)
    out = {"checks": [{"id": c, "pass": ok, "detail": d} for c, ok, d in checks], "all_pass": allok}
    print(json.dumps(out, indent=2, default=str))

    if args.extract:
        pack = {
            "artifact_meta": {k: v for k, v in art["meta"].items() if k != "arms"},
            "endpoints": art["endpoints"],
            "guards": art["guards"],
            "power": art["power"], "verdict": art["verdict"],
            "diagnostics": {k: v for k, v in art["diagnostics"].items() if "head" not in k},
            "arm_A_per_query_r20": {qid: r20_of(r) for qid, r in sorted(S["A1"].items())},
            "arm_B_per_query_r20": {qid: r20_of(r) for qid, r in sorted(S["B1"].items())},
            "verifier": out,
        }
        (base / "t1_verifier_extract.json").write_text(json.dumps(pack, indent=2))
        print(f"\nextract → {base / 't1_verifier_extract.json'}")

    if args.check:
        print("\nVERIFIER: ALL PASS" if allok else "\nVERIFIER: FAILURE(S)")
        return 0 if allok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
