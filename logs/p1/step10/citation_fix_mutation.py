#!/usr/bin/env python3
"""Mutation proof for §I115's citation verifier — every check reddened by >=1 mutation, no inert.

Imports ``verify`` from the verifier, deep-copies the artifact, applies one targeted mutation per
case, and records which checks go red.

Run:  .venv/bin/python logs/p1/step10/citation_fix_mutation.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from citation_fix_verifier import verify  # noqa: E402

ART = HERE / "citation_fix.json"


def main() -> int:
    base = json.loads(ART.read_text())
    baseline = {n: ok for n, ok in verify(base)}
    if not all(baseline.values()):
        print("BASELINE NOT GREEN — fix the artifact before mutating:", baseline)
        return 1

    def m_agg(key, delta):
        d = copy.deepcopy(base); d["aggregates"][key] = d["aggregates"][key] + delta; return d

    def m_field(i, key, val):
        d = copy.deepcopy(base); d["per_answer"][i][key] = val; return d

    mutations = {
        "MV01 n_answers +1": m_agg("n_answers", 1),
        "MV02 old_metric_sees_a_citation -> 5": m_agg("old_metric_sees_a_citation", 5),
        "MV03 a cited_old made non-empty (old regex DID see one)":
            m_field(0, "cited_old", [1]),
        "MV04 old_metric_aggregate -> 0.5": m_agg("old_metric_aggregate", -0.5),
        "MV05 new_cited +1": m_agg("new_cited", 1),
        "MV06 new_coverage +0.01": m_agg("new_coverage", 0.01),
        "MV07 new_uncited +1": m_agg("new_uncited", 1),
        "MV08 new_uncited_share +0.01": m_agg("new_uncited_share", 0.01),
        "MV09 new_accuracy_over_citing +0.01": m_agg("new_accuracy_over_citing", 0.01),
        "MV10 new_answer_cites_gold_recall +0.01": m_agg("new_answer_cites_gold_recall", 0.01),
        "MV11 valid_new not a subset of cited_new": m_field(0, "valid_new", [9999]),
        "MV12 gold_hit_new not a subset of cited_new": m_field(0, "gold_hit_new", [9999]),
        "MV13 duplicate page in cited_new": m_field(0, "cited_new", [1, 1]),
        "MV14 cited_old not a subset of cited_new": m_field(0, "cited_old", [9999]),
    }

    reddened: dict[str, int] = {n: 0 for n in baseline}
    for label, d in mutations.items():
        red = [n for n, ok in verify(d) if not ok]
        for n in red:
            reddened[n] += 1
        print(f"  {label:<52} -> reddened {len(red)}: {', '.join(s.split()[0] for s in red) or 'NONE'}")

    inert = [n for n, k in reddened.items() if k == 0]
    print(f"\nchecks reddened by >=1 mutation: {sum(1 for k in reddened.values() if k)}/{len(reddened)}")
    if inert:
        print("INERT CHECK(S):", inert)
        return 1
    print("MUTATION PROOF PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
