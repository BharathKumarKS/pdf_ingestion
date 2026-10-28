"""Mutation proof for `t1_verifier.py` — proves each check can FAIL, and which ones fire.

⚠️ TIMING, STATED PLAINLY. The T1 pre-registration (§9) required this proof BEFORE the run. It was
actually performed AFTER the run. The deviation is recorded in the log it writes. It does not affect the
run or the artifact: the verifier is a read-only checker, and mutating COPIES of the written JSON proves
discrimination exactly as well after the fact. Claiming otherwise would be worse than the deviation.

Each mutation is applied to a scratch COPY of the five input files, the verifier is run against that
copy (`--base`), and the full pass/fail vector is recorded. The essential property is:
  * every check has at least one mutation that reddens it (no check is inert), and
  * each mutation reddens its INTENDED check.
A mutation that also reddens other checks is reported with the reason rather than hidden — several checks
share the per-query array, so perfect isolation is not always possible (and is not required).

    uv run python logs/p1/step10/t1_mutation_proof.py
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path("logs/p1/step10")
SCRATCH = Path("/tmp/t1_mutation_scratch")
FILES = ["t1_base_lanes.json", "t1_arm_A1.json", "t1_arm_A2.json", "t1_arm_B1.json", "t1_arm_B2.json"]
VERIFIER = "logs/p1/step10/t1_verifier.py"


def _loads():
    return {f: json.loads((BASE / f).read_text()) for f in FILES}


def m1_v1_drop_row(d):
    d["t1_arm_A1.json"]["per_query"].pop()


def m2_v2_meta_mean(d):
    d["t1_base_lanes.json"]["meta"]["mean_r20"]["A"] += 0.01


def m3_v3_p2_delta(d):
    d["t1_base_lanes.json"]["endpoints"]["P2_R20_raw"]["mean_delta"] += 0.01


def m4_v4_p1_ci(d):
    d["t1_base_lanes.json"]["endpoints"]["P1_cR20"]["ci"][0] -= 0.05


def m5_v5_a2_metric(d):
    r = d["t1_arm_A2.json"]["per_query"][0]
    r["metrics"]["recall_at_20"] = 0.25


def m6_v6_instrument_drift(d):
    """Model INSTRUMENT DRIFT: A1, A2 and Stage F's arm A all move together, consistently recorded."""
    for f in ("t1_arm_A1.json", "t1_arm_A2.json", "stageF_arm_A1.json"):
        src = BASE / f
        obj = d.get(f) or json.loads(src.read_text())
        d[f] = obj
        for r in obj["per_query"]:
            if "metrics" in r:
                r["metrics"]["recall_at_20"] = round(min(1.0, r["metrics"]["recall_at_20"] + 0.05), 4)
    # the summary block moves with it, as a real drifting instrument would have recorded
    rows = [r for r in d["t1_arm_A1.json"]["per_query"] if "error" not in r]
    d["t1_base_lanes.json"]["meta"]["mean_r20"]["A"] = sum(
        r["metrics"]["recall_at_20"] for r in rows) / len(rows)
    agg = d["t1_base_lanes.json"]["diagnostics"]["E8_arm_A_aggregate"]
    agg["recall_at_20"] = d["t1_base_lanes.json"]["meta"]["mean_r20"]["A"]


def m7_v7_none_metric(d):
    for f in ("t1_arm_A1.json", "t1_arm_A2.json"):
        d[f]["per_query"][0]["metrics"]["mrr"] = None


def m8_v8_divisor(d):
    for r in d["t1_arm_B1.json"]["per_query"]:
        if r.get("achievable_max") is not None:
            r["achievable_max"] = round(r["achievable_max"] + 0.1, 6)


def m9_v9_stagef_metric(d):
    obj = json.loads((BASE / "stageF_arm_A1.json").read_text())
    obj["per_query"][0]["metrics"]["recall_at_20"] = 0.25
    d["stageF_arm_A1.json"] = obj


