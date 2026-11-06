#!/usr/bin/env python3
"""Independent stdlib verifier for §I115's citation re-derivation.

Re-derives EVERY cell from the artifact's raw per-answer arrays (it does not import the
harness). Importable: ``verify(d) -> list[(name, ok)]`` so the mutation proof can drive it.

Run:  .venv/bin/python logs/p1/step10/citation_fix_verifier.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / "logs/p1/step10/citation_fix.json"


def verify(d: dict) -> list[tuple[str, bool]]:
    per, agg = d["per_answer"], d["aggregates"]
    n = len(per)
    old_sees = sum(1 for x in per if x["cited_old"])
    new_sees = sum(1 for x in per if x["cited_new"])
    acc = [len(x["valid_new"]) / len(x["cited_new"]) for x in per if x["cited_new"]]
    ghr = [len(x["gold_hit_new"]) / x["n_gold"] for x in per if x["n_gold"]]
    c: list[tuple[str, bool]] = []
    add = lambda name, cond: c.append((name, bool(cond)))  # noqa: E731
    add("V1  n_answers matches the per-answer array", agg["n_answers"] == n)
    add("V2  old_metric_sees_a_citation re-derived", agg["old_metric_sees_a_citation"] == old_sees)
    add("V3  the SHIPPED regex sees ZERO citations (the vacuity)", old_sees == 0)
    add("V4  old_metric_aggregate is the vacuous 1.0", agg["old_metric_aggregate"] == 1.0)
    add("V5  new_cited re-derived", agg["new_cited"] == new_sees)
    add("V6  new_coverage re-derived", agg["new_coverage"] == round(new_sees / n, 4))
    add("V7  new_uncited re-derived", agg["new_uncited"] == n - new_sees)
    add("V8  new_uncited_share re-derived", agg["new_uncited_share"] == round((n - new_sees) / n, 4))
    add("V9  new_accuracy_over_citing re-derived",
        agg["new_accuracy_over_citing"] == (round(st.mean(acc), 4) if acc else None))
    add("V10 new_answer_cites_gold_recall re-derived",
        agg["new_answer_cites_gold_recall"] == (round(st.mean(ghr), 4) if ghr else None))
    add("V11 valid_new ⊆ cited_new", all(set(x["valid_new"]) <= set(x["cited_new"]) for x in per))
    add("V12 gold_hit_new ⊆ cited_new", all(set(x["gold_hit_new"]) <= set(x["cited_new"]) for x in per))
    add("V13 cited_new has no duplicates", all(len(x["cited_new"]) == len(set(x["cited_new"])) for x in per))
    add("V14 cited_old ⊆ cited_new (the fix is a superset, never a subset)",
        all(set(x["cited_old"]) <= set(x["cited_new"]) for x in per))
    return c


def main() -> int:
    d = json.loads(ART.read_text())
    checks = verify(d)
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
    n_ok = sum(1 for _, ok in checks if ok)
    print(f"\n{n_ok}/{len(checks)} checks PASS")
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
