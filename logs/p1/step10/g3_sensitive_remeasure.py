"""§G3 sensitive re-measurement — read-only, over two artifacts already on disk.

The §I51 endpoint (median of the retrieved top-5 `matched_concepts`) was INERT. This re-derives a
SENSITIVE endpoint: the per-query count of chunks matching >= 2 of the query's top-8 concepts, over
the WHOLE histogram (the artifacts record it with no LIMIT). Paired before vs after the merge.

Pre-registration: `.hermes/plans/2026-11-05-p1-g3-sensitive-remeasurement-preregistration.md`.
Writes logs/p1/step10/g3_sensitive_remeasure.json. No cluster, no run, no store write.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BEFORE = REPO / "logs/p1/step10/g3_query_side_baseline_2026-10-22.json"
AFTER = REPO / "logs/p1/step10/g3_query_side_baseline_2026-10-22_post_merge.json"
OUT = REPO / "logs/p1/step10/g3_sensitive_remeasure.json"


def ge2(hist: dict) -> int:
    """Chunks matching >= 2 concepts, from a {n_concepts: count} histogram."""
    return sum(int(c) for k, c in hist.items() if int(k) >= 2)


def total(hist: dict) -> int:
    return sum(int(c) for c in hist.values())


def t_ppf_975(df: int) -> float:
    """Two-sided 95 % t quantile. scipy if present, else the df=199 value (n=200 here)."""
    try:
        from scipy.stats import t  # type: ignore
        return float(t.ppf(0.975, df))
    except Exception:
        return 1.9720  # df=199; recorded so the fallback is visible, not silent


def load(path: Path) -> dict:
    d = json.loads(path.read_text())
    return {q["id"]: q for q in d["queries"]}, d


def main() -> int:
    before, bdoc = load(BEFORE)
    after, adoc = load(AFTER)

    ids = sorted(set(before) & set(after))
    assert set(before) == set(after), (
        f"query sets differ: before {len(before)} after {len(after)} "
        f"sym-diff {sorted(set(before) ^ set(after))[:5]}")
    assert ids, "no common queries"

    deltas, w, l, ties = [], 0, 0, 0
    n_before = n_after = tot_before = tot_after = 0
    for i in ids:
        b, a = ge2(before[i]["matched_concepts_histogram"]), ge2(after[i]["matched_concepts_histogram"])
        tb = total(before[i]["matched_concepts_histogram"])
        ta = total(after[i]["matched_concepts_histogram"])
        deltas.append(a - b)
        n_before += b
        n_after += a
        tot_before += tb
        tot_after += ta
        if a > b:
            w += 1
        elif a < b:
            l += 1
        else:
            ties += 1

    n = len(deltas)
    mean = sum(deltas) / n
    var = sum((d - mean) ** 2 for d in deltas) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    half = t_ppf_975(n - 1) * sd / math.sqrt(n)
    ci = [round(mean - half, 6), round(mean + half, 6)]
    resolved = not (ci[0] <= 0.0 <= ci[1])
    zero_width = (ci[0] == ci[1] == 0.0)

    art = {
        "meta": {
            "what": "§G3 sensitive re-measurement — per-query >=2-concept chunk COUNT, paired",
            "prereg": ".hermes/plans/2026-11-05-p1-g3-sensitive-remeasurement-preregistration.md",
            "before": BEFORE.name, "after": AFTER.name,
            "n_queries": n, "read_only": True, "no_cluster": True,
            "before_model": bdoc["meta"].get("embed_model"),
            "after_model": adoc["meta"].get("embed_model"),
        },
        "primary_ge2_count": {
            "before_total": n_before, "after_total": n_after,
            "mean_paired_delta": round(mean, 6), "sd": round(sd, 6),
            "ci95": ci, "n": n, "w": w, "l": l, "ties": ties,
            "queries_that_moved": w + l,
            "verdict": ("ZERO-WIDTH CI — instrument statement, not a null" if zero_width
                        else ("RESOLVED" if resolved else "UNRESOLVED")),
        },
        "secondary_share_ge_2": {
            "before": round(n_before / tot_before, 6) if tot_before else None,
            "after": round(n_after / tot_after, 6) if tot_after else None,
            "before_chunks": tot_before, "after_chunks": tot_after,
        },
    }
    OUT.write_text(json.dumps(art, indent=2, sort_keys=True) + "\n")
    print(json.dumps(art, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