MUTATIONS = [
    ("MV1", "V1", "drop one per-query row from arm A1", m1_v1_drop_row),
    ("MV2", "V2", "artifact meta.mean_r20.A += 0.01", m2_v2_meta_mean),
    ("MV3", "V3", "artifact P2 mean_delta += 0.01", m3_v3_p2_delta),
    ("MV4", "V4", "artifact P1 ci[0] -= 0.05", m4_v4_p1_ci),
    ("MV5", "V5", "arm A2 row 0 recall_at_20 -> 0.25", m5_v5_a2_metric),
    ("MV6", "V6", "INSTRUMENT DRIFT: A1+A2+StageF all +0.05, summary consistent", m6_v6_instrument_drift),
    ("MV7", "V7", "arm A1+A2 row 0 mrr -> None", m7_v7_none_metric),
    ("MV8", "V8", "arm B1 achievable_max += 0.1 (divisor differs across arms)", m8_v8_divisor),
    ("MV9", "V9", "Stage F arm A row 0 recall_at_20 -> 0.25 (A1 no longer matches Stage F)", m9_v9_stagef_metric),
]


def run_verifier() -> dict:
    out = subprocess.run([sys.executable, VERIFIER, "--base", str(SCRATCH)],
                         capture_output=True, text=True)
    try:
        return json.loads(out.stdout)
    except Exception:
        return {"checks": [], "all_pass": None, "stdout": out.stdout[-500:], "stderr": out.stderr[-500:]}


def main() -> int:
    # baseline: unmutated copy must PASS everything
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for f in FILES + ["stageF_arm_A1.json"]:
        shutil.copy(BASE / f, SCRATCH / f)
    baseline = run_verifier()
    base_fail = [c["id"] for c in baseline["checks"] if not c["pass"]]

    lines = []
    lines.append("T1 verifier — MUTATION PROOF (logs/p1/step10/t1_mutation_proof.py)")
    lines.append("")
    lines.append("⚠️ TIMING: performed AFTER the run, not before it as T1's pre-registration §9 required.")
    lines.append("   Recorded as a deviation. The verifier is a read-only checker of the written artifact,")
    lines.append("   so mutating copies proves discrimination equally well; nothing in the run is affected.")
    lines.append("")
    lines.append(f"BASELINE (no mutation): all_pass={baseline['all_pass']}  failing={base_fail or 'none'}")
    lines.append("")

    check_ids = [c["id"] for c in baseline["checks"]]
    table = []
    ok_all = (not base_fail)
    for name, intended, desc, fn in MUTATIONS:
        d = _loads()
        fn(d)
        for f, obj in d.items():
            (SCRATCH / f).write_text(json.dumps(obj, indent=2))
        res = run_verifier()
        failed = [c["id"] for c in res["checks"] if not c["pass"]]
        hit = any(c.startswith(intended) for c in failed)
        ok_all = ok_all and hit
        table.append((name, intended, desc, failed, hit))
        lines.append(f"{name}  intended={intended}  -> {'RED (as intended)' if hit else 'DID NOT FIRE'}")
        lines.append(f"     mutation: {desc}")
        lines.append(f"     checks red: {failed if failed else 'none'}")
        lines.append("")

    # coverage: every check must be reddened by at least one mutation
    covered = {cid: False for cid in check_ids}
    for _, _, _, failed, _ in table:
        for f in failed:
            for cid in check_ids:
                if cid == f:
                    covered[cid] = True
    lines.append("PER-CHECK COVERAGE (each check must be reddened by at least one mutation):")
    for cid in check_ids:
        lines.append(f"  {'YES' if covered[cid] else 'NO '}  {cid}")
    uncovered = [c for c, v in covered.items() if not v]
    lines.append("")
    lines.append(f"VERDICT: {'ALL MUTATIONS FIRE AS INTENDED' if ok_all else 'SOME MUTATION DID NOT FIRE'}; "
                 f"{'every check is reddened' if not uncovered else 'INERT CHECKS: ' + str(uncovered)}")
    (BASE / "t1_mutation_log.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if (ok_all and not uncovered and not base_fail) else 1


if __name__ == "__main__":
    raise SystemExit(main())
