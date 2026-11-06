"""Pool-order attribution — where in the fused pool does the gold sit, and does the FUSION help?

Read-only re-derivation over fusion_attribution.json. §I99 located the endpoint loss in the pool's own
ORDER (waste_order) but did not say (a) where in that order the gold sits, or (b) whether the RRF fusion
orders the gold better or worse than the lanes it fuses.

Arms compared, all read-only, same 133 queries:
  C      the product pool  (dense + sparse + colbert -> RRF, cap 100)     <- the fused order
  D100   dense-only pool   (no sparse, no colbert)                        <- the strongest single lane
  W500   the pool at cap 500 (does a wider cap reorder the top? §I92: no)

Run:  .venv/bin/python logs/p1/step10/pool_order_attribution.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

FUS = Path("logs/p1/step10/fusion_attribution.json")
K = 20


def r_at(pages: list, gold: set, k: int) -> float:
    return len(gold & set(pages[:k])) / len(gold) if gold else 0.0


def main() -> int:
    d = json.loads(FUS.read_text())
    rows = [r for r in d["per_query"] if "error" not in r]
    print(f"fusion_attribution.json — {len(rows)} queries, cut k={K}\n")

    hdr = (f"{'type':>9} {'n':>4} {'|gold|':>7} {'cov(pool)':>10} {'oracle@20':>10} "
           f"{'FUSED@20':>9} {'dense@20':>9} {'W500@20':>9} {'fused-oracle':>13}")
    print(hdr)
    for qt in ("factual", "overview", "multihop", "ALL"):
        rs = rows if qt == "ALL" else [r for r in rows if r["query_type"] == qt]
        cov, orc, fused, dense, w500, goldn = [], [], [], [], [], 0
        for r in rs:
            g = set(r["relevant_pages"])
            goldn += len(g)
            pool = r["C_pages"]
            cov.append(len(g & set(pool)) / len(g))
            orc.append(min(K, len(g & set(pool))) / len(g))
            fused.append(r_at(pool, g, K))
            dense.append(r_at(r["D100_pages"], g, K))
            w500.append(r_at(r["W500_pages"], g, K))
        print(f"{qt:>9} {len(rs):>4} {goldn/len(rs):>7.1f} {statistics.mean(cov):>10.3f} "
              f"{statistics.mean(orc):>10.4f} {statistics.mean(fused):>9.4f} "
              f"{statistics.mean(dense):>9.4f} {statistics.mean(w500):>9.4f} "
              f"{statistics.mean(orc)-statistics.mean(fused):>13.4f}")

    print("\nrank distribution of gold in the FUSED pool order (all queries):")
    bands = [(1, 20), (21, 50), (51, 100), (101, 10**9)]
    counts = {b: 0 for b in bands}
    for r in rows:
        g = set(r["relevant_pages"])
        for rank, pg in enumerate(r["C_pages"], start=1):
            if pg in g:
                for b in bands:
                    if b[0] <= rank <= b[1]:
                        counts[b] += 1
                        break
    tot = sum(counts.values()) or 1
    for b in bands:
        lbl = f"{b[0]}-{b[1]}" if b[1] < 10**9 else f"{b[0]}+"
        print(f"   ranks {lbl:>7}: {counts[b]:>6}  ({counts[b]/tot:.1%})")

    # the decisive contrast: fused vs dense-only, paired per query
    print("\npaired per query — FUSED@20 − DENSE-ONLY@20:")
    for qt in ("factual", "overview", "multihop", "ALL"):
        rs = rows if qt == "ALL" else [r for r in rows if r["query_type"] == qt]
        diffs = []
        for r in rs:
            g = set(r["relevant_pages"])
            diffs.append(r_at(r["C_pages"], g, K) - r_at(r["D100_pages"], g, K))
        m = statistics.mean(diffs)
        half = 1.96 * statistics.stdev(diffs) / (len(diffs) ** 0.5)
        res = "RESOLVED" if (m - half > 0 or m + half < 0) else "unresolved"
        print(f"   {qt:>9}: Δ={m:+.4f}  CI[{m-half:+.4f},{m+half:+.4f}]  {res}  "
              f"({sum(1 for x in diffs if x>0)}W/{sum(1 for x in diffs if x<0)}L)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
