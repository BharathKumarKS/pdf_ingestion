#!/usr/bin/env python
"""§I71 — an INDEPENDENT stdlib aggregation over the raw per-query array of `chunk_filter_ab.json`.

Written from the pre-registration's schema, NOT from the harness's code: it re-derives every
aggregate, endpoint and decision field **from `queries[]` alone** and diffs its own numbers against
the artifact's summary blocks. The harness's `arms` / `endpoints` / `decision` blocks are treated as
CLAIMS, never as ground truth.

⚠️ The reviewer gets the EXTRACT this script writes (`--extract`), which carries the raw per-query
rows and the claims — never the artifact whole (a 500 KB read truncated a tool-using reviewer once).

    uv run python logs/p1/step10/chunk_filter_ab_verifier.py --check
    uv run python logs/p1/step10/chunk_filter_ab_verifier.py --extract <path>
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ART = Path(__file__).resolve().parent / "chunk_filter_ab.json"

KS = (20, 100, 500, 1000)
EMBEDDERS = ("gemma", "qwen3")
ARMS = ("C", "T")


def mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 6) if xs else None


def paired(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None, "wlt": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "mean": round(m, 6),
        "sd": round(sd, 6),
        "ci95": [round(m - half, 6), round(m + half, 6)],
        "resolved": bool((m - half) > 0 or (m + half) < 0),
        "wlt": {"T_worse": sum(1 for d in diffs if d < 0),
                "T_better": sum(1 for d in diffs if d > 0),
                "tie": sum(1 for d in diffs if d == 0)},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--extract", default=None)
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    rows = art["queries"]
    checks: list[tuple[str, object, object, bool]] = []

    def cmp(name: str, mine, theirs) -> None:
        ok = (mine == theirs)
        if isinstance(mine, float) and isinstance(theirs, float):
            ok = abs(mine - theirs) < 1e-9
        checks.append((name, mine, theirs, ok))

    # ── arms: recompute every aggregate mean and its n from queries[] ─────────────────────────
    for arm in ARMS:
        for e in EMBEDDERS:
            for key in ("c", "r"):
                for k in KS:
                    vals = [r["arms"][arm][e][f"{key}{k}"] for r in rows
                            if r["arms"].get(arm, {}).get(e, {}).get(f"{key}{k}") is not None]
                    block = "ceiling_norm" if key == "c" else "raw"
                    cmp(f"arms.{arm}.{e}.{block}.R@{k}", mean(vals),
                        art["arms"][arm][e][block][f"R@{k}"])
                    cmp(f"arms.{arm}.{e}.{block}.n_queries_{key}@{k}", len(vals),
                        art["arms"][arm][e][block][f"n_queries_{key}@{k}"])

    # ── endpoints: recompute every paired T−C contrast ────────────────────────────────────────
    for e in EMBEDDERS:
        for key in ("c", "r"):
            label = "ceiling_norm" if key == "c" else "raw"
            for k in KS:
                diffs = [r["arms"]["T"][e][f"{key}{k}"] - r["arms"]["C"][e][f"{key}{k}"]
                         for r in rows
                         if r["arms"].get("T", {}).get(e, {}).get(f"{key}{k}") is not None
                         and r["arms"].get("C", {}).get(e, {}).get(f"{key}{k}") is not None]
                mine = paired(diffs)
                theirs = art["endpoints"][e][f"{label}_R@{k}_T_minus_C"]
                for field in ("n", "mean", "sd", "ci95", "resolved", "wlt"):
                    cmp(f"endpoints.{e}.{label}.R@{k}.{field}", mine[field], theirs[field])

    # ── the decision block, recomputed from the PRIMARY endpoint ─────────────────────────────
    prim = art["endpoints"]["gemma"]["ceiling_norm_R@20_T_minus_C"]
    d = art["decision"]
    cmp("decision.delta", prim["mean"], d["delta"])
    cmp("decision.ci95", prim["ci95"], d["ci95"])
    cmp("decision.n", prim["n"], d["n"])
    cmp("decision.ATTRIBUTABLE", bool(prim["resolved"]), bool(d["ATTRIBUTABLE"]))
    cmp("decision.wlt", prim["wlt"], d["wlt"])
    if prim["n"] and prim["sd"] is not None:
        cmp("decision.resolution_floor_n133",
            round(1.96 * prim["sd"] / math.sqrt(prim["n"]), 6), d["resolution_floor_n133"])

    # ── the pool partition and the bands (guards C2 / C4), re-derived from the artifact ───────
    v = art["verifiers"]
    c2 = v["C2_pool_partition_and_bands"]
    cmp("C2.pool_C - flagged_in_pool == pool_T",
        c2["pool_C"] - c2["flagged_in_pool"] == c2["pool_T"], True)
    cmp("C2.T_equals_C_minus_flagged", c2["T_equals_C_minus_flagged"], True)
    cmp("C2.pool_C == 3489", c2["pool_C"], 3489)
    cmp("C2.flagged_in_pool == 19", c2["flagged_in_pool"], 19)
    cmp("C2.pool_T == 3470", c2["pool_T"], 3470)
    for band, registered in (("toc", 72), ("index", 186), ("front_matter", 5)):
        cmp(f"C2.corpus_band.{band}", c2["corpus_bands"][band]["this_run"], registered)
    cmp("C2.corpus_flagged == 263", c2["corpus_flagged"], 263)
    cmp("C2.corpus_flagged_out_of_window == 244", c2["corpus_flagged_out_of_window"], 244)
    cmp("C2.in_window + out_of_window == corpus chunks",
        c2["corpus_window_split"]["in_window"] + c2["corpus_window_split"]["out_of_window"], 3796)
    cmp("C2.flagged split sums to the corpus flagged",
        c2["corpus_window_split"].get("flagged_in_window", 0)
        + c2["corpus_window_split"].get("flagged_out_of_window", 0), 263)
    cmp("C2.in-pool flagged == flagged_in_window",
        c2["flagged_in_pool"], c2["corpus_window_split"].get("flagged_in_window"))
    c4 = v["C4_treatment_from_text_not_column"]
    cmp("C4.flagged_from_text == 19", c4["flagged_from_text"], 19)
    cmp("C4.corpus_flagged_from_text == 263", c4["corpus_flagged_from_text"], 263)
    cmp("C4.stored_False == 5", c4["stored_is_content_False"], 5)
    cmp("C4.19 != 5", c4["flagged_from_text"] != c4["stored_is_content_False"], True)
    x1 = v["X1_pool_pages_eq_reachable_pages"]
    cmp("X1.reachable_pages == 888", x1["reachable_pages_sqlite"], 888)
    cmp("X1.pool pages == sqlite pages", x1["pages_in_pool_C"], x1["reachable_pages_sqlite"])

    # ── C1: the registered §I70 row, re-diffed against the RECOMPUTED arm-C aggregate ─────────
    i70 = {"R@20": 0.293934, "R@100": 0.569074, "R@500": 0.922982, "R@1000": 1.0}
    recomputed_c = {k: mean([r["arms"]["C"]["qwen3"][f"c{k[2:]}"] for r in rows
                             if r["arms"]["C"]["qwen3"].get(f"c{k[2:]}") is not None])
                    for k in i70}
    for k, want in i70.items():
        cmp(f"C1.recomputed_armC_qwen3.{k}", recomputed_c[k], want)

    # ── chunk_stats, recomputed ──────────────────────────────────────────────────────────────
    cs = art["meta"]["chunk_stats"]
    cmp("chunk_stats.chunks_per_page_C",
        round(cs["n_chunks_C"] / cs["pages_C"], 4), cs["chunks_per_page_C"])
    cmp("chunk_stats.chunks_per_page_T",
        round(cs["n_chunks_T"] / cs["pages_T"], 4), cs["chunks_per_page_T"])
    cmp("chunk_stats.n_chunks_C == pool_C", cs["n_chunks_C"], c2["pool_C"])
    cmp("chunk_stats.n_chunks_T == pool_T", cs["n_chunks_T"], c2["pool_T"])

    # ── the query count, and that no query is silently missing from an arm ───────────────────
    cmp("n_queries", len(rows), 133)
    cmp("every query has both arms x both embedders",
        all(all(e in r["arms"][a] for a in ARMS for e in EMBEDDERS) for r in rows), True)
    cmp("C5.n_queries", v["C5_empty_ceiling_reported"]["n_queries"], len(rows))
    cmp("C5.no_query_dropped_silently",
        v["C5_empty_ceiling_reported"]["queries_dropped_silently"], [])

    bad = [c for c in checks if not c[3]]
    if args.extract:
        pack = {
            "what": ("§I71 chunk-filter A/B — reviewer extract. The RAW per-query rows are the "
                     "ground truth; recompute the aggregates yourself, do not take the summary's "
                     "word for it."),
            "preregistration": art["meta"]["preregistration"],
            "preregistration_commit": art["meta"]["preregistration_commit"],
            "endpoint_and_rule": {
                "endpoint": art["meta"]["endpoint"],
                "rule": art["meta"]["preregistered_rule"],
                "guards": ["C1 arm C reproduces §I70's qwen3@1024 row EXACTLY",
                           "C2 treatment pool == C minus flagged; flagged == 263; bands 72/186/5",
                           "C3 A-vs-A: arm C byte-identical on a re-embed at another batch size",
                           "C4 built from the TEXT, not the stored is_content (263, not 5)",
                           "C5 empty-ceiling queries reported, never dropped",
                           "C6 one shared chunk->page mapping"],
            },
            "meta": art["meta"],
            "verifiers": art["verifiers"],
            "claims": {"arms": art["arms"], "endpoints": art["endpoints"],
                       "decision": art["decision"]},
            "independent_aggregation": {
                "n_checks": len(checks),
                "n_mismatch": len(bad),
                "mismatches": [{"check": b[0], "recomputed": b[1], "artifact": b[2]} for b in bad],
            },
            "queries": rows,
        }
        Path(args.extract).write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
        print(f"wrote extract {args.extract}")

    print(f"independent aggregation: {len(checks)} checks, {len(bad)} mismatch(es)")
    for name, mine, theirs, ok in bad:
        print(f"  MISMATCH {name}: recomputed={mine!r} artifact={theirs!r}")
    if not bad:
        for name, mine, _, _ in checks[:6]:
            print(f"  ok  {name} = {mine!r}")
        print(f"  … {len(checks) - 6} more all match")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
