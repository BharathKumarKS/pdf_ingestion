#!/usr/bin/env python
"""§I57 — OLD index vs NEW index, paired per query. The only cross-system comparison that exists.

Why this exists
---------------
The question "is the new system better?" had no scripted answer: `evaluate_rag.py` writes only a
`.md`, so the two runs could only be compared by reading two tables by eye. This pairs them by query
id and computes the paired delta + 95 % CI on every metric both runs share.

⚠️ READ THE CONFOUNDS BEFORE THE NUMBERS. The two runs are **not a controlled comparison**:

| | §D12 (OLD) | §3d (NEW) |
|---|---|---|
| run | `p0-9-gold-v2_2026-10-17_0422.md` | `p1-step10-retrieval-only_2026-10-20_0411.md` |
| collection | **`knowledge_base`** (deployed, doc `6d55c52b`) | **`knowledge_base_v2`** (doc `7ba61432`) |
| index | 5,135 points (5,051 chunks + 84 RAPTOR) | 3,796 points, **no RAPTOR nodes at all** |
| DA lane | **live** | **DEAD** (768-vs-1024, §I12) |
| generation | full — judge ran (Faith / Ans.Rel) | **retrieval-only — no generation metrics** |
| abstention | generation mode (declining answer counts) | score-threshold only |
| label clamp | before §3c | after §3c |

So a delta here mixes at least six changes. **The direction is informative; the magnitude is not
attributable.** Held constant: the query set (133 answerable v2 queries) and the metric definitions.

Run:
    uv run python logs/p1/step10/compare_old_vs_new_index.py
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "logs/p1/step10/compare_old_vs_new_index.json"

OLD = REPO / "data/eval_results/p0-9-gold-v2_2026-10-17_0422.md"
NEW = REPO / "data/eval_results/p1-step10-retrieval-only_2026-10-20_0411.md"
TYPES = ("factual", "multihop", "overview")
METRICS = [("r100", "Recall@100"), ("r20", "Recall@20"), ("hit20", "Hit@20"),
           ("ctxp", "Ctx.Prec"), ("mrr", "MRR"), ("ndcg", "NDCG@20")]


def parse(path: Path) -> dict[str, dict]:
    """Per-query rows from an `evaluate_rag.py` report. Only answerable queries carry metrics."""
    rows: dict[str, dict] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("| ") or ln.startswith("| ---") or ln.startswith("| ID "):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 9 or not c[0].startswith(("gold-", "ovw-")):
            continue

        def f(x: str):
            try:
                return float(x)
            except ValueError:
                return None

        v = {"type": c[2], "r100": f(c[3]), "r20": f(c[4]), "hit20": f(c[5]),
             "ctxp": f(c[6]), "mrr": f(c[7]), "ndcg": f(c[8])}
        if all(v[k] is not None for k, _ in METRICS):
            rows[c[0]] = v
    return rows


def paired(old: dict, new: dict, ids: list[str], metric: str) -> dict:
    d = [new[i][metric] - old[i][metric] for i in ids]
    n = len(d)
    if n == 0:
        return {}
    m = statistics.mean(d)
    sd = statistics.stdev(d) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "old": round(statistics.mean(old[i][metric] for i in ids), 6),
        "new": round(statistics.mean(new[i][metric] for i in ids), 6),
        "delta": round(m, 6),
        "sd": round(sd, 6),
        "ci95": [round(m - half, 6), round(m + half, 6)],
        "resolved": bool((m - half) > 0 or (m + half) < 0),
        "wins": sum(1 for x in d if x > 1e-9),
        "losses": sum(1 for x in d if x < -1e-9),
        "identical": sum(1 for x in d if abs(x) <= 1e-9),
    }


def main() -> int:
    old, new = parse(OLD), parse(NEW)
    shared = sorted(set(old) & set(new))
    if not shared:
        print("ABORT: no shared queries — the two reports are not comparable at all.", file=sys.stderr)
        return 3

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/compare_old_vs_new_index.py",
            "what": "§I57 — OLD index vs NEW index, paired per query (the only cross-system comparison)",
            "old_report": str(OLD.relative_to(REPO)),
            "new_report": str(NEW.relative_to(REPO)),
            "old_collection": "knowledge_base (deployed, doc 6d55c52b)",
            "new_collection": "knowledge_base_v2 (doc 7ba61432)",
            "held_constant": "the 133 answerable v2 queries and the metric definitions",
            "confounds": [
                "index composition: 5,135 points (5,051 chunks + 84 RAPTOR) vs 3,796 with NO RAPTOR",
                "the DA lane was LIVE in the old run and DEAD in the new one (§I12)",
                "the old run was full (judge ran); the new one is retrieval-only",
                "abstention mode differs (generation vs score-threshold) — not comparable",
                "§3c's label clamp landed between the two runs",
                "different documents: the labels were built against the OLD index (§D4/§D6)",
            ],
            "reading": ("the DIRECTION is informative; the MAGNITUDE is not attributable to any one "
                        "change. This is not a controlled comparison and cannot license a claim that "
                        "the new system is better or worse overall."),
            "not_measured": ("generation metrics (Faithfulness / Answer Relevance) have NEVER been "
                             "measured on the new index — the only v2 run was retrieval-only."),
            "n_shared": len(shared),
        },
        "overall": {label: paired(old, new, shared, met) for met, label in METRICS},
        "by_type": {
            t: {label: paired(old, new, [i for i in shared if old[i]["type"] == t], met)
                for met, label in METRICS}
            for t in TYPES
        },
        "queries": [
            {"id": i, "type": old[i]["type"],
             **{label: round(new[i][met] - old[i][met], 6) for met, label in METRICS}}
            for i in shared
        ],
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"§I57  OLD ({old and 'knowledge_base'}) vs NEW (knowledge_base_v2) — "
          f"paired, n={len(shared)}")
    print(f"{'metric':10s} {'OLD':>7s} {'NEW':>7s} {'delta':>8s}  {'95% CI':>19s}  {'verdict':10s} W/L/T")
    for label, s in out["overall"].items():
        print(f"{label:10s} {s['old']:7.4f} {s['new']:7.4f} {s['delta']:+8.4f}  "
              f"[{s['ci95'][0]:+.4f},{s['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if s['resolved'] else 'unresolved':10s} "
              f"{s['wins']}/{s['losses']}/{s['identical']}")
    print("\nby type, R@20:")
    for t, blk in out["by_type"].items():
        s = blk["Recall@20"]
        print(f"  {t:9s} n={s['n']:3d}  {s['old']:.4f} -> {s['new']:.4f}  delta {s['delta']:+.4f}  "
              f"CI [{s['ci95'][0]:+.4f},{s['ci95'][1]:+.4f}]  "
              f"{'RESOLVED' if s['resolved'] else 'unresolved':9s} "
              f"W/L/T {s['wins']}/{s['losses']}/{s['identical']}")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
