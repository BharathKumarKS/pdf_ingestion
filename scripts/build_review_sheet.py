#!/usr/bin/env python
"""Build the human-verification sheet for the v2 gold set (P0-9 Session 5 / Task 7).

Writes ``data/gold_v2_review.md`` — one row per sampled query, with the exact PDF pages
to open. The user fills the verdict column; ``scripts/score_review_sheet.py`` reads it back.

Design decisions (pre-registered in .hermes/plans/2026-10-16-p0-9-5-verification-protocol.md):

* **Stratified by the process that produced the labels, not sampled uniformly.**
  The five strata came from five different generation+judge paths, so an error rate
  pooled over a uniform sample can hide a lane-specific failure — and the visual lane
  (a *different, strict* judge prompt, §B4c) and the negatives (a three-tier acceptance
  rule) are precisely where we already know there is uncertainty. The plan's Task 7
  snippet samples 25 uniformly, which lands only ~4 in each of those strata.
* **Equal allocation per stratum** (default 6 → 30 queries) so no lane is under-sampled
  and nobody can argue the sample was pointed away from a weak lane.
* **At most 5 pages are listed per query.** Overview labels average 58 pages (max 314);
  verifying them all is infeasible. When there are more than 5, the first, the last and
  three evenly spaced pages are listed — over-labelling from a book-wide scan shows up at
  the edges of a label set.
* **Deterministic**: fixed per-stratum seeds, so a re-run reproduces the same sample.

Usage:
    uv run python scripts/build_review_sheet.py                 # 6 per stratum = 30
    uv run python scripts/build_review_sheet.py --per-stratum 5  # the plan's 25
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

MAX_PAGES_SHOWN = 5

# (stratum key, human label, how to judge it)
STRATA = [
    ("factual", "factual (answerable)",
     "Is the answer on the listed page?"),
    ("multihop", "multihop (answerable)",
     "Do the listed pages establish BOTH concepts and the link between them?"),
    ("overview", "overview (answerable)",
     "Does the page CONTRIBUTE to the topic's synthesis? (not: does it answer a question)"),
    ("visual", "visual (answerable)",
     "Does the page SHOW the figure/table described? (a different figure is WRONG)"),
    ("negative", "negatives (must be unanswerable)",
     "Is the book genuinely unable to answer this? Any page that does = ANSWERABLE"),
]


def _pages_to_check(pages: list[int]) -> list[int]:
    """All labelled pages when few; else first, last and three evenly spaced."""
    pages = sorted(pages)
    if len(pages) <= MAX_PAGES_SHOWN:
        return pages
    idx = sorted({round(i * (len(pages) - 1) / (MAX_PAGES_SHOWN - 1))
                  for i in range(MAX_PAGES_SHOWN)})
    return [pages[i] for i in idx]


def _cell(text: str, limit: int = 88) -> str:
    text = " ".join(str(text).split())          # collapse newlines
    text = text.replace("|", r"\|")             # keep the table intact
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", default="data/eval_queries_v2.json")
    ap.add_argument("--out", default="data/gold_v2_review.md")
    ap.add_argument("--per-stratum", type=int, default=6,
                    help="queries sampled per stratum (default 6 → 30 total; "
                         "5 reproduces the plan's 25)")
    args = ap.parse_args()

    queries = [q for q in json.loads(Path(args.queries).read_text(encoding="utf-8"))
               if not str(q.get("id", "")).startswith("_")]

    buckets: dict[str, list[dict]] = {k: [] for k, _, _ in STRATA}
    for q in queries:
        if q.get("answerable") is False:
            buckets["negative"].append(q)
        elif q.get("query_type") in buckets:
            buckets[q["query_type"]].append(q)
        else:
            # 'answerable' missing/None or an unknown type — do not silently drop it
            raise SystemExit(f"unclassifiable query {q.get('id')!r}: "
                             f"answerable={q.get('answerable')!r} type={q.get('query_type')!r}")

    out: list[str] = []
    out.append("# Gold v2 — human verification sheet (P0-9 Session 5 / Task 7)")
    out.append("")
    out.append(f"Generated from `{args.queries}` by `scripts/build_review_sheet.py` "
               f"({args.per_stratum} per stratum). Fill the **verdict** column.")
    out.append("")
    out.append("## How to check each row")
    out.append("")
    out.append("1. Open `data/base_textbooks/feynman-lectures-on-physics-volume1.pdf`.")
    out.append("2. Go to each page in **pages to open** and read it against the row's criterion.")
    out.append("3. **The DB page number carries ±1 of chunk-boundary fuzz (§D4).** A page counts")
    out.append("   as correct if the content is on the listed page **or within ±1 of it** — glance")
    out.append("   at the neighbours before calling it wrong. Record `WRONG` only when the content")
    out.append("   is absent across that window.")
    out.append("4. Verdicts: `OK` · `WRONG` (a listed page does not support the query — "
               "over-labelled) · `MISSING-PAGE` (the answer is on a page NOT listed — "
               "under-labelled; **write that page in notes**) · negatives also use `ANSWERABLE`.")
    out.append("5. An error is `WRONG`, `MISSING-PAGE` or `ANSWERABLE`. `OK` is the only pass.")
    out.append("")
    out.append(f"## Sample: {args.per_stratum} per stratum = "
               f"{args.per_stratum * len(STRATA)} queries")
    out.append("")
    out.append("| stratum | population | sampled | criterion |")
    out.append("|---|---|---|---|")
    for key, label, criterion in STRATA:
        out.append(f"| {label} | {len(buckets[key])} | "
                   f"{min(args.per_stratum, len(buckets[key]))} | {criterion} |")
    out.append("")

    total_sampled = 0
    for key, label, criterion in STRATA:
        pool = sorted(buckets[key], key=lambda q: q["id"])
        k = min(args.per_stratum, len(pool))
        rng = random.Random(f"p0-9-5-{key}")
        sample = sorted(rng.sample(pool, k), key=lambda q: q["id"])
        total_sampled += len(sample)

        out.append(f"## {label}")
        out.append("")
        out.append(f"*{criterion}*")
        out.append("")
        out.append("| id | query | labels | pages to open | verdict | notes |")
        out.append("|---|---|---|---|---|---|")
        for q in sample:
            pages = list(q.get("relevant_pages") or [])
            if key == "negative":
                pages_cell = "— (must be unanswerable)"
                labels_cell = "0"
            else:
                check = _pages_to_check(pages)
                shown = ", ".join(str(p) for p in check)
                if len(pages) > len(check):
                    shown += f"  (of {len(pages)} labelled)"
                pages_cell = shown
                labels_cell = str(len(pages))
            query_cell = _cell(q.get("query", ""))
            if q.get("topic"):
                query_cell += " · topic: " + _cell(q["topic"], 34)
            out.append(f"| {q['id']} | {query_cell} | "
                       f"{labels_cell} | {pages_cell} | | |")
        out.append("")

    out.append("---")
    out.append("")
    out.append("## Scoring")
    out.append("")
    out.append("```bash")
    out.append("uv run python scripts/score_review_sheet.py")
    out.append("```")
    out.append("")
    out.append("Record the result in `IMPROVEMENTS.md` §F4b as "
               "`label error rate = X/N = Y%`, with the per-stratum breakdown.")
    out.append("")

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dest} — {total_sampled} queries "
          f"({args.per_stratum} per stratum × {len(STRATA)} strata)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
