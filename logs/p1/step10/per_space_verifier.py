"""Independent verifier for the §A per-space query-vector probe (stdlib only).

Re-derives every guard from the artifact's RAW per-query records — never from the summary.

    python logs/p1/step10/per_space_verifier.py --check [--artifact P]
    python logs/p1/step10/per_space_verifier.py --list-checks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "per_space_probe.json"
checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list-checks", action="store_true")
    ap.add_argument("--artifact", default=str(ART))
    args = ap.parse_args()

    a = json.loads(Path(args.artifact).read_text())
    rows = a["per_query"]
    meta, summ = a["meta"], a["summary"]

    # ── V1 population / premise ──────────────────────────────────────────────────────────────
    check("V1_population", len(rows) == meta["n_queries"] and len(rows) > 0, f"n={len(rows)}")
    check("V4_arm_and_collection_spaces_differ",
          meta["arm_a"]["dim"] != meta["derived"]["dim"],
          f"arm_a={meta['arm_a']['dim']} derived={meta['derived']['dim']}")
    check("V5_derived_space_is_the_registered_one",
          meta["derived"]["model"] == "nomic-ai/nomic-embed-text-v1.5" and meta["derived"]["dim"] == 768,
          f"{meta['derived']}")

    # ── A1 — before: the lane was empty; after: it is not ────────────────────────────────────
    for lane in ("da", "graph"):
        empty_before = [r["id"] for r in rows if r[lane]["before_n"] != 0]
        check(f"V_A1_{lane}_empty_before", not empty_before, f"{empty_before[:5]}")
        err = [r["id"] for r in rows if not r[lane].get("before_error")]
        check(f"V_A1_{lane}_before_errored", not err, f"no error recorded: {err[:5]}")
        empty_after = [r["id"] for r in rows if r[lane]["after_n"] <= 0]
        check(f"V_A1_{lane}_nonempty_after", not empty_after, f"{empty_after[:5]}")

    # ── A2 — the lane's vector switched space ────────────────────────────────────────────────
    for lane in ("da", "graph"):
        bad = [r["id"] for r in rows if not r[lane]["a2_width_switched"]]
        check(f"V_A2_{lane}_width_switched", not bad, f"{bad[:5]}")

    # ── A3 — arm B is a bit-exact no-op ──────────────────────────────────────────────────────
    for lane in ("da", "graph"):
        bad = [r["id"] for r in rows if not r[lane]["a3_arm_b_pass_through"]]
        check(f"V_A3_{lane}_pass_through", not bad, f"{bad[:5]}")
    bad = [r["id"] for r in rows if not r["da"].get("a3_da_result_identical")]
    check("V_A3_da_result_ids_identical", not bad, f"{bad[:5]}")

    # ── the summary must be the re-derivation, not a claim ───────────────────────────────────
    want = {
        "A1_da_nonempty_after": sum(1 for r in rows if r["da"]["after_n"] > 0),
        "A1_graph_nonempty_after": sum(1 for r in rows if r["graph"]["after_n"] > 0),
        "A1_da_empty_before": sum(1 for r in rows if r["da"]["before_n"] == 0),
        "A1_graph_empty_before": sum(1 for r in rows if r["graph"]["before_n"] == 0),
        "A2_both_lanes_switched": sum(1 for r in rows if r["da"]["a2_width_switched"]
                                      and r["graph"]["a2_width_switched"]),
        "A3_da_bit_exact": sum(1 for r in rows if r["da"]["a3_arm_b_pass_through"]
                               and r["da"]["a3_da_result_identical"]),
        "A3_graph_pass_through": sum(1 for r in rows if r["graph"]["a3_arm_b_pass_through"]),
    }
    for k, v in want.items():
        check(f"V_summary_{k}", summ.get(k) == v, f"got={summ.get(k)} exp={v}")

    print(f"artifact : {args.artifact}\n")
    if args.list_checks:
        for n, okk, _ in checks:
            print(f"{'PASS' if okk else 'FAIL'} {n}")
        print(f"{len(checks)} checks")
        return 0
    n_fail = 0
    for n, okk, d in checks:
        if not okk:
            n_fail += 1
            print(f"  FAIL  {n}   {d}")
    print(f"{len(checks)} checks, {n_fail} failed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
