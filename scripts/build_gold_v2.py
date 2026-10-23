#!/usr/bin/env python3
"""Assemble data/eval_queries_v2.json from the scanned gold pieces + verified negatives.

No LLM calls — this only merges files that earlier sessions produced and scanned.

Sources (all scan-labelled; see IMPROVEMENTS.md for the labels' provenance):
  --gold      data/eval_queries_gold_expanded.json        factual + multihop (55 + 40)
  --overview  data/eval_queries_gold_overview_expanded.json  the 3c overview set (40)
  --visual    data/eval_queries_gold_visual_expanded.json the 3d-ii visual set (40 -> 33 usable)
  --negatives data/eval_negatives.json                    scan-verified negatives (34)

Decisions applied here (do not silently change them):
  * The 8 `overview` entries inside --gold are the narrow pre-3c topics that round 2
    replaced; they are DROPPED (HANDOFF: 135 answerable = 95 + 40).
  * Only `calibrated` visual entries are carried (the plan's D6: do NOT reuse v1's visual
    queries; 3d-ii regenerated them — 6 uncalibrated and 1 non-specific excluded, §B4d).
  * An answerable entry whose labels fall ENTIRELY outside the retrievable window
    [min_content_page, max_content_page] is DROPPED — such a query can never be answered
    and measures nothing (§D6).
  * v1 (data/eval_queries.json) is NOT merged.

Usage:
    uv run python scripts/build_gold_v2.py
    uv run python scripts/build_gold_v2.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _load(path: str) -> list[dict]:
    p = Path(path)
    if not p.is_absolute():
        p = _ROOT / p
    return [e for e in json.loads(p.read_text()) if not e.get("id", "").startswith("_")]


def _retrievable_window() -> tuple[int, int]:
    """The content region retrieval is bounded to (IMPROVEMENTS.md §D6).

    Front matter below ``min_content_page`` and back matter above ``max_content_page`` are
    never returned, so a label there is unreachable.
    """
    from src.core.config import get_settings
    cfg = get_settings()
    return (cfg.min_content_page or 0), (cfg.max_content_page or 10**9)


def _drop_unretrievable(entries: list[dict], lo: int, hi: int) -> tuple[list[dict], list[str]]:
    """Split out answerable entries whose labels ALL fall outside the retrievable window."""
    kept, dropped = [], []
    for q in entries:
        pages = q.get("relevant_pages") or []
        if q.get("answerable", True) and pages and not any(lo <= p <= hi for p in pages):
            dropped.append(q["id"])
            continue
        kept.append(q)
    return kept, dropped


def _clamp_unretrievable(entries: list[dict], lo: int, hi: int) -> tuple[list[dict], list[dict]]:
    """Remove individual label pages outside [lo, hi] from entries that survive the drop.

    Why this exists (IMPROVEMENTS.md §D6): a label page outside the window can never be retrieved,
    so it lowers the query's achievable maximum by 1/n for nothing — it measures the window, not
    the retriever. ``_drop_unretrievable`` only removes a query when ALL its labels are outside, so
    a query with one stray page survives with a structurally reduced maximum. Measured 2026-10-19:
    4 multihop queries (gold-081/087/088/094) carried a page in 22–24 against min_content_page 30,
    every one of them a multi-page *generator* page in old-DB numbering (§D4) that the scan never
    expanded — i.e. §D4's defect surfacing as a §D6 one. Text-lane achievable max 0.9910 → 1.0000.
    """
    clamped: list[dict] = []
    removed: list[dict] = []
    for q in entries:
        pages = q.get("relevant_pages") or []
        if not q.get("answerable", True) or not pages:
            clamped.append(q)
            continue
        kept_pages = [p for p in pages if lo <= p <= hi]
        if len(kept_pages) == len(pages):
            clamped.append(q)
            continue
        removed.append({
            "id": q["id"], "lane": q.get("query_type"),
            "removed": sorted(set(pages) - set(kept_pages)),
            "n_before": len(pages), "n_after": len(kept_pages),
        })
        clamped.append({**q, "relevant_pages": kept_pages})
    return clamped, removed


# ── re-points forced by the re-ingest (IMPROVEMENTS.md §I58) ──────────────────────────────────
# The labels were authored against the deployed index (doc 6d55c52b, 5,048 chunks). The rebuilt
# index (doc 7ba61432, 3,796 chunks) is a re-chunk of the SAME PDF, so a page number can move even
# though the answering text did not. Each entry below was established by an **exact text match in
# the new index's SQLite chunks** — never by "whatever the retriever returns", which would make the
# eval easier rather than correct.
_REPOINT: dict[str, dict[int, int]] = {
    # '42-2 Thermionic emission' — the TOC line sits on p30 in the old index and p34 in the new one
    # (both `is_content=1`). ⚠️ §I58 caveat: this is TOC content, and the §I39 E5 filter excludes
    # TOC at ingest. The stored `is_content` predates §I39, so it is reachable TODAY; the next
    # re-ingest will make this query unanswerable by design. Kept measurable, flagged in §I58.
    "gold-003": {30: 34},
    # The source sentence ("...10 quarts of water per second...", "* Counting antibaryons as -1
    # baryon.") is on p98 in the new index — p99 has NO chunks at all after the re-chunk.
    "gold-009": {99: 98},
    "gold-010": {99: 98},
}


def _repoint_pages(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Move label pages the re-ingest relocated, so a label is not stranded by a page-number shift.

    Why this exists (§I58): a label page that the new index has no chunk for caps the query's
    achievable maximum — `gold-003` read **0.0000** (unreachable even at ±1), i.e. its R@20 was 0
    *by construction*, silently dragging the factual lane's mean down. This is a re-point, not a
    clamp: the clamp removes labels outside the window, this moves labels the re-chunk shifted.
    """
    out: list[dict] = []
    moved: list[dict] = []
    for q in entries:
        mapping = _REPOINT.get(q.get("id"))
        pages = q.get("relevant_pages") or []
        if not mapping or not pages:
            out.append(q)
            continue
        new_pages = sorted({mapping.get(p, p) for p in pages})
        if new_pages == sorted(pages):
            out.append(q)
            continue
        moved.append({"id": q["id"], "lane": q.get("query_type"),
                      "from": list(pages), "to": new_pages})
        note = (q.get("calibration_note") or "").strip()
        out.append({
            **q,
            "relevant_pages": new_pages,
            "calibration_note": (note + f" | §I58 re-point {list(pages)} -> {new_pages} "
                                        f"(exact text match in the re-ingested index)").strip(" |"),
        })
    return out, moved


