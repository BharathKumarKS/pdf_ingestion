#!/usr/bin/env python3
"""§I39 follow-up — locate the REAL TOC and index boundaries in doc 7ba61432.

The band table in §I39 (front 1-30, TOC 20-26, body 31-900, back 901-970, index 936-970) came
from the old document's page analysis. The signal probe found TOC continuation text on pages
33-34, i.e. INSIDE the "body" band — so every "body false positive" count measured with those
bands is contaminated by genuine TOC chunks. This probe finds the boundaries from the text.

Read-only.

    uv run python logs/p1/step10/i39_boundary_probe.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
DOC = "7ba61432-c5e0-416d-aecf-25a232523481"

COMMA_PAGEREF = re.compile(r",\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")
TOC_EQ = re.compile(r"\d+-\d+\s*,\s*\d+\s*=")
DOT_LEADER = re.compile(r"\.\s?\.\s?\.")


def main() -> int:
    from src.pdf_ingestion.content_filter import is_index_heading, is_index_layout

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT chunk_index, text, page_number, is_content FROM chunks "
        "WHERE document_id = ? ORDER BY chunk_index", (DOC,)
    ).fetchall()
    con.close()

    def dens(rx, text: str, lines: list[str]) -> float:
        return (sum(1 for ln in lines if rx.search(ln)) / len(lines)) if lines else 0.0

    # ── 1. the index heading, where it really is ─────────────────────────────
    print("[1] chunks whose text contains an exact index-heading line")
    for r in rows:
        if is_index_heading(r["text"] or ""):
            print(f"    p{r['page_number']} idx{r['chunk_index']} is_content={r['is_content']}: "
                  f"{(r['text'] or '')[:110]!r}")

    # ── 2. where each signal fires, by page ──────────────────────────────────
    print("\n[2] signal firings by page (page: count) — index-entry and TOC patterns")
    for label, rx, thr in (
        ("comma-page-ref density>=0.25", COMMA_PAGEREF, 0.25),
        ("toc 'N-N, N =' literal", TOC_EQ, None),
        ("dot-leader", DOT_LEADER, None),
    ):
        per_page: Counter = Counter()
        for r in rows:
            text = r["text"] or ""
            lines = [ln for ln in text.splitlines() if ln.strip()]
            hit = (dens(rx, text, lines) >= thr) if thr is not None else bool(rx.search(text))
            if hit:
                per_page[r["page_number"]] += 1
        pages = sorted(per_page)
        print(f"\n    {label}: fires on {sum(per_page.values())} chunks, pages "
              f"{pages[0]}-{pages[-1]} ({len(pages)} distinct pages)")
        runs, cur = [], [pages[0]] if pages else []
        for p in pages[1:]:
            if p - cur[-1] <= 2:
                cur.append(p)
            else:
                runs.append(cur)
                cur = [p]
        if cur:
            runs.append(cur)
        for run in runs:
            n = sum(per_page[p] for p in run)
            print(f"       pages {run[0]}-{run[-1]}: {n} chunks")
        print(f"       detail: " + " ".join(f"{p}:{per_page[p]}" for p in pages[:40]))

    # ── 3. every chunk on pages 27-46, to find where the TOC ends ────────────
    print("\n[3] chunks on pages 27-46 (is_content, and whether it looks like TOC)")
    for r in rows:
        p = r["page_number"]
        if not (27 <= p <= 46):
            continue
        text = r["text"] or ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        toc_like = dens(COMMA_PAGEREF, text, lines) >= 0.25 or bool(TOC_EQ.search(text))
        print(f"    p{p} idx{r['chunk_index']} is_content={r['is_content']} "
              f"toc_like={int(toc_like)}: {text[:100]!r}")

    # ── 4. corrected band table, derived from the text ───────────────────────
    print("\n[4] is_content by band under the CORRECTED boundaries")
    idx_pages = {r["page_number"] for r in rows
                 if dens(COMMA_PAGEREF, r["text"] or "",
                         [ln for ln in (r["text"] or "").splitlines() if ln.strip()]) >= 0.25}
    toc_pages = {r["page_number"] for r in rows if TOC_EQ.search(r["text"] or "")}
    print(f"    index-entry pages: {min(idx_pages)}-{max(idx_pages)}  ({len(idx_pages)} pages)"
          if idx_pages else "    index-entry pages: none")
    print(f"    TOC-pattern pages: {min(toc_pages)}-{max(toc_pages)}  ({len(toc_pages)} pages)"
          if toc_pages else "    TOC-pattern pages: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
