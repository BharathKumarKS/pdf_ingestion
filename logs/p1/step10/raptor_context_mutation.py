"""Mutation proof for the RAPTOR-as-generator-context verifier (§I113).

Loads the artifact, applies one mutation at a time to a COPY, runs the verifier's `verify()` on it, and
asserts: (a) every mutation reddens at least one check, (b) every check is reddened by at least one
mutation (no inert check). Does not touch the artifact on disk.

Run:  .venv/bin/python logs/p1/step10/raptor_context_mutation.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from raptor_context_verifier import ART, METRICS, verify  # noqa: E402

BASE = json.loads(ART.read_text())


def mutations(a: dict):
    """(name, mutated_artifact) — one mutation per verifiable claim."""
    m = copy.deepcopy(a); m["aggregates"]["A_faithfulness"] += 0.5
    yield "MV01 aggregate A_faithfulness falsified", m

    m = copy.deepcopy(a); m["aggregates"]["B_faithfulness"] += 0.5
    yield "MV02 aggregate B_faithfulness falsified", m

    for metric in METRICS:
        m = copy.deepcopy(a); m["deltas"][metric]["mean"] += 0.5
        yield f"MV03 {metric} delta mean falsified", m

        m = copy.deepcopy(a); m["deltas"][metric]["ci"][0] += 0.5
        yield f"MV04 {metric} delta CI falsified", m

        m = copy.deepcopy(a); m["deltas"][metric]["n"] += 1
        yield f"MV05 {metric} delta n falsified", m

        m = copy.deepcopy(a); m["deltas"][metric]["wins"] += 1
        yield f"MV06 {metric} delta wins falsified", m

    m = copy.deepcopy(a); m["deltas"]["faithfulness"]["resolved"] = not m["deltas"]["faithfulness"]["resolved"]
    yield "MV07 faithfulness resolved flag flipped", m

    for i, key in enumerate(("G1_population_40", "G2_zero_errors", "G3_pages_identical_between_arms",
                             "G4_summaries_are_pageless_and_absent", "G5_judge_cross_family",
                             "G6_armA_reproduces_I108_baseline", "G7_attachment_deterministic"), start=8):
        m = copy.deepcopy(a); m["guards"][key] = not m["guards"][key]
        yield f"MV{i:02d} {key} flag flipped", m

    m = copy.deepcopy(a); m["per_query"][0]["n_summaries"] += 1
    yield "MV15 n_summaries desynced from summary_ids", m

    m = copy.deepcopy(a)  # duplicate a page inside arm A -> the distinct-pages check must redden
    if m["per_query"][0]["page_list_A"]:
        m["per_query"][0]["page_list_A"][1] = m["per_query"][0]["page_list_A"][0]
    yield "MV16 duplicate page in page_list_A", m

    m = copy.deepcopy(a)  # duplicate a summary id -> the distinct-summary-ids check must redden
    if len(m["per_query"][0]["summary_ids"]) >= 2:
        m["per_query"][0]["summary_ids"][1] = m["per_query"][0]["summary_ids"][0]
    yield "MV17 duplicate summary id", m


def main() -> int:
    base_res = {n: ok for n, ok, _ in verify(BASE)}
    reddened_by: dict[str, int] = {n: 0 for n in base_res}
    bad = []
    for name, mutated in mutations(BASE):
        res = {n: ok for n, ok, _ in verify(mutated)}
        newly = [n for n, ok in res.items() if not ok]
        if not newly:
            bad.append(f"{name}: NO check reddened (inert mutation)")
        for n in newly:
            reddened_by[n] += 1
        print(f"  {name:44s} -> reddened {len(newly)}: {', '.join(newly)}")
    inert = [n for n, c in reddened_by.items() if c == 0]
    print("\nchecks reddened by >=1 mutation: "
          f"{sum(1 for c in reddened_by.values() if c)}/{len(reddened_by)}")
    if inert:
        print("INERT CHECKS (never reddened):", inert)
    if bad:
        for b in bad:
            print("  ⚠️", b)
    ok = not inert and not bad
    print("MUTATION PROOF PASS" if ok else "MUTATION PROOF FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
