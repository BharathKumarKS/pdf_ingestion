"""Verifier + mutation proof for the §G3 sensitive re-measurement.

Independently RE-DERIVES the primary endpoint from the two input artifacts and checks the output
artifact against it (V1..V8). Then mutates COPIES of the output artifact — one targeted change per
check — and records the pass/fail vector, proving each check discriminates (no inert check).

Usage:
    .venv/bin/python logs/p1/step10/g3_sensitive_remeasure_verifier.py            # verify
    .venv/bin/python logs/p1/step10/g3_sensitive_remeasure_verifier.py --mutate   # + mutation proof
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
D = REPO / "logs/p1/step10"
ART = D / "g3_sensitive_remeasure.json"
BEFORE = D / "g3_query_side_baseline_2026-10-22.json"
AFTER = D / "g3_query_side_baseline_2026-10-22_post_merge.json"
# Mutable so the input-mutation (M8) can point the re-derivation at a doctored input copy.
_AFTER_PATH = AFTER


def ge2(hist): return sum(int(c) for k, c in hist.items() if int(k) >= 2)
def tot(hist): return sum(int(c) for c in hist.values())


def t975(df):
    try:
        from scipy.stats import t  # type: ignore
        return float(t.ppf(0.975, df))
    except Exception:
        return 1.9720


def rederive():
    """Independent recomputation of the primary endpoint from the raw inputs."""
    b = {q["id"]: q for q in json.loads(BEFORE.read_text())["queries"]}
    a = {q["id"]: q for q in json.loads(_AFTER_PATH.read_text())["queries"]}
    ids = sorted(set(b) & set(a))
    deltas = [ge2(a[i]["matched_concepts_histogram"]) - ge2(b[i]["matched_concepts_histogram"])
              for i in ids]
    n = len(deltas)
    mean = sum(deltas) / n
    var = sum((d - mean) ** 2 for d in deltas) / (n - 1)
    sd = math.sqrt(var)
    half = t975(n - 1) * sd / math.sqrt(n)
    return {
        "ids_match": set(b) == set(a) and n == 200,
        "n": n, "mean": round(mean, 6), "sd": round(sd, 6),
        "ci": [round(mean - half, 6), round(mean + half, 6)],
        "before_total": sum(ge2(b[i]["matched_concepts_histogram"]) for i in ids),
        "after_total": sum(ge2(a[i]["matched_concepts_histogram"]) for i in ids),
        "before_chunks": sum(tot(b[i]["matched_concepts_histogram"]) for i in ids),
        "w": sum(1 for d in deltas if d > 0), "l": sum(1 for d in deltas if d < 0),
        "ties": sum(1 for d in deltas if d == 0),
    }


def checks(art, ref):
    p, s = art["primary_ge2_count"], art["secondary_share_ge_2"]
    c = []
    c.append(("V1_anchor_before_138", p["before_total"] == 138, f"{p['before_total']}"))
    c.append(("V2_anchor_after_158", p["after_total"] == 158, f"{p['after_total']}"))
    c.append(("V3_delta_consistent",
              abs(p["mean_paired_delta"] - (p["after_total"] - p["before_total"]) / p["n"]) < 1e-9,
              f"{p['mean_paired_delta']}"))
    c.append(("V4_mean_matches_rederivation", p["mean_paired_delta"] == ref["mean"],
              f"{p['mean_paired_delta']} vs {ref['mean']}"))
    c.append(("V5_ci_matches_rederivation", p["ci95"] == ref["ci"], f"{p['ci95']} vs {ref['ci']}"))
    c.append(("V6_wl_ties_sum_to_n", p["w"] + p["l"] + p["ties"] == p["n"],
              f"{p['w']}+{p['l']}+{p['ties']} vs {p['n']}"))
    c.append(("V7_share_ge2_consistent",
              abs(s["before"] - p["before_total"] / s["before_chunks"]) < 1e-5,
              f"{s['before']} vs {p['before_total']}/{s['before_chunks']}"))
    lo, hi = p["ci95"]
    expect = "UNRESOLVED" if lo <= 0 <= hi else "RESOLVED"
    c.append(("V8_verdict_logic", p["verdict"] == expect, f"{p['verdict']} expect {expect}"))
    c.append(("V9_inputs_ids_match", ref["ids_match"], str(ref["ids_match"])))
    return c


MUTATIONS = [
    ("M1_before_total_off", lambda a: a["primary_ge2_count"].__setitem__("before_total", 139)),
    ("M2_after_total_off", lambda a: a["primary_ge2_count"].__setitem__("after_total", 157)),
    ("M3_mean_wrong", lambda a: a["primary_ge2_count"].__setitem__("mean_paired_delta", 0.5)),
    ("M4_ci_wrong", lambda a: a["primary_ge2_count"].__setitem__("ci95", [0.1, 0.2])),
    ("M5_w_off", lambda a: a["primary_ge2_count"].__setitem__("w", 10)),
    ("M6_share_wrong", lambda a: a["secondary_share_ge_2"].__setitem__("before", 0.9)),
    ("M7_verdict_flipped", lambda a: a["primary_ge2_count"].__setitem__("verdict", "RESOLVED")),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()

    art = json.loads(ART.read_text())
    ref = rederive()
    base = checks(art, ref)
    print(f"reference (independent re-derivation): {json.dumps(ref)}")
    for n, ok, d in base:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n:34s} {d}")
    npass = sum(1 for _, ok, _ in base if ok)
    print(f"  -> {npass}/{len(base)} PASS\n")

    if args.mutate:
        reddened = set()
        for name, fn in MUTATIONS:
            m = copy.deepcopy(art)
            fn(m)
            res = checks(m, ref)
            red = [n for n, ok, _ in res if not ok]
            reddened |= set(red)
            print(f"  {name}: reddens {red}")
        # M8 mutates an INPUT copy (V9 reads the inputs, so only an input mutation can redden it).
        global _AFTER_PATH
        doc = json.loads(AFTER.read_text())
        doc["queries"] = doc["queries"][:-1]          # drop one query from AFTER
        tmp = D / "_g3_after_mutation_tmp.json"
        tmp.write_text(json.dumps(doc))
        try:
            _AFTER_PATH = tmp
            res = checks(art, rederive())
            red = [n for n, ok, _ in res if not ok]
            reddened |= set(red)
            print(f"  M8_input_after_drops_a_query: reddens {red}")
        finally:
            _AFTER_PATH = AFTER
            tmp.unlink(missing_ok=True)
        allc = [n for n, _, _ in base]
        inert = sorted(set(allc) - reddened)
        print(f"\n  checks {len(allc)}  reddened {len(reddened)}  INERT: {inert or 'none'}")

    return 0 if npass == len(base) else 1


if __name__ == "__main__":
    raise SystemExit(main())