def main() -> int:
    p = argparse.ArgumentParser(
        description="Assemble data/eval_queries_v2.json from the scanned gold pieces "
                    "+ verified negatives")
    p.add_argument("--gold", default="data/eval_queries_gold_expanded.json")
    p.add_argument("--overview", default="data/eval_queries_gold_overview_expanded.json")
    p.add_argument("--visual", default="data/eval_queries_gold_visual_expanded.json")
    p.add_argument("--negatives", default="data/eval_negatives.json")
    p.add_argument("--output", default="data/eval_queries_v2.json")
    p.add_argument("--dry-run", action="store_true", help="Report counts; write nothing")
    args = p.parse_args()

    gold_all = _load(args.gold)
    dropped_ovw = [q for q in gold_all if q.get("query_type") == "overview"]
    visual_all = _load(args.visual)
    negs = _load(args.negatives)

    lo, hi = _retrievable_window()
    gold, drop_g = _drop_unretrievable(
        [q for q in gold_all if q.get("query_type") != "overview"], lo, hi)
    overview, drop_o = _drop_unretrievable(_load(args.overview), lo, hi)
    visual, drop_v = _drop_unretrievable(
        [q for q in visual_all if q.get("calibrated")], lo, hi)
    # ...then clamp stray pages out of the survivors (IMPROVEMENTS.md §D6).
    gold, clamp_g = _clamp_unretrievable(gold, lo, hi)
    overview, clamp_o = _clamp_unretrievable(overview, lo, hi)
    visual, clamp_v = _clamp_unretrievable(visual, lo, hi)
    clamped = clamp_g + clamp_o + clamp_v
    # ...and finally move labels the RE-INGEST relocated (§I58) — a page-number shift, not a clamp.
    gold, repoint_g = _repoint_pages(gold)
    overview, repoint_o = _repoint_pages(overview)
    visual, repoint_v = _repoint_pages(visual)
    repointed = repoint_g + repoint_o + repoint_v

    note = {
        "id": "_note",
        "_note": (
            "Gold set v2 (P0-9). Answerable queries are page->question generated "
            "(non-circular) with relevant_pages scan-expanded to every page that answers them. "
            "Negatives are scan-verified: accepted only if no page scored YES. Visual queries "
            "were regenerated by 3d-ii (v1's are NOT reused) and scan-labelled; only "
            "`calibrated` ones are carried (see IMPROVEMENTS.md §B4d). Queries labelled only "
            "outside the retrievable content region are dropped (§D6)."
        )
    }
    out = [note] + gold + overview + visual + negs

    ans = len(gold) + len(overview) + len(visual)
    total = len(gold) + len(overview) + len(visual) + len(negs)
    pct = 100.0 * len(negs) / total if total else 0.0
    print(f"  text (factual+multihop): {len(gold)}  [dropped {len(dropped_ovw)} superseded overview]")
    print(f"  overview (3c):           {len(overview)}")
    print(f"  visual (3d-ii, usable):  {len(visual)}  [of {len(visual_all)} scanned]")
    print(f"  negatives:               {len(negs)}")
    unretrievable = drop_g + drop_o + drop_v
    if unretrievable:
        print(f"  dropped (labels outside [{lo}, {hi}]): {unretrievable}  "
              f"— IMPROVEMENTS.md §D6")
    if clamped:
        print(f"  clamped (stray pages removed from [{lo}, {hi}]-surviving queries):")
        for c in clamped:
            print(f"    {c['id']:14} {c['lane']:9} removed {c['removed']}  "
                  f"n {c['n_before']} -> {c['n_after']}")
    else:
        print(f"  clamped: none (no surviving query carries a page outside [{lo}, {hi}])")
    if repointed:
        print("  re-pointed (page moved by the re-ingest; §I58, exact text match):")
        for c in repointed:
            print(f"    {c['id']:14} {c['lane']:9} {c['from']} -> {c['to']}")
    else:
        print("  re-pointed: none")
    print(f"  => {ans} answerable + {len(negs)} negatives = {total}  ({pct:.1f}% negatives)")

    if total and pct < 15.0:
        print("  !! negatives below 15% — the schema test will fail")
        return 1

    if args.dry_run:
        print("DRY RUN — nothing written")
        return 0

    outp = Path(args.output)
    if not outp.is_absolute():
        outp = _ROOT / outp
    outp.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
