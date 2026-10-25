#!/usr/bin/env python
"""§I72 — an INDEPENDENT stdlib aggregation over the raw per-query array of `ce_survival.json`.

Written from the pre-registration's schema, NOT from the harness's code: it re-derives every
aggregate, every contrast, the survival ratio and the decision **from `queries[]` alone** and diffs
its own numbers against the artifact's summary blocks. Those blocks are treated as CLAIMS.

⚠️ The reviewer gets the EXTRACT (`--extract`), never the artifact whole.

    uv run python logs/p1/step10/ce_survival_verifier.py --check
    uv run python logs/p1/step10/ce_survival_verifier.py --extract <path>
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ART = Path(__file__).resolve().parent / "ce_survival.json"
KS = (20, 100, 500, 1000)
EMBEDDERS = ("qwen3", "gemma")
STAGES = ("pre", "post")
I70_QWEN3_1024_R20 = 0.293934
I70_GEMMA_768_R20 = 0.480410


def mean(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 6) if xs else None


def paired(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None, "wlt": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(m - half, 6), round(m + half, 6)],
            "resolved": bool((m - half) > 0 or (m + half) < 0),
            "wlt": {"gemma_worse": sum(1 for d in diffs if d < 0),
                    "gemma_better": sum(1 for d in diffs if d > 0),
                    "tie": sum(1 for d in diffs if d == 0)}}


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
        ok = mine == theirs
        if isinstance(mine, float) and isinstance(theirs, float):
            ok = abs(mine - theirs) < 1e-9
        checks.append((name, mine, theirs, ok))

    # ── every aggregate mean and its n, recomputed from queries[] ─────────────────────────────
    # `i70` lives under its own top-level key because it is a DIFFERENT convention, not a stage.
    arm_blocks = [("pre", art["arms"]["pre"]), ("post", art["arms"]["post"]),
                  ("i70", art["arms_i70_convention"])]
    for st, blk in arm_blocks:
        for e in EMBEDDERS:
            for key in ("c", "r"):
                block = "ceiling_norm" if key == "c" else "raw"
                for k in KS:
                    vals = [r[st][e][f"{key}{k}"] for r in rows
                            if r.get(st, {}).get(e, {}).get(f"{key}{k}") is not None]
                    cmp(f"arms.{st}.{e}.{block}.R@{k}", mean(vals), blk[e][block][f"R@{k}"])
                    cmp(f"arms.{st}.{e}.{block}.n_queries_{key}@{k}", len(vals),
                        blk[e][block][f"n_queries_{key}@{k}"])

    # ── the contrasts, recomputed ─────────────────────────────────────────────────────────────
    def contrast(stage: str, key: str, k: int) -> dict:
        diffs = [r[stage]["gemma"][f"{key}{k}"] - r[stage]["qwen3"][f"{key}{k}"]
                 for r in rows
                 if r.get(stage, {}).get("gemma", {}).get(f"{key}{k}") is not None
                 and r.get(stage, {}).get("qwen3", {}).get(f"{key}{k}") is not None]
        return paired(diffs)

    for st in STAGES:
        for key in ("c", "r"):
            mine = contrast(st, key, 20)
            theirs = art["endpoints"][st][f"{'ceiling_norm' if key == 'c' else 'raw'}"
                                           f"_R@20_gemma_minus_qwen3"]
            for field in ("n", "mean", "sd", "ci95", "resolved", "wlt"):
                cmp(f"endpoints.{st}.{key}R@20.{field}", mine[field], theirs[field])
    cmp("endpoints.post.ceiling_norm_R@100",
        contrast("post", "c", 100)["mean"],
        art["endpoints"]["post"]["ceiling_norm_R@100_gemma_minus_qwen3"]["mean"])

    # ── the decision block, recomputed ────────────────────────────────────────────────────────
    pre_d = contrast("pre", "c", 20)
    post_d = contrast("post", "c", 20)
    d = art["decision"]
    cmp("decision.pre_delta", pre_d["mean"], d["pre_delta"])
    cmp("decision.pre_ci", pre_d["ci95"], d["pre_ci"])
    cmp("decision.post_delta", post_d["mean"], d["post_delta"])
    cmp("decision.post_ci", post_d["ci95"], d["post_ci"])
    cmp("decision.post_n", post_d["n"], d["post_n"])
    cmp("decision.post_wlt", post_d["wlt"], d["post_wlt"])
    cmp("decision.SURVIVES", bool(post_d["resolved"] and (post_d["mean"] or 0) > 0),
        bool(d["SURVIVES"]))
    if pre_d["mean"] and post_d["mean"] is not None:
        cmp("decision.survival_ratio_post_over_pre",
            round(post_d["mean"] / pre_d["mean"], 6), d["survival_ratio_post_over_pre"])
    if post_d["n"] and post_d["sd"] is not None:
        cmp("decision.resolution_floor_n133",
            round(1.96 * post_d["sd"] / math.sqrt(post_d["n"]), 6), d["resolution_floor_n133"])

    # ── S1′(a): the §I70 CONVENTION must reproduce §I70's two registered rows ────────────────
    for e, want in (("qwen3", I70_QWEN3_1024_R20), ("gemma", I70_GEMMA_768_R20)):
        cmp(f"S1prime.a.i70_convention.{e}.R@20",
            mean([r["i70"][e]["c20"] for r in rows if r["i70"][e].get("c20") is not None]), want)
        # ...and the two conventions are genuinely DIFFERENT numbers, which is the whole reason
        # the first run was void. If these ever coincide the harness has collapsed them.
        cmp(f"S1prime.b.contrast_convention.{e}.R@20",
            mean([r["pre"][e]["c20"] for r in rows if r["pre"][e].get("c20") is not None]),
            art["verifiers"]["S1prime_instrument_is_I70s"]["b_contrast_convention"][
                f"pre_{e}_R@20"])
    cmp("S1prime.conventions_differ_on_qwen3",
        mean([r["i70"]["qwen3"]["c20"] for r in rows if r["i70"]["qwen3"].get("c20") is not None])
        != mean([r["pre"]["qwen3"]["c20"] for r in rows if r["pre"]["qwen3"].get("c20") is not None]),
        True)
    cmp("S1.pool_size", art["meta"]["pool_size"], 3489)
    cmp("S1.reachable_pages", art["meta"]["reachable_pages"], 888)

    # ── S2/S3/S4/S6, re-derived from the rows ────────────────────────────────────────────────
    cmp("S2.n_order_changes", sum(1 for r in rows for e in EMBEDDERS
                                  if r["post"].get(e, {}).get("order_changed")),
        art["verifiers"]["S2_reranker_live_and_reordering"]["n_order_changes"])
    cmp("S3.n_identical", sum(1 for x in art["verifiers"]["S3_reranker_deterministic"]["rows"]
                              if x.get("identical")),
        art["verifiers"]["S3_reranker_deterministic"]["n_identical"])
    cmp("S4.n_failures", art["verifiers"]["S4_failures_reported"]["n_failures"],
        len(art["verifiers"]["S4_failures_reported"]["failures"]))
    missing = [r["id"] for r in rows if any(e not in r["post"] for e in EMBEDDERS)]
    failed_ids = {f["id"] for f in art["verifiers"]["S4_failures_reported"]["failures"]}
    cmp("S4.every_missing_arm_has_a_recorded_failure",
        sorted(set(missing) - failed_ids), [])
    cmp("S6.ceiling_size", art["verifiers"]["S6_shared_page_mapping_and_alignment"]["ceiling_size"],
        888)

    # ── coverage: no query silently absent from a stage ──────────────────────────────────────
    cmp("n_queries", len(rows), 133)
    cmp("every query has BOTH embedders in the PRE stage",
        all(all(e in r["pre"] for e in EMBEDDERS) for r in rows), True)

    bad = [c for c in checks if not c[3]]
    if args.extract:
        pack = {
            "what": ("§I72 cross-encoder survival test — reviewer extract. The RAW per-query rows "
                     "are the ground truth; recompute the aggregates yourself."),
            "preregistration": art["meta"]["preregistration"],
            "endpoint_and_rule": {
                "endpoint": "paired ceiling-normalised R@20 POST-rerank, gemma@768 − qwen3@1024, n=133",
                "rule": "the bet SURVIVES iff the POST delta is > 0 with a 95% CI excluding 0",
                "guards": ["S1 PRE reproduces §I70's qwen3@1024 0.293934 and gemma@768 0.480410",
                           "S2 the rerank service is live and reordering",
                           "S3 the same list reranked twice is identical (determinism)",
                           "S4 failures counted and reported, n stated",
                           "S5 A-vs-A gemma re-embed bit-identical",
                           "S6 one shared chunk->page map; ceiling 888; docs in cosine order"],
            },
            "scope": art["decision"]["scope"],
            "meta": art["meta"],
            "verifiers": art["verifiers"],
            "claims": {"arms": art["arms"], "endpoints": art["endpoints"],
                       "decision": art["decision"]},
            "independent_aggregation": {
                "n_checks": len(checks), "n_mismatch": len(bad),
                "mismatches": [{"check": b[0], "recomputed": b[1], "artifact": b[2]} for b in bad],
            },
            "queries": rows,
        }
        Path(args.extract).write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
        print(f"wrote extract {args.extract}")

    print(f"independent aggregation: {len(checks)} checks, {len(bad)} mismatch(es)")
    for name, mine, theirs, _ in bad:
        print(f"  MISMATCH {name}: recomputed={mine!r} artifact={theirs!r}")
    if not bad:
        for name, mine, _, _ in checks[:6]:
            print(f"  ok  {name} = {mine!r}")
        print(f"  … {len(checks) - 6} more all match")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
