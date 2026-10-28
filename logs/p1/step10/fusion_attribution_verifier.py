"""Independent verifier for the fusion attribution — re-derives everything from the RAW per-query arrays.

Independently written (stdlib only: no numpy, no project imports, no shared helpers with the harness) so
a bug in the harness's aggregation cannot hide in its own check. It reads ONLY the written JSON.

    uv run python logs/p1/step10/fusion_attribution_verifier.py --check
    uv run python logs/p1/step10/fusion_attribution_verifier.py --check --artifact <path>   # mutations

Checks (each must be able to fail):
  V1  every arm scored 133 rows with 0 errors
  V2  every arm's mean coverage re-derives from its per-query page arrays
  V3  the per-query_type means re-derive
  V4  G1  — arm C's coverage reproduces T0's fusion row (0.684486, tol 1e-6)
  V5  G2  — arm C's mean pool size reproduces T0's (86.466165, tol 1e-6)
  V6  G2b — D500_raw reproduces T0's boundary 5 (0.838136, tol 1e-6)
  V7  G4  — every product arm's pool is page-deduped
  V8  G6  — pages(C) is a subset of pages(W500) on every query
  V9  G5  — arm C's two reps are bit-exact per query
  V10 the reported deltas re-derive
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE = Path("logs/p1/step10")
T0_FUSION_COVERAGE = 0.684486
T0_FUSION_POOL_MEAN = 86.466165
T0_B5_COVERAGE = 0.838136
TOL = 1e-6
PRODUCT_ARMS = ("C", "C_nommr", "W500", "W500_nommr")
DENSE_ARMS = ("D100", "D100_raw", "D500_raw")
ALL_ARMS = PRODUCT_ARMS + DENSE_ARMS
DELTA_KEYS = ("W500_minus_C", "C_nommr_minus_C", "W500_nommr_minus_W500", "C_minus_D100",
              "D100_minus_D100_raw", "D500_raw_minus_D100_raw")


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--artifact", default=str(BASE / "fusion_attribution.json"))
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    rows = [r for r in art["per_query"] if "error" not in r]
    errors = art["errors"]
    checks = []

    # V1 — 133 rows / 0 errors, and every arm present on every row.
    missing = {a: [r["id"] for r in rows if f"{a}_pages" not in r] for a in ALL_ARMS}
    v1 = (len(rows) == 133 and not errors and not any(missing.values()))
    checks.append(("V1_133_rows_0_errors_all_arms", v1,
                   {"n_rows": len(rows), "n_errors": len(errors),
                    "rows_missing_an_arm": {k: v[:5] for k, v in missing.items() if v}}))

    # coverage re-derivation: |pages ∩ relevant| / n_reachable. Every page the product's search returns
    # is in-window, so |pages ∩ reachable| == |pages ∩ relevant| (stated in the harness).
    def cov(r, arm):
        nr = r["n_reachable"]
        if not nr:
            return None
        return len(set(r[f"{arm}_pages"]) & set(r["relevant_pages"])) / nr

    # V2 — mean coverage per arm.
    v2 = True
    v2d = {}
    for arm in ALL_ARMS:
        red = mean(cov(r, arm) for r in rows if cov(r, arm) is not None)
        stored = art["aggregate"][arm]["overall"]["coverage"]
        v2d[arm] = {"rederived": red, "stored": stored}
        if stored is None or red is None or abs(red - stored) > 1e-12:
            v2 = False
    checks.append(("V2_mean_coverage_rederives", v2, v2d))

    # V3 — per-type means.
    v3 = True
    v3d = {}
    for arm in ALL_ARMS:
        for qt in ("factual", "multihop", "overview"):
            sub = [r for r in rows if r["query_type"] == qt]
            red = mean(cov(r, arm) for r in sub if cov(r, arm) is not None)
            stored = art["aggregate"][arm]["by_type"][qt]["coverage"]
            v3d[f"{arm}.{qt}"] = {"rederived": red, "stored": stored}
            if stored is None or red is None or abs(red - stored) > 1e-12:
                v3 = False
    checks.append(("V3_per_type_means_rederive", v3, v3d))

    # V4/V5/V6 — the three anchors.
    c_cov = mean(cov(r, "C") for r in rows if cov(r, "C") is not None)
    c_pool = mean(r["C_pool_size"] for r in rows)
    d500 = mean(cov(r, "D500_raw") for r in rows if cov(r, "D500_raw") is not None)
    checks.append(("V4_G1_C_reproduces_T0_fusion", abs(c_cov - T0_FUSION_COVERAGE) <= TOL,
                   {"rederived": c_cov, "t0": T0_FUSION_COVERAGE}))
    checks.append(("V5_G2_C_reproduces_T0_pool_mean", abs(c_pool - T0_FUSION_POOL_MEAN) <= TOL,
                   {"rederived": c_pool, "t0": T0_FUSION_POOL_MEAN}))
    checks.append(("V6_G2b_D500_raw_reproduces_T0_b5", abs(d500 - T0_B5_COVERAGE) <= TOL,
                   {"rederived": d500, "t0": T0_B5_COVERAGE}))

    # V7 — page-dedup in every product arm.
    dup = {a: [r["id"] for r in rows if len(r[f"{a}_pages"]) != len(set(r[f"{a}_pages"]))]
           for a in PRODUCT_ARMS}
    checks.append(("V7_G4_pools_page_deduped", not any(dup.values()),
                   {k: v[:5] for k, v in dup.items() if v}))

    # V8 — nesting.
    nn = [r["id"] for r in rows if not set(r["C_pages"]) <= set(r["W500_pages"])]
    checks.append(("V8_G6_C_subset_of_W500", not nn, {"non_nested_ids": nn[:10]}))

    # V9 — determinism of arm C.
    cc = [r["id"] for r in rows if r.get("C2_pages") != r.get("C_pages")]
    checks.append(("V9_G5_arm_C_bit_exact_repeat", not cc, {"mismatch_ids": cc[:10]}))

    # V10 — the reported deltas.
    def delta(a, b):
        d = [cov(r, b) - cov(r, a) for r in rows if cov(r, a) is not None and cov(r, b) is not None]
        return {"n": len(d), "mean": mean(d)}

    pairs = {"W500_minus_C": ("C", "W500"), "C_nommr_minus_C": ("C", "C_nommr"),
             "W500_nommr_minus_W500": ("W500", "W500_nommr"), "C_minus_D100": ("D100", "C"),
             "D100_minus_D100_raw": ("D100_raw", "D100"),
             "D500_raw_minus_D100_raw": ("D100_raw", "D500_raw")}
    v10 = True
    v10d = {}
    for key in DELTA_KEYS:
        a, b = pairs[key]
        red = delta(a, b)
        stored = art["deltas"][key]
        v10d[key] = {"rederived": red["mean"], "stored": stored["mean"], "n": red["n"]}
        if stored["mean"] is None or red["mean"] is None or abs(red["mean"] - stored["mean"]) > 1e-12:
            v10 = False
    checks.append(("V10_deltas_rederive", v10, v10d))

    allok = all(ok for _, ok, _ in checks)
    print(json.dumps({"checks": [{"id": c, "pass": ok, "detail": d} for c, ok, d in checks],
                      "all_pass": allok}, indent=2, default=str))
    if args.check:
        print("\nVERIFIER: ALL PASS" if allok else "\nVERIFIER: FAILURE(S)")
        return 0 if allok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
