"""Mutation proof for per_space_verifier.py. Every check must be reddenable, and every mutation
must redden its INTENDED check.  Usage: python logs/p1/step10/per_space_mutation.py
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "per_space_probe.json"
VER = HERE / "per_space_verifier.py"


def run(art, tmp: Path, list_checks=False):
    p = tmp / "a.json"
    p.write_text(json.dumps(art))
    r = subprocess.run([sys.executable, str(VER), "--list-checks" if list_checks else "--check",
                        "--artifact", str(p)], capture_output=True, text=True)
    return set(re.findall(r"FAIL\s+(\S+)", r.stdout)), r.stdout


def mutations():
    m = []

    def add(name, intended, fn):
        m.append((name, intended, fn))

    add("MV_V1_population", "V1_population", lambda a: a["meta"].__setitem__("n_queries", 999))
    add("MV_V4_spaces", "V4_arm_and_collection_spaces_differ",
        lambda a: a["meta"]["arm_a"].__setitem__("dim", a["meta"]["derived"]["dim"]))
    add("MV_V5_derived", "V5_derived_space_is_the_registered_one",
        lambda a: a["meta"]["derived"].__setitem__("dim", 512))
    for lane in ("da", "graph"):
        add(f"MV_A1_{lane}_before", f"V_A1_{lane}_empty_before",
            (lambda a, lane=lane: a["per_query"][0][lane].__setitem__("before_n", 3)))
        add(f"MV_A1_{lane}_err", f"V_A1_{lane}_before_errored",
            (lambda a, lane=lane: a["per_query"][0][lane].__setitem__("before_error", None)))
        add(f"MV_A1_{lane}_after", f"V_A1_{lane}_nonempty_after",
            (lambda a, lane=lane: a["per_query"][0][lane].__setitem__("after_n", 0)))
        add(f"MV_A2_{lane}", f"V_A2_{lane}_width_switched",
            (lambda a, lane=lane: a["per_query"][0][lane].__setitem__("a2_width_switched", False)))
        add(f"MV_A3_{lane}", f"V_A3_{lane}_pass_through",
            (lambda a, lane=lane: a["per_query"][0][lane].__setitem__(
                "a3_arm_b_pass_through", False)))
    add("MV_A3_da_ids", "V_A3_da_result_ids_identical",
        lambda a: a["per_query"][0]["da"].__setitem__("a3_da_result_identical", False))
    for k in ("A1_da_nonempty_after", "A1_graph_nonempty_after", "A1_da_empty_before",
              "A1_graph_empty_before", "A2_both_lanes_switched", "A3_da_bit_exact",
              "A3_graph_pass_through"):
        add(f"MV_summary_{k}", f"V_summary_{k}",
            (lambda a, k=k: a["summary"].__setitem__(k, (a["summary"].get(k) or 0) + 1)))
    return m


def main() -> int:
    art = json.loads(ART.read_text())
    with tempfile.TemporaryDirectory() as td:
        base_red, out = run(art, Path(td), list_checks=True)
        all_checks = set(re.findall(r"(?:PASS|FAIL)\s+(\S+)", out))
        if base_red:
            print(f"BASELINE NOT CLEAN: {sorted(base_red)}")
            return 2
        rows, all_red = [], set()
        import concurrent.futures as cf

        def one(item):
            name, intended, fn = item
            with tempfile.TemporaryDirectory() as sub:
                a = copy.deepcopy(art)
                fn(a)
                red, _ = run(a, Path(sub))
            return name, intended, intended in red, sorted(red)

        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for res in ex.map(one, mutations()):
                rows.append(res)
                all_red |= set(res[3])

    w = max(len(r[0]) for r in rows)
    ok_all = True
    for name, intended, hit, red in rows:
        extra = [x for x in red if x != intended]
        print(f"{name:{w}s}  {intended:34s}  {'YES' if hit else 'NO '}"
              + (f"   (+{len(extra)} other)" if extra else ""))
        ok_all &= hit
    inert = sorted(all_checks - all_red)
    print(f"\nmutations {len(rows)}  checks {len(all_checks)}  reddened {len(all_red)}")
    print(f"INERT checks     : {inert if inert else 'none'}")
    print(f"all mutations hit: {ok_all}")
    return 0 if (ok_all and not inert) else 1


if __name__ == "__main__":
    sys.exit(main())
