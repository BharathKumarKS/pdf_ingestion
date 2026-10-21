#!/usr/bin/env python3
"""§I39 / §E5 — re-measure the candidate content-filter signals against the LIVE corpus.

Read-only. Doc `7ba61432` (the rebuilt corpus, knowledge_base_v2). Prints:
  1. the current `is_content` verdict by page band (what the filter catches today);
  2. sample TOC and index chunk texts, so the candidate regexes are designed on real text;
  3. each candidate signal's catch count on the index/TOC bands and its false positives in the body.

    uv run python logs/p1/step10/i39_filter_signal_probe.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
DOC = "7ba61432-c5e0-416d-aecf-25a232523481"

# page bands, per §I39's measured table
FRONT = (1, 30)
TOC = (20, 26)
BODY = (31, 900)
BACK = (901, 970)
INDEX = (936, 970)


def band(page: int) -> str:
    if page <= 30:
        return "toc" if 20 <= page <= 26 else "front"
    if page <= 900:
        return "body"
    return "index" if page >= 936 else "back"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, chunk_index, text, page_number, is_content FROM chunks "
        "WHERE document_id = ? ORDER BY chunk_index", (DOC,)
    ).fetchall()
    con.close()
    print(f"doc {DOC[:8]}: {len(rows)} chunks\n")

    by_band = Counter(band(r["page_number"]) for r in rows)
    print("[1] current is_content verdict by band")
    print(f"    {'band':7} {'chunks':>7} {'is_content=1':>13} {'is_content=0':>13} {'null':>6}")
    for b in ("front", "toc", "body", "back", "index"):
        sub = [r for r in rows if band(r["page_number"]) == b]
        if not sub:
            continue
        c1 = sum(1 for r in sub if r["is_content"] == 1)
        c0 = sum(1 for r in sub if r["is_content"] == 0)
        cn = len(sub) - c1 - c0
        print(f"    {b:7} {len(sub):>7} {c1:>13} {c0:>13} {cn:>6}")
    print(f"    {'TOTAL':7} {len(rows):>7}")

    print("\n[2] samples — TOC band (pages 20-26)")
    for r in [x for x in rows if band(x["page_number"]) == "toc"][:6]:
        print(f"    p{r['page_number']} idx{r['chunk_index']} "
              f"is_content={r['is_content']}: {(r['text'] or '')[:150]!r}")
    print("\n    samples — index band (pages 936-970)")
    for r in [x for x in rows if band(x["page_number"]) == "index"][:6]:
        print(f"    p{r['page_number']} idx{r['chunk_index']} "
              f"is_content={r['is_content']}: {(r['text'] or '')[:150]!r}")
    print("\n    samples — body band (pages 31-900), for the false-positive check")
    for r in [x for x in rows if band(x["page_number"]) == "body"][:3]:
        print(f"    p{r['page_number']} idx{r['chunk_index']}: {(r['text'] or '')[:150]!r}")

    # ── candidate signals ────────────────────────────────────────────────────
    PAGE_REF = re.compile(r"(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")
    PAGE_REF_COMMA = re.compile(r",\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")
    DOT_LEADER = re.compile(r"\.\s?\.\s?\.")
    TOC_EQ = re.compile(r"\d+-\d+\s*,\s*\d+\s*=")

    def density(rx, text: str, lines: list[str]) -> float:
        if not lines:
            return 0.0
        return sum(1 for ln in lines if rx.search(ln)) / len(lines)

    cands = {
        "page-ref density >=0.34": lambda t, ls: density(PAGE_REF, t, ls) >= 0.34,
        "comma page-ref >=0.34": lambda t, ls: density(PAGE_REF_COMMA, t, ls) >= 0.34,
        "comma page-ref >=0.25": lambda t, ls: density(PAGE_REF_COMMA, t, ls) >= 0.25,
        "dot-leader (REJECTED)": lambda t, ls: bool(DOT_LEADER.search(t)),
        "toc 'N-N, N ='": lambda t, ls: bool(TOC_EQ.search(t)),
    }

    print("\n[3] candidate signals — catches by band, and body false positives")
    print(f"    {'signal':26} {'index':>7} {'toc':>6} {'front':>6} {'back':>6} {'BODY FP':>8}")
    for name, fn in cands.items():
        counts = Counter()
        body_fp = 0
        for r in rows:
            b = band(r["page_number"])
            text = r["text"] or ""
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if fn(text, lines):
                counts[b] += 1
                if b == "body":
                    body_fp += 1
        n_index = sum(1 for r in rows if band(r["page_number"]) == "index")
        n_toc = sum(1 for r in rows if band(r["page_number"]) == "toc")
        print(f"    {name:26} {counts['index']:>3}/{n_index:<3} {counts['toc']:>2}/{n_toc:<3} "
              f"{counts['front']:>6} {counts['back']:>6} {body_fp:>8}")

    # ── inspect anything a candidate would drop in the body ──────────────────
    dropped = []
    for r in rows:
        if band(r["page_number"]) != "body":
            continue
        text = r["text"] or ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if (density(PAGE_REF_COMMA, text, lines) >= 0.25
                or density(PAGE_REF, text, lines) >= 0.34
                or DOT_LEADER.search(text)
                or TOC_EQ.search(text)):
            dropped.append((r["page_number"], r["chunk_index"], text))
    print(f"\n[4] BODY chunks any candidate would drop: {len(dropped)}")
    for page, idx, text in dropped[:12]:
        print(f"    p{page} idx{idx}: {text[:130]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
