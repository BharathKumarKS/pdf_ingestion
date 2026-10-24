#!/usr/bin/env python
"""§I66 — the verifier for the downstream-widths A/B.

Two halves, deliberately kept apart (the repo's standing rule — "mechanical evidence, not a second
opinion"):

  (a) an INDEPENDENT re-aggregation of the artifact's own per-query array, written to a different
      structure than the harness's `summarise()` so it is a re-derivation and not a re-run of the
      same code path, plus every guard check E2/E3/E4/E5/E6/E7/E8/E9; and
  (b) a compact reviewer extract (`--extract`) carrying the claims and the per-query rows, to be
      handed to the cross-family reviewer WITH the run (pre-registration §9).

Usage:
    unset PYTHONPATH
    uv run python logs/p1/step10/downstream_widths_verifier.py            # re-derive + check guards
    uv run python logs/p1/step10/downstream_widths_verifier.py --extract  # write the reviewer pack
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ART = REPO / "logs/p1/step10/downstream_widths_ab.json"
PACK = REPO / "logs/p1/step10/downstream_widths_verifier_rows.json"

ARMS = ("C", "W1", "W2", "L1", "L2", "N")
TREATMENT_REF = {"W1": "C", "W2": "C", "L1": "W2", "L2": "W2"}
TREATMENTS = tuple(TREATMENT_REF)
PRIMARY = {"W1": "width", "L1": "cut"}
METRICS = ("recall_at_top_k_ceiling_norm", "recall_at_top_k", "recall_at_pool",
           "hit_at_top_k", "ndcg_at_top_k", "mrr", "context_precision")
K_TOP = 20


def _mean(xs):
    return round(statistics.mean(xs), 6) if xs else None


def _paired(treat_vals, ctrl_vals):
    d = [t - c for t, c in zip(treat_vals, ctrl_vals) if t is not None and c is not None]
    if not d:
        return {"n": 0, "mean": None, "ci95": None, "resolved": None}
    m = statistics.mean(d)
    sd = statistics.stdev(d) if len(d) > 1 else 0.0
    half = 1.96 * sd / math.sqrt(len(d)) if len(d) > 1 else 0.0
    return {"n": len(d), "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(m - half, 6), round(m + half, 6)],
            "resolved": bool((m - half) > 0 or (m + half) < 0)}


def verify(path: Path) -> int:
    art = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in art["queries"] if "error" not in r]
    stored = art["summary"]
    fails: list[str] = []

    # E3 — the query count in every arm
    if art["meta"]["n_queries"] != len(rows):
        fails.append(f"E3: meta n_queries {art['meta']['n_queries']} != {len(rows)} non-errored rows")
    if art["meta"]["n_queries_errored"]:
        fails.append(f"E3: {art['meta']['n_queries_errored']} errored queries (named in the artifact)")
    for r in rows:
        if set(r["arms"]) != set(ARMS):
            fails.append(f"E3: {r['id']} is missing an arm: {sorted(r['arms'])}")

    # E2 — the control arm's settings are the shipped ones
    shipped = art["meta"]["shipped"]
    for r in rows:
        s = r["arms"]["C"]["settings"]
        if (s["W"], s["L"], s["da_fetch_k"]) != (shipped["W"], shipped["L"], shipped["da_fetch_k"]):
            fails.append(f"E2: {r['id']} control settings {s} != shipped {shipped}")

    # E8/E9 — the DA lane and the 64d prefetch are pinned across every arm
    da_vals = {r["arms"][t]["settings"]["da_fetch_k"] for r in rows for t in ARMS}
    pf_vals = {r["arms"][t]["settings"]["prefetch"] for r in rows for t in ARMS}
    if da_vals != {100}:
        fails.append(f"E8: da_fetch_k moved: {sorted(da_vals)}")
    if pf_vals != {2000}:
        fails.append(f"E9: prefetch moved: {sorted(pf_vals)}")

    # E4' — the negative control is bit-exact ON THE METRICS; diagnostics reported, not voiding
    # (re-registration §8 E4'; IMPROVEMENTS.md §I67: Qdrant's server-side RRF fusion is
    # non-deterministic and can move n_pool on a minority of queries without moving any metric).
    mism = 0
    diag = 0
    max_abs = 0.0
    for r in rows:
        for k, cv in r["arms"]["C"].items():
            if k == "settings":
                continue
            nv = r["arms"]["N"].get(k)
            if cv is None and nv is None:
                continue
            if k in ("n_pool", "n_pages", "rerank_fallback", "da_hits"):
                if cv != nv:
                    diag += 1
                continue
            if cv is None or nv is None or abs(cv - nv) > 1e-12:
                mism += 1
            else:
                max_abs = max(max_abs, abs(cv - nv))
    if mism:
        fails.append(f"E4': negative control is NOT bit-exact on the METRICS ({mism} mismatches, "
                     f"max_abs {max_abs}) — the A/B is VOID")

    # E5 — re-derive the aggregates independently and compare to the stored summary
    derived = {}
    for metric in METRICS:
        for t in ARMS:
            derived[f"{metric}__{t}"] = _mean(
                [r["arms"][t][metric] for r in rows if r["arms"][t][metric] is not None])
        for t in TREATMENTS:
            ref = TREATMENT_REF[t]
            derived[f"{metric}__delta_{t}_minus_{ref}"] = _paired(
                [r["arms"][t][metric] for r in rows], [r["arms"][ref][metric] for r in rows])
    for k, v in derived.items():
        if json.dumps(v, sort_keys=True) != json.dumps(stored["all_queries"].get(k), sort_keys=True):
            fails.append(f"E5: {k} re-derived {v} != stored {stored['all_queries'].get(k)}")

    # E6 — fallbacks counted and named per arm
    fb = stored["all_queries"]["queries_with_reranker_fallback"]
    fb_recount = {t: sum(1 for r in rows if r["arms"][t]["rerank_fallback"]) for t in ARMS}
    if fb != fb_recount:
        fails.append(f"E6: fallback counts {fb} != recounted {fb_recount}")

    # E7 — the cut can move, and the width arms' pools grow
    pool_med = {t: statistics.median(r["arms"][t]["n_pool"] for r in rows) for t in ARMS}
    if not (pool_med["C"] > K_TOP):
        fails.append(f"E7: control pool median {pool_med['C']} <= top-20 cut — metric inert")
    if not (pool_med["W1"] > pool_med["C"] and pool_med["W2"] > pool_med["W1"]):
        fails.append(f"E7: width pools do not grow: C={pool_med['C']} W1={pool_med['W1']} "
                     f"W2={pool_med['W2']}")
    cut_moves = any(r["arms"]["L1"]["n_pages"] != r["arms"]["W2"]["n_pages"]
                    or r["arms"]["L2"]["n_pages"] != r["arms"]["W2"]["n_pages"] for r in rows)
    if not cut_moves:
        fails.append("E7: the cut arms' pool PAGE sets are identical to W2 — the cut is inert at "
                     "this W; report L as uninformative, not as a null")

    # ── the verdict ────────────────────────────────────────────────────────────
    print(f"artifact: {path.name}   n={len(rows)}   arms={list(ARMS)}")
    print(f"pool medians: " + "  ".join(f"{t}={pool_med[t]:.0f}" for t in ARMS))
    print(f"fallbacks:    " + "  ".join(f"{t}={fb[t]}" for t in ARMS))
    print(f"da_fetch_k pinned {sorted(da_vals)}   prefetch pinned {sorted(pf_vals)}   "
          f"E4' metric mismatches {mism}   diagnostic diffs {diag} (not voiding)   "
          f"cut moves pages {cut_moves}")
    print("\nre-derived primaries (Δ R@20 ceiling-normalised):")
    for t, kind in PRIMARY.items():
        ref = TREATMENT_REF[t]
        d = derived[f"recall_at_top_k_ceiling_norm__delta_{t}_minus_{ref}"]
        print(f"  {kind:5} {t} vs {ref}: mean {d['mean']:+.6f}  CI95 "
              f"[{d['ci95'][0]:+.6f}, {d['ci95'][1]:+.6f}]  "
              f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}")
    for t in ("W2", "L2"):
        ref = TREATMENT_REF[t]
        d = derived[f"recall_at_top_k_ceiling_norm__delta_{t}_minus_{ref}"]
        print(f"  sens. {t} vs {ref}: mean {d['mean']:+.6f}  CI95 "
              f"[{d['ci95'][0]:+.6f}, {d['ci95'][1]:+.6f}]  "
              f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}")

    if fails:
        print("\n=== VERIFIER: FAIL ===")
        for f in fails[:40]:
            print("  " + f)
        return 1
    print("\n=== VERIFIER: all checks pass (E2/E3/E4'/E5/E6/E7/E8/E9) ===")
    return 0


def extract(path: Path) -> int:
    """The compact reviewer pack: the claims + every per-query row, for a cross-family reviewer."""
    art = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in art["queries"] if "error" not in r]
    pack = {
        "claim": ("§I66 — the pre-registered A/B on the product retrieval path: do the downstream "
                  "widths (the fusion output W, the re-score cut L) improve the endpoint the "
                  "product ships?"),
        "preregistration": art["meta"]["preregistration"],
        "design": {
            "arms": art["meta"]["arms"],
            "treatment_refs": art["meta"]["treatment_refs"],
            "shipped": art["meta"]["shipped"],
            "pinned": art["meta"]["pinned"],
            "one_variable_each": ("each contrast differs from its reference in exactly ONE field: "
                                  "W1/W2 move W only (vs C); L1/L2 move L only (vs W2)"),
            "cut_arm_note": art["meta"]["cut_arm_note"],
            "primary_endpoint": "paired Δ R@20 ceiling-normalised: W1−C and L1−W2",
            "decision_rule": "ship iff CI excludes 0 AND point estimate > 0; unresolved ⇒ not shipped",
            "confounds": [art["meta"]["hyde"], art["meta"]["prefetch_note"],
                          art["meta"]["graph_lane"]],
        },
        "stored_summary": art["summary"],
        "per_query": rows,
    }
    PACK.write_text(json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"wrote {PACK}  ({len(rows)} rows, {PACK.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(ART))
    ap.add_argument("--extract", action="store_true")
    a = ap.parse_args()
    p = Path(a.artifact)
    if not p.exists():
        print(f"artifact not found: {p} — run the A/B first", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(extract(p) if a.extract else verify(p))
