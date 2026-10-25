#!/usr/bin/env python
"""Independent aggregation for the embedder screen (§1 of the 2026-10-24 plan).

Deliberately written as a SECOND implementation, not a reuse of `embedder_screen.py`'s helpers:
stdlib only (no numpy), different code shape, and it reads ONLY the raw per-query array — never the
artifact's own summary blocks. That is what makes it evidence rather than a re-print.

Two modes:

  --write-extract OUT   build the reviewer pack from the artifact (raw per-query array + meta only;
                        the author's aggregates, endpoints, decision and verifiers are EXCLUDED, so
                        a reviewer must recompute rather than compare a summary against itself).
  --extract IN          recompute every aggregate and every endpoint from the raw array and print
                        one JSON object.
  --check IN            recompute AND diff against the artifact's own summary blocks, printing a
                        per-field match/mismatch list. Every number the register quotes must
                        re-derive here.

Run:
    python3 logs/p1/step10/embedder_screen_verifier.py --check logs/p1/step10/embedder_screen.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

KS = (20, 100, 500, 1000)
BASELINES = ("qwen3@1024", "nomic@768")


def mean(xs):
    return sum(xs) / len(xs)


def paired(diffs):
    """Mean, sample SD (ddof=1), 95 % CI half-width = 1.96*sd/sqrt(n), W/L/T. Stdlib only."""
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None, "wlt": None}
    m = mean(diffs)
    sd = math.sqrt(sum((d - m) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    lo, hi = m - half, m + half
    return {
        "n": n, "mean": round(m, 6), "sd": round(sd, 6),
        "ci95": [round(lo, 6), round(hi, 6)],
        "resolved": bool(lo > 0 or hi < 0),
        "direction": "cand>base" if lo > 0 else ("cand<base" if hi < 0 else "straddles 0"),
        "wlt": {"cand_worse": sum(1 for d in diffs if d < 0),
                "cand_better": sum(1 for d in diffs if d > 0),
                "tie": sum(1 for d in diffs if d == 0)},
    }


def load_extract(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d


def recompute(ext: dict) -> dict:
    """Every aggregate + every endpoint, from the raw per-query array only."""
    rows = ext["queries"]
    arms = ext["arms"]
    keys = [("c", "ceiling_norm"), ("r", "raw")]
    aggs = {}
    for arm in arms:
        aggs[arm] = {}
        for key, label in keys:
            for k in KS:
                vals = [r["a"][arm][f"{key}{k}"] for r in rows
                        if arm in r["a"] and r["a"][arm].get(f"{key}{k}") is not None]
                aggs[arm].setdefault(label, {})[f"R@{k}"] = round(mean(vals), 6) if vals else None
    endpoints = {}
    for arm in arms:
        if arm in BASELINES:
            continue
        endpoints[arm] = {}
        for base in BASELINES:
            for key, label in keys:
                for k in KS:
                    diffs = [r["a"][arm][f"{key}{k}"] - r["a"][base][f"{key}{k}"] for r in rows
                             if arm in r["a"] and base in r["a"]
                             and r["a"][arm].get(f"{key}{k}") is not None
                             and r["a"][base].get(f"{key}{k}") is not None]
                    endpoints[arm][f"{label}_R@{k}_vs_{base}"] = paired(diffs)
    decision = {}
    for arm in arms:
        if arm in BASELINES:
            continue
        eq = endpoints[arm]["ceiling_norm_R@20_vs_qwen3@1024"]
        en = endpoints[arm]["ceiling_norm_R@20_vs_nomic@768"]
        decision[arm] = {
            "beats_qwen3": bool(eq["resolved"] and eq["mean"] > 0),
            "beats_nomic": bool(en["resolved"] and en["mean"] > 0),
        }
        decision[arm]["PASSES_the_rule"] = decision[arm]["beats_qwen3"] and decision[arm]["beats_nomic"]
    return {"arms": aggs, "endpoints": endpoints, "decision": decision,
            "n_queries": len(rows), "n_arms": len(arms)}


def diff_report(recomputed: dict, artifact: dict) -> dict:
    """Field-by-field: does the artifact's own summary re-derive from its raw per-query array?"""
    bad = []
    for arm, blocks in recomputed["arms"].items():
        for label, vals in blocks.items():
            for k, v in vals.items():
                got = artifact["arms"][arm][label][k]
                if got != v:
                    bad.append(f"arms.{arm}.{label}.{k}: artifact={got} recomputed={v}")
    for arm, eps in recomputed["endpoints"].items():
        for name, v in eps.items():
            got = artifact["endpoints"][arm][name]
            for f in ("n", "mean", "sd", "ci95", "resolved", "direction", "wlt"):
                if got[f] != v[f]:
                    bad.append(f"endpoints.{arm}.{name}.{f}: artifact={got[f]} recomputed={v[f]}")
    for arm, d in recomputed["decision"].items():
        for f in ("beats_qwen3", "beats_nomic", "PASSES_the_rule"):
            if artifact["decision"][arm][f] != d[f]:
                bad.append(f"decision.{arm}.{f}: artifact={artifact['decision'][arm][f]} recomputed={d[f]}")
    return {"n_mismatches": len(bad), "mismatches": bad[:50], "pass": len(bad) == 0}


