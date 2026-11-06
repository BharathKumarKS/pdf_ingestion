"""Mutation proof for the overview retrieval-signal probe verifier (§I112).

Loads the artifact, applies one mutation at a time to a COPY, runs the verifier's `verify()` on it, and
asserts: (a) every mutation reddens at least one check, (b) every check is reddened by at least one
mutation (no inert check). Does not touch the artifact on disk.

Run:  .venv/bin/python logs/p1/step10/overview_signal_probe_mutation.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from overview_signal_probe_verifier import ART, verify  # noqa: E402

BASE = json.loads(ART.read_text())


def mutations(a: dict):
    """(name, mutated_artifact) — one mutation per verifiable claim."""
    m = copy.deepcopy(a); m["per_query"][0]["metrics"]["A"]["R@20"] += 0.5
    yield "MV1 per-query metric falsified", m

    m = copy.deepcopy(a); m["aggregates"]["A"]["R@20"] += 0.5
    yield "MV2 aggregate falsified", m

    m = copy.deepcopy(a); m["deltas"]["C-A"]["mean"] += 0.5
    yield "MV3 delta falsified", m

    m = copy.deepcopy(a); m["deltas"]["C-A"]["resolved"] = not m["deltas"]["C-A"]["resolved"]
    yield "MV4 resolved flag flipped", m

    m = copy.deepcopy(a); m["guards"]["G1_population_40"] = not m["guards"]["G1_population_40"]
    yield "MV5 G1 flag flipped", m

    m = copy.deepcopy(a); m["guards"]["G3_hypotheses_frozen"] = not m["guards"]["G3_hypotheses_frozen"]
    yield "MV6 G3 flag flipped", m

    m = copy.deepcopy(a); m["guards"]["G5_armB_differs_from_A"] = not m["guards"]["G5_armB_differs_from_A"]
    yield "MV7 G5 flag flipped", m

    m = copy.deepcopy(a); m["guards"]["G6_lane_ordered_len_ge_20"] = not m["guards"]["G6_lane_ordered_len_ge_20"]
    yield "MV8 G6 flag flipped", m

    m = copy.deepcopy(a); m["guards"]["G7_determinism_A"] = not m["guards"]["G7_determinism_A"]
    yield "MV9 G7 flag flipped", m

    m = copy.deepcopy(a)  # duplicate a page inside arm A -> the distinct-pages check must redden
    if m["per_query"][0]["pages"]["A"]:
        m["per_query"][0]["pages"]["A"][1] = m["per_query"][0]["pages"]["A"][0]
    yield "MV10 duplicate page in a list", m


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
        print(f"  {name:34s} -> reddened {len(newly)}: {', '.join(newly)}")
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
