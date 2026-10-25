#!/usr/bin/env python
"""§I74 — an INDEPENDENT stdlib aggregation over the raw per-query array of `ce_gvn.json`.

Written from the pre-registration's schema, NOT from the harness's code: it re-derives every
aggregate, contrast, CI, survival ratio and decision field **from `queries[]` alone** and diffs its
own numbers against the artifact's summary blocks. Those blocks are CLAIMS.

    uv run python logs/p1/step10/ce_gvn_verifier.py --check
    uv run python logs/p1/step10/ce_gvn_verifier.py --extract <path>
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ART = Path(__file__).resolve().parent / "ce_gvn.json"
KS = (20, 100, 500, 1000)
ARMS = ("qwen3", "nomic", "gemma")
STAGES = ("pre", "post")
I70_ROWS = {"qwen3": 0.293934, "nomic": 0.433930, "gemma": 0.480410}
RESOLUTION_FLOOR = 0.020


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
            "wlt": {"first_worse": sum(1 for d in diffs if d < 0),
                    "first_better": sum(1 for d in diffs if d > 0),
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

    # ── arms: every aggregate mean and its n ─────────────────────────────────────────────────
    arm_blocks = [("pre", art["arms"]["pre"]), ("post", art["arms"]["post"]),
                  ("i70", art["arms_i70_convention"])]
    for st, blk in arm_blocks:
        for a in ARMS:
            for key in ("c", "r"):
                block = "ceiling_norm" if key == "c" else "raw"
                for k in KS:
                    vals = [r[st][a][f"{key}{k}"] for r in rows
                            if r.get(st, {}).get(a, {}).get(f"{key}{k}") is not None]
                    cmp(f"arms.{st}.{a}.{block}.R@{k}", mean(vals), blk[a][block][f"R@{k}"])
                    cmp(f"arms.{st}.{a}.{block}.n_queries_{key}@{k}", len(vals),
                        blk[a][block][f"n_queries_{key}@{k}"])

    # ── the contrasts ────────────────────────────────────────────────────────────────────────
    def contrast(stage: str, first: str, second: str, key: str, k: int) -> dict:
        diffs = [r[stage][first][f"{key}{k}"] - r[stage][second][f"{key}{k}"]
                 for r in rows
                 if r.get(stage, {}).get(first, {}).get(f"{key}{k}") is not None
                 and r.get(stage, {}).get(second, {}).get(f"{key}{k}") is not None]
        return paired(diffs)

    prim = art["endpoints"]["primary_gemma_minus_nomic"]
    for st in STAGES:
        mine = contrast(st, "gemma", "nomic", "c", 20)
        theirs = prim[f"{st}_ceiling_norm_R@20"]
        for field in ("n", "mean", "sd", "ci95", "resolved", "wlt"):
            cmp(f"primary.{st}.{field}", mine[field], theirs[field])
    cmp("primary.post.raw_R@20", contrast("post", "gemma", "nomic", "r", 20)["mean"],
        prim["post_raw_R@20"]["mean"])
    cmp("primary.post.ceiling_norm_R@100", contrast("post", "gemma", "nomic", "c", 100)["mean"],
        prim["post_ceiling_norm_R@100"]["mean"])
    # ⚠️ The operand order is the LABEL's, not a convenience: "nomic_minus_qwen3" means
    # nomic − qwen3, which is +0.068311. Getting this backwards is what the first --check run
    # caught (it reported the sign-flipped value), which is the verifier doing its job.
    for label, first, second in (("context_gemma_minus_qwen3", "gemma", "qwen3"),
                                 ("context_nomic_minus_qwen3", "nomic", "qwen3")):
        cmp(f"{label}.post.ceiling_norm_R@20",
            contrast("post", first, second, "c", 20)["mean"],
            art["endpoints"][label]["post_ceiling_norm_R@20"]["mean"])

    # ── the decision, recomputed from the primary POST contrast ──────────────────────────────
    pre_d = contrast("pre", "gemma", "nomic", "c", 20)
    post_d = contrast("post", "gemma", "nomic", "c", 20)
    d = art["decision"]
    cmp("decision.pre_delta", pre_d["mean"], d["pre_delta"])
    cmp("decision.pre_ci", pre_d["ci95"], d["pre_ci"])
    cmp("decision.post_delta", post_d["mean"], d["post_delta"])
    cmp("decision.post_ci", post_d["ci95"], d["post_ci"])
    cmp("decision.post_n", post_d["n"], d["post_n"])
    cmp("decision.post_wlt", post_d["wlt"], d["post_wlt"])
    if pre_d["mean"] and post_d["mean"] is not None:
        cmp("decision.survival_ratio", round(post_d["mean"] / pre_d["mean"], 6),
            d["survival_ratio_post_over_pre"])
    if post_d["n"] and post_d["sd"] is not None:
        cmp("decision.resolution_floor_this_run",
            round(1.96 * post_d["sd"] / math.sqrt(post_d["n"]), 6),
            d["resolution_floor_this_run"])
    cmp("decision.reversal", bool(post_d["resolved"] and (post_d["mean"] or 0) < 0), d["reversal"])

    # the pre-registered rule, applied independently to the RECOMPUTED delta
    if post_d["resolved"] and (post_d["mean"] or 0) > RESOLUTION_FLOOR:
        want = "GEMMA"
    elif post_d["resolved"] and (post_d["mean"] or 0) <= RESOLUTION_FLOOR:
        want = "NOMIC"
    else:
        want = "NOMIC"
    cmp("decision.DISPOSITION_matches_the_rule", d["DISPOSITION"], want)

    # ── G1/G2 — the two anchors under §I70's convention ─────────────────────────────────────
    for a in ARMS:
        cmp(f"G_anchor.{a}.i70_convention.R@20",
            mean([r["i70"][a]["c20"] for r in rows if r["i70"][a].get("c20") is not None]),
            I70_ROWS[a])
    cmp("meta.pool_size", art["meta"]["pool_size"], 3489)
    cmp("meta.reachable_pages", art["meta"]["reachable_pages"], 888)

    # ── G3/G4/G5/G7 ─────────────────────────────────────────────────────────────────────────
    cmp("G3.n_order_changes",
        sum(1 for r in rows for a in ARMS if r["post"].get(a, {}).get("order_changed")),
        art["verifiers"]["G3_reranker_live_and_reordering"]["n_order_changes"])
    cmp("G4.n_identical",
        sum(1 for x in art["verifiers"]["G4_reranker_deterministic"]["rows"] if x.get("identical")),
        art["verifiers"]["G4_reranker_deterministic"]["n_identical"])
    cmp("G5.n_failures", art["verifiers"]["G5_failures_reported"]["n_failures"],
        len(art["verifiers"]["G5_failures_reported"]["failures"]))
    missing = [r["id"] for r in rows if any(a not in r["post"] for a in ARMS)]
    failed_ids = {f["id"] for f in art["verifiers"]["G5_failures_reported"]["failures"]}
    cmp("G5.every_missing_arm_has_a_recorded_failure", sorted(set(missing) - failed_ids), [])
    cmp("G7.ceiling_size", art["verifiers"]["G7_shared_page_mapping_and_alignment"]["ceiling_size"],
        888)

    # ── coverage ─────────────────────────────────────────────────────────────────────────────
    cmp("n_queries", len(rows), 133)
    cmp("every query has ALL THREE arms in the PRE stage",
        all(all(a in r["pre"] for a in ARMS) for r in rows), True)

    bad = [c for c in checks if not c[3]]
    if args.extract:
        pack = {
            "what": ("§I74 gemma-vs-nomic at the cross-encoder — reviewer extract. The RAW "
                     "per-query rows are the ground truth; recompute the aggregates yourself."),
            "preregistration": art["meta"]["preregistration"],
            "endpoint_and_rule": {
                "endpoint": ("paired ceiling-normalised R@20 POST-rerank, gemma@768 − nomic@768, "
                             "n=133"),
                "rule": ("delta > 0.020 and resolved -> gemma; 0 < delta <= 0.020 or unresolved -> "
                         "nomic; delta resolves negative -> nomic AND record the reversal"),
                "guards": ["G1 anchor: §I70 convention reproduces qwen3@1024 0.293934 exactly",
                           "G2 anchor: §I70 convention reproduces nomic@768 0.433930 exactly",
                           "G3 the rerank service is live and reordering",
                           "G4 the same list reranked twice is identical",
                           "G5 failures counted and reported, n stated",
                           "G6 A-vs-A for BOTH candidates, bit-identical",
                           "G7 one shared page map; ceiling 888; docs in cosine order"],
            },
            "scope": art["decision"]["scope"],
            "meta": art["meta"],
            "verifiers": art["verifiers"],
            "claims": {"arms": art["arms"], "arms_i70_convention": art["arms_i70_convention"],
                       "endpoints": art["endpoints"], "decision": art["decision"]},
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