def write_extract(artifact: dict, out: Path) -> dict:
    """Reviewer pack: meta + the RAW per-query array, compact. No author aggregates."""
    keep = ("c20", "c100", "c500", "c1000", "r20", "r100", "r500", "r1000")
    rows = []
    for r in artifact["queries"]:
        rows.append({
            "id": r["id"], "t": r["query_type"],
            "n_rel": r["n_relevant"], "n_reach": r["n_reachable"],
            "a": {arm: {k: v.get(k) for k in keep} for arm, v in r["arms"].items()},
        })
    ext = {
        "meta": artifact["meta"],
        "arms": artifact["meta"]["arms"],
        "baselines": artifact["meta"]["baselines"],
        "ks": list(KS),
        "note": ("raw per-query arm scores only. c{k} = ceiling-normalised R@k (the endpoint family), "
                 "r{k} = raw R@k. The artifact's aggregates/endpoints/decision/verifiers are "
                 "deliberately NOT included — recompute them."),
        "queries": rows,
    }
    out.write_text(json.dumps(ext, separators=(",", ":")) + "\n", encoding="utf-8")
    return ext


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-extract", metavar="OUT")
    ap.add_argument("--extract", metavar="IN")
    ap.add_argument("--check", metavar="ARTIFACT")
    args = ap.parse_args()

    if args.write_extract:
        art = json.loads(Path(args.check or "logs/p1/step10/embedder_screen.json")
                         .read_text(encoding="utf-8"))
        ext = write_extract(art, Path(args.write_extract))
        print(f"wrote {args.write_extract}  ({len(ext['queries'])} queries, "
              f"{len(ext['arms'])} arms)")
        return 0

    if args.extract:
        print(json.dumps(recompute(load_extract(Path(args.extract))), indent=2, sort_keys=True))
        return 0

    if args.check:
        art = json.loads(Path(args.check).read_text(encoding="utf-8"))
        rec = recompute({"queries": [{"id": r["id"], "a": r["arms"]} for r in art["queries"]],
                         "arms": art["meta"]["arms"]})
        rep = diff_report(rec, art)
        print(json.dumps({"n_queries": rec["n_queries"], "n_arms": rec["n_arms"],
                          "recomputed_ceiling_norm_R@20": {a: rec["arms"][a]["ceiling_norm"]["R@20"]
                                                           for a in rec["arms"]},
                          "recomputed_decision": rec["decision"],
                          "diff": rep}, indent=2, sort_keys=True))
        return 0 if rep["pass"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
