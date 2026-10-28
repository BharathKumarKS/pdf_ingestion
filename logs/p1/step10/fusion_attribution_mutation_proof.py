"""Mutation proof for `fusion_attribution_verifier.py` — proves each check can FAIL, and which ones fire.

Each mutation is applied to a scratch COPY of the artifact, the verifier is run against that copy
(`--artifact`), and the full pass/fail vector is recorded. The essential property is:
  * every check has at least one mutation that reddens it (no inert check), and
  * each mutation reddens its INTENDED check.
A mutation that also reddens other checks is reported with the reason rather than hidden — several checks
read the same per-query page arrays, so perfect isolation is not always possible (and is not required).

    uv run python logs/p1/step10/fusion_attribution_mutation_proof.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path("logs/p1/step10")
ARTIFACT = BASE / "fusion_attribution.json"
SCRATCH = Path("/tmp/fusion_attribution_mutation.json")
VERIFIER = "logs/p1/step10/fusion_attribution_verifier.py"


def _load():
    return json.loads(ARTIFACT.read_text())


def m1_v1_drop_row(d):
    d["per_query"].pop()


def m2_v2_mean_coverage(d):
    d["aggregate"]["C"]["overall"]["coverage"] += 0.01


def m3_v3_type_mean(d):
    d["aggregate"]["C"]["by_type"]["factual"]["coverage"] += 0.01


def m4_v4_anchor_drift(d):
    """Move arm C's coverage away from T0's anchor by rewriting its page sets on every 3rd query."""
    for i, r in enumerate(d["per_query"]):
        if "error" in r or i % 3:
            continue
        r["C_pages"] = []
        r["C2_pages"] = []


def m5_v5_pool_mean(d):
    for r in d["per_query"]:
        if "error" not in r and "C_pool_size" in r:
            r["C_pool_size"] += 1


def m6_v6_b5_drift(d):
    for i, r in enumerate(d["per_query"]):
        if "error" in r or i % 4:
            continue
        r["D500_raw_pages"] = []


def m7_v7_duplicate_page(d):
    for r in d["per_query"]:
        if "error" not in r and r.get("C_pages"):
            r["C_pages"] = r["C_pages"] + [r["C_pages"][0]]


def m8_v8_nesting(d):
    for r in d["per_query"]:
        if "error" not in r and r.get("W500_pages") and r.get("C_pages"):
            r["W500_pages"] = [p for p in r["W500_pages"] if p not in set(r["C_pages"])]


def m9_v9_repeat_mismatch(d):
    for r in d["per_query"]:
        if "error" not in r and r.get("C2_pages"):
            r["C2_pages"] = r["C2_pages"] + [999999]


def m10_v10_delta(d):
    d["deltas"]["W500_minus_C"]["mean"] += 0.01


MUTATIONS = [
    ("MV1", "V1", "drop one per-query row", m1_v1_drop_row),
    ("MV2", "V2", "aggregate.C.overall.coverage += 0.01", m2_v2_mean_coverage),
    ("MV3", "V3", "aggregate.C.by_type.factual.coverage += 0.01", m3_v3_type_mean),
    ("MV4", "V4", "ANCHOR DRIFT: arm C's pages emptied on every 3rd query", m4_v4_anchor_drift),
    ("MV5", "V5", "arm C pool sizes +1 (pool mean moves off T0's 86.466165)", m5_v5_pool_mean),
    ("MV6", "V6", "D500_raw pages emptied on every 4th query (b5 anchor drifts)", m6_v6_b5_drift),
    ("MV7", "V7", "duplicate a page inside arm C's pool", m7_v7_duplicate_page),
    ("MV8", "V8", "remove arm C's pages from arm W500's pool (nesting broken)", m8_v8_nesting),
    ("MV9", "V9", "arm C's repeat pages gain a phantom page", m9_v9_repeat_mismatch),
    ("MV10", "V10", "deltas.W500_minus_C.mean += 0.01", m10_v10_delta),
]


def run_verifier() -> dict:
    out = subprocess.run([sys.executable, VERIFIER, "--artifact", str(SCRATCH)],
                         capture_output=True, text=True)
    try:
        return json.loads(out.stdout)
    except Exception:
        return {"checks": [], "all_pass": None, "stdout": out.stdout[-400:], "stderr": out.stderr[-400:]}


def main() -> int:
    SCRATCH.write_text(ARTIFACT.read_text())      # the unmutated copy IS the baseline
    baseline = run_verifier()
    base_fail = [c["id"] for c in baseline["checks"] if not c["pass"]]
    check_ids = [c["id"] for c in baseline["checks"]]

    lines = ["Fusion attribution verifier — MUTATION PROOF (fusion_attribution_mutation_proof.py)", ""]
    lines.append(f"BASELINE (no mutation): all_pass={baseline['all_pass']}  failing={base_fail or 'none'}")
    lines.append("")

    table, ok_all = [], not base_fail
    for name, intended, desc, fn in MUTATIONS:
        d = _load()
        fn(d)
        SCRATCH.write_text(json.dumps(d, indent=2))
        res = run_verifier()
        failed = [c["id"] for c in res["checks"] if not c["pass"]]
        hit = any(c.startswith(intended) for c in failed)
        ok_all = ok_all and hit
        table.append((name, intended, desc, failed, hit))
        lines.append(f"{name}  intended={intended}  -> {'RED (as intended)' if hit else 'DID NOT FIRE'}")
        lines.append(f"     mutation: {desc}")
        lines.append(f"     checks red: {failed if failed else 'none'}")
        lines.append("")

    covered = {cid: False for cid in check_ids}
    for _, _, _, failed, _ in table:
        for f in failed:
            if f in covered:
                covered[f] = True
    lines.append("PER-CHECK COVERAGE (each check must be reddened by at least one mutation):")
    for cid in check_ids:
        lines.append(f"  {'YES' if covered[cid] else 'NO '}  {cid}")
    uncovered = [c for c, v in covered.items() if not v]
    lines.append("")
    lines.append(f"VERDICT: {'ALL MUTATIONS FIRE AS INTENDED' if ok_all else 'SOME MUTATION DID NOT FIRE'}; "
                 f"{'every check is reddened' if not uncovered else 'INERT CHECKS: ' + str(uncovered)}")
    (BASE / "fusion_attribution_mutation_log.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if (ok_all and not uncovered and not base_fail) else 1


if __name__ == "__main__":
    raise SystemExit(main())
