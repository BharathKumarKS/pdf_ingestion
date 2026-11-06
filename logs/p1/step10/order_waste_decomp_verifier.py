"""Independent verifier for Stage 0's root-cause decomposition.

stdlib only. Reads the WRITTEN artifact AND re-derives every number from the SOURCE artifact's
raw per-query arrays, so the harness's own arithmetic is not trusted.

    python logs/p1/step10/order_waste_decomp_verifier.py --check [--artifact P] [--source P]

Every check must be able to FAIL. The mutation proof (order_waste_decomp_mutation.py) reddens
each check in turn; a check no mutation can redden is inert and is reported as such.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "order_waste_decomp.json"
SRC = HERE / "t4_endpoint.json"
T0 = HERE / "t0_baseline.json"

TYPES = ("factual", "overview", "multihop")
EXPECTED_N = {"factual": 53, "overview": 40, "multihop": 40}
TOL = 1e-9


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, vid, ok, detail=""):
        self.rows.append({"id": vid, "pass": bool(ok), "detail": detail})

    @property
    def failed(self):
        return [r for r in self.rows if not r["pass"]]


def rederive(src: dict):
    """Re-derive the whole decomposition straight from the source per-query arrays."""
    out = {}
    for t in TYPES:
        sel = [r for r in src["per_query"] if r["query_type"] == t]
        recs = []
        for r in sel:
            rel = set(r["relevant_pages"])
            n_rel = r["n_relevant"]
            n_reach = r["n_reachable"]
            recs.append(
                dict(
                    n_rel=n_rel,
                    pool_gold=r["C_pool_cov"] * n_reach,
                    R_ceil_20=min(20, n_rel) / n_rel,
                    oracle=min(20, r["C_pool_cov"] * n_reach) / n_rel,
                    rN=len(set(r["N_pages"]) & rel) / n_rel,
                    rC=len(set(r["C_pages"]) & rel) / n_rel,
                )
            )
        out[t] = recs
    allr = [r for t in TYPES for r in out[t]]
    return out, allr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--source", default=str(SRC))
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    src = json.loads(Path(args.source).read_text())
    c = Checks()

    d = art["decomposition"]
    per, allr = rederive(src)

    # V1 -- the recorded input digests match the files on disk
    meta_inputs = art["meta"]["inputs"]
    ok = meta_inputs.get("t4_endpoint.json") == sha256(Path(args.source))
    c.add("V1_input_digest_t4", ok, f"meta={meta_inputs.get('t4_endpoint.json','?')[:16]} disk={sha256(Path(args.source))[:16]}")
    ok2 = meta_inputs.get("t0_baseline.json") == sha256(T0)
    c.add("V1b_input_digest_t0", ok2, f"meta={meta_inputs.get('t0_baseline.json','?')[:16]} disk={sha256(T0)[:16]}")

    # V2 -- population counts
    n_ok = d["n_queries"] == len(src["per_query"]) == 133
    c.add("V2_n_queries_133", n_ok, f"artifact={d['n_queries']} source={len(src['per_query'])}")
    for t in TYPES:
        got = d["by_type"][t]["aggregate"]["n"]
        c.add(f"V2b_n_{t}", got == EXPECTED_N[t], f"got={got} expected={EXPECTED_N[t]}")

    # V3..V7 -- every aggregate cell re-derived from the source arrays
    cells = [("R_ceil_20", "R_ceil_20"), ("pool_oracle_20", "oracle"),
             ("realised_N", "rN"), ("realised_C", "rC")]
    for name, key in cells:
        for t in TYPES:
            got = d["by_type"][t]["aggregate"][name]
            exp = mean(r[key] for r in per[t])
            c.add(f"V3_{name}_{t}", abs(got - exp) <= TOL, f"got={got:.10f} exp={exp:.10f}")
        got = d["overall"][name]
        exp = mean(r[key] for r in allr)
        c.add(f"V3_{name}_overall", abs(got - exp) <= TOL, f"got={got:.10f} exp={exp:.10f}")

    # V4 -- per-query pool_gold is C_pool_cov * n_reachable (source), and it is stored
    bad = 0
    for t in TYPES:
        for rec, src_row in zip(d["by_type"][t]["per_query"], [r for r in src["per_query"] if r["query_type"] == t]):
            exp = src_row["C_pool_cov"] * src_row["n_reachable"]
            if abs(rec["pool_gold"] - exp) > 1e-12:
                bad += 1
    c.add("V4_pool_gold_identity", bad == 0, f"{bad} mismatches")

    # V5 -- the waste identities hold exactly
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        c.add(f"V5_waste_pool_{t}", abs(a["waste_pool"] - (a["R_ceil_20"] - a["pool_oracle_20"])) <= TOL)
        c.add(f"V5_waste_order_{t}", abs(a["waste_order"] - (a["pool_oracle_20"] - a["realised_N"])) <= TOL)
        c.add(f"V5_waste_ce_{t}", abs(a["waste_ce"] - (a["realised_N"] - a["realised_C"])) <= TOL)
        c.add(f"V5_recoverable_{t}", abs(a["recoverable_total"] - (a["R_ceil_20"] - a["realised_C"])) <= TOL)

    # V6 -- the shares sum to 1 where the total is non-zero
    for t in TYPES:
        a = d["by_type"][t]["aggregate"]
        if a["recoverable_total"] > 0:
            s = a["share_waste_pool"] + a["share_waste_order"] + a["share_waste_ce"]
            c.add(f"V6_shares_sum_1_{t}", abs(s - 1.0) <= 1e-9, f"sum={s:.12f}")

    # V7 -- the oracle can never exceed the label ceiling, per query
    bad = 0
    for t in TYPES:
        for r in per[t]:
            if r["oracle"] > r["R_ceil_20"] + 1e-12:
                bad += 1
    c.add("V7_oracle_le_ceiling", bad == 0, f"{bad} violations")

    # V8 -- the product's realised recall can never exceed the pool oracle, per query
    bad = 0
    for t in TYPES:
        for r in per[t]:
            if r["rC"] > r["oracle"] + 1e-12:
                bad += 1
    c.add("V8_realised_C_le_oracle", bad == 0, f"{bad} violations")

    # V9 -- the funnel coverage block matches T0's aggregate
    t0 = json.loads(T0.read_text())["aggregate"]
    bad = []
    for t in ("overall",) + TYPES:
        for stage in ("base", "cut", "fusion", "ce"):
            blk = t0[stage]
            b = blk.get("overall") if t == "overall" else (blk.get("by_type") or {}).get(t)
            if not b:
                continue
            exp = b.get("coverage_reachable", b.get("coverage"))
            got = art["funnel_coverage"][t][stage]["coverage"]
            if abs(got - exp) > 1e-9:
                bad.append(f"{t}/{stage}")
    c.add("V9_funnel_matches_T0", not bad, f"mismatches={bad}")

    # V10 -- no NaN / null in the aggregates
    bad = []
    for t in TYPES:
        for k, v in d["by_type"][t]["aggregate"].items():
            if v is None or (isinstance(v, float) and v != v):
                bad.append(f"{t}.{k}")
    c.add("V10_no_nan", not bad, f"{bad}")

    print(f"artifact : {args.artifact}")
    print(f"source   : {args.source}")
    print()
    for r in c.rows:
        print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['id']}" + (f"   {r['detail']}" if not r["pass"] else ""))
    print()
    print(f"{len(c.rows)} checks, {len(c.failed)} failed")
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main())
