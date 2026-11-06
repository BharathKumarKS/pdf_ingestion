"""Independent stdlib verifier for RAPTOR-as-generator-context (§I113).

Re-derives EVERY aggregate and paired delta (mean / 95% CI / n / wins / losses / resolved) from the
artifact's RAW per-query arm scores, and re-checks G1-G7 against the raw data. It does NOT import the
harness.

Run:  .venv/bin/python logs/p1/step10/raptor_context_verifier.py
Exit: 0 = all checks pass.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ART = Path("logs/p1/step10/raptor_context.json")
I108_OVERVIEW_FAITHFULNESS = 0.5097   # the anchor (§I108, n=40)
METRICS = ("faithfulness", "answer_relevance", "citation_accuracy")


def paired(pq: list[dict], metric: str) -> dict:
    """Re-derive a paired delta exactly as the harness does, from the raw arm scores."""
    d = [r["B"][metric] - r["A"][metric] for r in pq
         if r["A"][metric] is not None and r["B"][metric] is not None]
    if len(d) < 2:
        return {"n": len(d), "mean": None, "ci": None, "resolved": False,
                "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0)}
    m = statistics.mean(d)
    half = 1.96 * statistics.stdev(d) / (len(d) ** 0.5)
    return {"n": len(d), "mean": m, "ci": [m - half, m + half],
            "resolved": (m - half > 0 or m + half < 0),
            "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0)}


def verify(art: dict) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    pq = art["per_query"]
    a = art["aggregates"]
    g = art["guards"]

    def chk(name, ok, detail=""):
        out.append((name, bool(ok), detail))

    # ---- aggregates re-derived from the per-query arm scores -------------------
    af = [r["A"]["faithfulness"] for r in pq if r["A"]["faithfulness"] is not None]
    bf = [r["B"]["faithfulness"] for r in pq if r["B"]["faithfulness"] is not None]
    chk("V1 A_faithfulness aggregate re-derived",
        a["A_faithfulness"] is not None and af
        and abs(statistics.mean(af) - a["A_faithfulness"]) <= 1e-9)
    chk("V2 B_faithfulness aggregate re-derived",
        a["B_faithfulness"] is not None and bf
        and abs(statistics.mean(bf) - a["B_faithfulness"]) <= 1e-9)

    # ---- paired deltas re-derived (mean / CI / n / wins / losses) --------------
    for metric in METRICS:
        want, got = paired(pq, metric), art["deltas"][metric]
        chk(f"V3.{metric} mean re-derived",
            want["n"] < 2 and got["mean"] is None
            or want["mean"] is not None and abs(want["mean"] - got["mean"]) <= 1e-9)
        chk(f"V4.{metric} 95% CI re-derived",
            want["ci"] is None and got["ci"] is None
            or want["ci"] is not None and got["ci"] is not None
            and abs(want["ci"][0] - got["ci"][0]) <= 1e-9
            and abs(want["ci"][1] - got["ci"][1]) <= 1e-9)
        chk(f"V5.{metric} n / wins / losses re-derived",
            want["n"] == got["n"] and want["wins"] == got["wins"]
            and want["losses"] == got["losses"])
        # a RESOLVED verdict must match its own CI
        lo, hi = got["ci"] if got["ci"] is not None else (0.0, 0.0)
        chk(f"V6.{metric} resolved flag matches the CI",
            bool(got["resolved"]) == (lo > 0 or hi < 0))

    # ---- guards re-checked against the raw data --------------------------------
    chk("V7 G1 population 40 ovw-*",
        g["G1_population_40"] == (len(pq) == 40
                                  and all(r["id"].startswith("ovw-") and r["n_relevant"] > 0 for r in pq)))
    chk("V8 G2 zero errors", g["G2_zero_errors"] == (len(art["errors"]) == 0))
    chk("V9 G3 pages identical between arms",
        g["G3_pages_identical_between_arms"] == all(r["page_list_A"] == r["page_list_B"] for r in pq))
    chk("V10 G4 summaries pageless and absent from the page list",
        g["G4_summaries_are_pageless_and_absent"] == all(
            not r["summaries_have_page"] and not (set(r["summary_ids"]) & set(r["page_list_A"]))
            for r in pq))
    chk("V11 G5 judge cross-family",
        g["G5_judge_cross_family"] == (art["meta"]["judge"] != art["meta"]["generator"]))
    chk("V12 G6 arm A reproduces the I108 baseline",
        g["G6_armA_reproduces_I108_baseline"] == (
            bool(af) and abs(statistics.mean(af) - I108_OVERVIEW_FAITHFULNESS) <= 0.030))
    chk("V13 G7 attachment deterministic",
        g["G7_attachment_deterministic"] == all(r["summary_determinism_ok"] for r in pq))

    # ---- internal consistency of the per-query record --------------------------
    chk("V14 n_summaries matches len(summary_ids) and the meta count",
        all(r["n_summaries"] == len(r["summary_ids"]) == art["meta"]["n_summaries"] for r in pq))
    chk("V15 page lists are distinct pages",
        all(len(set(r["page_list_A"])) == len(r["page_list_A"])
            and len(set(r["page_list_B"])) == len(r["page_list_B"]) for r in pq))
    chk("V16 summary ids are distinct within a query",
        all(len(set(r["summary_ids"])) == len(r["summary_ids"]) for r in pq))
    return out


def main() -> int:
    art = json.loads(ART.read_text())
    res = verify(art)
    npass = sum(1 for _, ok, _ in res if ok)
    for name, ok, detail in res:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))
    print(f"\n{npass}/{len(res)} checks PASS")
    return 0 if npass == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
