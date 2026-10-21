#!/usr/bin/env python3
"""§I39 follow-up — design the TOC/index signals with the CORRECTED band boundaries.

Established by i39_boundary_probe.py (doc 7ba61432, 3,796 chunks):
  * the TOC is pages 22-34 (74 dot-leader chunks), NOT pages 20-26 (19) as §I39's table says;
    content resumes at p34 idx139 ("This two-year course in physics is presented from...")
  * the index is pages 937-968 (188 chunks by the comma-page-ref signal); p936 is chapter prose
  * no chunk contains an exact `## Index` heading, so that signal is dead on this corpus too

So a false-positive count taken over "pages 31-900" is contaminated by ~55 genuine TOC chunks.
This probe re-measures every candidate with the TOC/index pages EXCLUDED from the body.

Read-only.

    uv run python logs/p1/step10/i39_signal_design.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
DOC = "7ba61432-c5e0-416d-aecf-25a232523481"

TOC_PAGES = set(range(22, 35))      # 22-34, measured
INDEX_PAGES = set(range(937, 969))  # 937-968, measured
FRONT_PAGES = set(range(1, 22))

COMMA_PAGEREF = re.compile(r",\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")
DOT_RUN = re.compile(r"(?:\.\s?){4,}")          # a dot-leader run, not a 3-dot ellipsis
TOC_EQ = re.compile(r"\d+-\d+\s*,\s*\d+\s*=")
SECNUM = re.compile(r"\b\d{1,2}-\d{1,2}\b")


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT chunk_index, text, page_number, is_content FROM chunks "
        "WHERE document_id = ? ORDER BY chunk_index", (DOC,)
    ).fetchall()
    con.close()

    def zone(p: int) -> str:
        if p in TOC_PAGES:
            return "TOC"
        if p in INDEX_PAGES:
            return "INDEX"
        if p in FRONT_PAGES:
            return "FRONT"
        return "BODY"

    print(f"doc {DOC[:8]}: {len(rows)} chunks")
    zones = {}
    for r in rows:
        zones.setdefault(zone(r["page_number"]), []).append(r)
    for z, rs in sorted(zones.items()):
        print(f"    {z:6} {len(rs):>5} chunks  (pages {min(r['page_number'] for r in rs)}"
              f"-{max(r['page_number'] for r in rs)})")

    def dot_lines(text: str) -> int:
        return sum(1 for ln in text.splitlines() if DOT_RUN.search(ln))

    def cand(name, fn):
        got = {"TOC": 0, "INDEX": 0, "BODY": 0, "FRONT": 0}
        for r in rows:
            text = r["text"] or ""
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if fn(text, lines):
                got[zone(r["page_number"])] += 1
        n_toc = len(zones.get("TOC", []))
        n_idx = len(zones.get("INDEX", []))
        print(f"    {name:34} TOC {got['TOC']:>2}/{n_toc:<3} INDEX {got['INDEX']:>3}/{n_idx:<3} "
              f"FRONT {got['FRONT']:>3}  BODY_FP {got['BODY']:>4}")
        return got

    print("\n[1] single signals")
    cand("dot-run x>=1", lambda t, ls: dot_lines(t) >= 1)
    for k in (2, 3, 5, 8):
        cand(f"dot-run lines >={k}", lambda t, ls, k=k: dot_lines(t) >= k)
    for k in (0.2, 0.3, 0.5):
        cand(f"dot-run lines/line_count >={k}",
             lambda t, ls, k=k: (dot_lines(t) / len(ls) >= k) if ls else False)
    cand("TOC 'N-N, N =' literal", lambda t, ls: bool(TOC_EQ.search(t)))
    for k in (0.25, 0.34, 0.5):
        cand(f"comma-pageref density >={k}",
             lambda t, ls, k=k: (sum(1 for ln in ls if COMMA_PAGEREF.search(ln)) / len(ls) >= k)
             if ls else False)

    print("\n[2] conjunctions (the shapes the two lanes actually look like)")
    cand("dot-run lines>=1 AND secnum>=1",
         lambda t, ls: dot_lines(t) >= 1 and len(SECNUM.findall(t)) >= 1)
    cand("dot-run present AND secnum>=1",
         lambda t, ls: any(DOT_RUN.search(ln) for ln in ls) and len(SECNUM.findall(t)) >= 1)
    cand("dot-run present AND secnum>=2",
         lambda t, ls: any(DOT_RUN.search(ln) for ln in ls) and len(SECNUM.findall(t)) >= 2)
    cand("dot-run present AND secnum>=3",
         lambda t, ls: any(DOT_RUN.search(ln) for ln in ls) and len(SECNUM.findall(t)) >= 3)
    cand("dot-run lines>=3 AND secnum>=3",
         lambda t, ls: dot_lines(t) >= 3 and len(SECNUM.findall(t)) >= 3)
    cand("dot-run lines>=2 AND secnum>=2",
         lambda t, ls: dot_lines(t) >= 2 and len(SECNUM.findall(t)) >= 2)
    cand("dot-run lines>=1 AND secnum>=3",
         lambda t, ls: dot_lines(t) >= 1 and len(SECNUM.findall(t)) >= 3)
    cand("TOC_EQ OR (dot>=3 AND secnum>=3)",
         lambda t, ls: bool(TOC_EQ.search(t)) or (dot_lines(t) >= 3
                                                  and len(SECNUM.findall(t)) >= 3))

    print("\n[3] what a chosen TOC rule would drop from the TRUE body (pages 35-900, 901-936)")
    for r in rows:
        p = r["page_number"]
        if zone(p) != "BODY":
            continue
        text = r["text"] or ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if dot_lines(text) >= 3 and len(SECNUM.findall(text)) >= 3:
            print(f"    p{p} idx{r['chunk_index']}: {text[:120]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
