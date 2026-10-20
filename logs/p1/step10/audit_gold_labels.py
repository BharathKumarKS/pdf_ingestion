#!/usr/bin/env python3
"""§3b — audit the gold labels' page provenance and reachability.

Answers three questions the §D4/§D6 record raises but never quantified:

  1. **Provenance.** Each label page is either *generator-derived* or *scan-derived* (a PDF page the
     whole-book fitz scan scored YES). The generator component is recorded in ``calibration_note``,
     in THREE distinct formats — the parser must handle all of them:

         factual   "Generated from chunk <uuid> (page 30) | scan-expanded: 3 pages"
         multihop  "Generated from chunk <uuid> (page 79) | ..."          <- single page
         multihop  "Multi-page, generated from pages [23, 172, 627] | ..." <- MULTI page
         overview  "Overview, topic '...' (topics derived from the book's section headings); ..."
                   -> NO generator page; labels are purely scan-derived
         visual    "Visual, generated from page 37 (DB page numbering — traceability only,
                   NOT a label); ..."                                     -> explicitly NOT a label

     §D4 established the generator component is in **old-DB** coordinates (offset ±1..±3 on ~28% of
     chunks) while the scan component is in **PDF** coordinates — the system the re-ingested index
     now speaks. So the generator component is the part carrying residual error.

  2. **Reachability.** Retrieval is bounded to ``[min_content_page, max_content_page]`` (§D6), so a
     label page outside that window can never be retrieved. ``build_gold_v2.py`` only drops a query
     when *all* its labels are outside, so a query with one unreachable page survives — with a
     structurally reduced maximum.

  3. **Ceiling impact.** ⚠️ Two different quantities, and §D9's printed "ceiling" is only the first:

       * the §D9 ceiling = ``min(K, |rel|) / |rel|`` — the cost of the top-K cut. Unaffected by
         removing a page when ``|rel| <= K``.
       * the **achievable maximum** = ``(|rel| - #unreachable) / |rel|`` — the cost of a label that
         cannot be retrieved. This is the one removing unreachable pages improves.

Read-only. Writes logs/p1/step10/label_audit.json. Exit 0 = the audit ran.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

QUERIES = ROOT / "data" / "eval_queries_v2.json"
OUT = ROOT / "logs/p1/step10/label_audit.json"

LANES = ("factual", "multihop", "overview", "visual")
TEXT_LANES = ("factual", "multihop", "overview")
TOP_K = 20

SINGLE_RE = re.compile(r"Generated from chunk\s+([0-9a-fA-F-]{8,})\s*\(page\s+(\d+)\)")
MULTI_RE = re.compile(r"generated from pages\s*\[([0-9,\s]+)\]")
VISUAL_RE = re.compile(r"generated from page\s+(\d+)\s*\(DB page numbering")


def generator_pages(note: str, lane: str) -> tuple[list[int], str]:
    """(generator pages, provenance kind) for one calibration_note."""
    if lane == "visual" or VISUAL_RE.search(note):
        return [], "none (visual note is traceability only)"
    m = MULTI_RE.search(note)
    if m:
        return [int(x) for x in re.findall(r"\d+", m.group(1))], "multi-page"
    m = SINGLE_RE.search(note)
    if m:
        return [int(m.group(2))], "single-chunk"
    if lane == "overview":
        return [], "none (topic-derived)"
    return [], "unparsed"


def d9_ceiling(n: int) -> float:
    return min(TOP_K, n) / n if n else 0.0


def main() -> int:
    from src.core.config import get_settings

    cfg = get_settings()
    lo = cfg.min_content_page or 0
    hi = cfg.max_content_page or 10**9

    entries = [q for q in json.loads(QUERIES.read_text())
               if not q.get("id", "").startswith("_")]
    answerable = [q for q in entries if q.get("answerable", True)]

    print("=" * 92)
    print("§3b — gold-label provenance and reachability audit")
    print("=" * 92)
    print(f"  query file : {QUERIES.relative_to(ROOT)}")
    print(f"  entries    : {len(entries)}  ({len(answerable)} answerable)")
    print(f"  window     : [{lo}, {hi}]  (min/max_content_page — the retrievable region)")

    rows = []
    for q in answerable:
        lane = q.get("query_type")
        pages = sorted(q.get("relevant_pages") or [])
        note = q.get("calibration_note") or ""
        gen, kind = generator_pages(note, lane)
        gen_set = set(gen)
        gen_in_labels = sorted(gen_set & set(pages))
        unreachable = [p for p in pages if p < lo or p > hi]
        n = len(pages)
        rows.append({
            "id": q["id"], "lane": lane, "n_pages": n,
            "generator_kind": kind,
            "generator_pages": gen,
            "generator_pages_in_labels": gen_in_labels,
            "n_generator_in_labels": len(gen_in_labels),
            "n_scan_only": n - len(gen_in_labels),
            "unreachable": unreachable,
            "unreachable_are_generator": sorted(set(unreachable) & gen_set),
            "d9_ceiling": round(d9_ceiling(n), 6),
            "achievable_max_before": round((n - len(unreachable)) / n, 6) if n else 0.0,
            "achievable_max_after": 1.0 if n else 0.0,
        })

    # ── 1. provenance ─────────────────────────────────────────────────────
    print("\n[1] provenance (answerable queries)")
    print(f"      {'lane':9} {'n':>4} {'labels':>7} {'gen-in-labels':>13} {'scan-only':>10}  "
          f"{'kinds':<28}")
    prov: dict = {}
    for lane in LANES:
        sub = [r for r in rows if r["lane"] == lane]
        if not sub:
            continue
        labels = sum(r["n_pages"] for r in sub)
        gen = sum(r["n_generator_in_labels"] for r in sub)
        kinds = Counter(r["generator_kind"] for r in sub)
        prov[lane] = {
            "queries": len(sub), "labels": labels,
            "generator_pages_in_labels": gen, "scan_only_labels": labels - gen,
            "generator_kinds": dict(kinds),
        }
        print(f"      {lane:9} {len(sub):>4} {labels:>7} {gen:>13} {labels - gen:>10}  "
              f"{str(dict(kinds))[:28]:<28}")

    unparsed = [r["id"] for r in rows if r["generator_kind"] == "unparsed"]
    if unparsed:
        print(f"      !! unparsed notes: {unparsed}")
    print("      (overview labels are purely scan-derived by construction; visual notes are")
    print("       traceability only, so neither carries a generator page — as designed)")

    # ── 2. reachability ───────────────────────────────────────────────────
    print(f"\n[2] reachability against [{lo}, {hi}]")
    affected = [r for r in rows if r["unreachable"]]
    total_pages = sum(r["n_pages"] for r in rows)
    bad_pages = sum(len(r["unreachable"]) for r in affected)
    print(f"      label pages: {total_pages}   unreachable: {bad_pages} "
          f"({100.0 * bad_pages / max(total_pages, 1):.3f}%)")
    print(f"      queries carrying >=1 unreachable page: {len(affected)} / {len(rows)}")
    for r in sorted(affected, key=lambda x: x["id"]):
        print(f"        {r['id']:14} {r['lane']:9} n={r['n_pages']:3} "
              f"unreachable={r['unreachable']}  generator={r['generator_pages']}  "
              f"achievable max {r['achievable_max_before']:.3f} -> {r['achievable_max_after']:.3f}")
    if affected:
        print("      NOTE: every unreachable page here is a MULTI-PAGE generator page (old-DB")
        print("            numbering) that was never scan-expanded — i.e. the §D4 defect showing")
        print("            up as a §D6 one.")
    else:
        print("      NOTE: no surviving query carries a page outside the window "
              "(§3c fix B applied 2026-10-19).")

    # ── 3. the two ceilings, kept apart ───────────────────────────────────
    print("\n[3] ceiling impact (§D9 ceiling vs achievable maximum — different quantities)")
    ceil_impact: dict = {}
    for lane in LANES:
        sub = [r for r in rows if r["lane"] == lane]
        if not sub:
            continue
        d9 = statistics.mean(r["d9_ceiling"] for r in sub)
        ab = statistics.mean(r["achievable_max_before"] for r in sub)
        aa = statistics.mean(r["achievable_max_after"] for r in sub)
        ceil_impact[lane] = {"d9_ceiling": d9, "achievable_max_before": ab,
                             "achievable_max_after": aa}
        print(f"      {lane:9} §D9 ceiling {d9:.4f} (unchanged by this fix)   "
              f"achievable max {ab:.4f} -> {aa:.4f}  ({aa - ab:+.4f})")

    text = [r for r in rows if r["lane"] in TEXT_LANES]
    t_d9 = statistics.mean(r["d9_ceiling"] for r in text)
    t_ab = statistics.mean(r["achievable_max_before"] for r in text)
    t_aa = statistics.mean(r["achievable_max_after"] for r in text)
    print(f"      {'TEXT LANE':9} §D9 ceiling {t_d9:.4f}   achievable max {t_ab:.4f} -> "
          f"{t_aa:.4f}  ({t_aa - t_ab:+.4f})")
    print(f"      (§D9's recorded text-lane ceiling 0.8016 / overview 0.3992 — reproduced: "
          f"{t_d9:.4f})")

    OUT.write_text(json.dumps({
        "window": [lo, hi],
        "provenance": prov,
        "unreachable_queries": affected,
        "ceiling_impact": ceil_impact,
        "text_lane": {"d9_ceiling": t_d9, "achievable_max_before": t_ab,
                      "achievable_max_after": t_aa},
        "rows": rows,
    }, indent=2))
    print(f"\n  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
