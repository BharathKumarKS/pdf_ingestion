#!/usr/bin/env python
"""Score the human-verification sheet (P0-9 Session 5 / Task 7).

Reads the filled-in ``data/gold_v2_review.md`` and reports the label error rate, pooled
and per stratum. Refuses to report a number while rows are still unfilled — a partial
sheet silently understates the denominator.

An error is ``WRONG``, ``MISSING-PAGE`` or ``ANSWERABLE``; ``OK`` is the only pass.
The verdict vocabulary is pre-registered in
``.hermes/plans/2026-10-16-p0-9-5-verification-protocol.md``.

Usage:
    uv run python scripts/score_review_sheet.py
    uv run python scripts/score_review_sheet.py --sheet data/gold_v2_review.md
"""
from __future__ import annotations

import argparse
import re
from collections import OrderedDict
from pathlib import Path

ERROR_VERDICTS = {"WRONG", "MISSING-PAGE", "ANSWERABLE"}
PASS_VERDICT = "OK"
VALID = ERROR_VERDICTS | {PASS_VERDICT}

_SECTION = re.compile(r"^## (.+)$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")


def parse(sheet: str) -> OrderedDict[str, list[tuple[str, str]]]:
    """stratum label -> [(query_id, verdict), …] for rows with a verdict cell.

    A stratum section is any ``## `` heading mentioning "answerable" (every sample
    section does; the instruction/scoring sections do not).
    """
    sections: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
    current: str | None = None
    for line in sheet.splitlines():
        sec = _SECTION.match(line.strip())
        if sec:
            name = sec.group(1).strip()
            current = name if "answerable" in name.lower() else None
            if current:
                sections.setdefault(current, [])
            continue
        if current is None or not line.startswith("|"):
            continue
        parts = _CELL_SPLIT.split(line)
        # | id | query | labels | pages | verdict | notes |  -> 8 parts incl. outer empties
        if len(parts) < 7:
            continue
        qid, verdict = parts[1].strip(), parts[5].strip()
        if not qid or qid == "id" or set(qid) <= set("- "):
            continue          # header or separator row
        sections[current].append((qid, verdict))
    return sections


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% score interval for k/n. Returns (lo, hi) as fractions.

    Preferred over the normal approximation at these sizes: with k=0 it still gives a
    finite upper bound (the rule of three: 3/n), which is exactly the case a small
    verification sample produces and the case people over-read.
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarize(sections: OrderedDict[str, list[tuple[str, str]]]) -> dict:
    """Count verdicts per stratum and pooled. Pure — the tests call this directly."""
    unknown: list[tuple[str, str]] = []
    unfilled: list[str] = []
    total = errors = 0
    per_stratum: list[dict] = []
    for name, rows in sections.items():
        s_total = s_errors = s_unfilled = 0
        for qid, verdict in rows:
            if not verdict:
                unfilled.append(qid)
                s_unfilled += 1
                continue
            v = verdict.upper()
            if v not in VALID:
                unknown.append((qid, verdict))
                continue
            s_total += 1
            if v in ERROR_VERDICTS:
                s_errors += 1
        per_stratum.append({"stratum": name, "scored": s_total,
                            "errors": s_errors, "blank": s_unfilled})
        total += s_total
        errors += s_errors
    return {"per_stratum": per_stratum, "total": total, "errors": errors,
            "unfilled": unfilled, "unknown": unknown}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", default="data/gold_v2_review.md")
    args = ap.parse_args()

    path = Path(args.sheet)
    if not path.exists():
        raise SystemExit(f"{path} not found — run scripts/build_review_sheet.py first")
    sections = parse(path.read_text(encoding="utf-8"))
    if not sections:
        raise SystemExit(f"no sample rows found in {path}")

    result = summarize(sections)
    total, errors = result["total"], result["errors"]
    unfilled, unknown = result["unfilled"], result["unknown"]

    print(f"sheet: {path}\n")
    print(f"{'stratum':38s} {'scored':>6s} {'errors':>6s} {'rate':>7s} {'95% CI':>16s}")
    print("-" * 80)
    for s in result["per_stratum"]:
        n, k = s["scored"], s["errors"]
        rate = f"{k / n * 100:.1f}%" if n else "—"
        lo, hi = wilson(k, n)
        ci = f"[{lo * 100:.1f}%, {hi * 100:.1f}%]" if n else "—"
        print(f"{s['stratum'][:38]:38s} {n:6d} {k:6d} {rate:>7s} {ci:>16s}")
    print("-" * 80)
    pooled = f"{errors / total * 100:.1f}%" if total else "—"
    lo, hi = wilson(errors, total)
    pci = f"[{lo * 100:.1f}%, {hi * 100:.1f}%]" if total else "—"
    print(f"{'POOLED':38s} {total:6d} {errors:6d} {pooled:>7s} {pci:>16s}")
    if unfilled:
        print(f"{'(blanks)':38s} {'':>6s} {'':>6s} {'':>7s} {len(unfilled):>13d} rows")

    if unknown:
        print("\nUnrecognised verdicts (fix these):")
        for qid, verdict in unknown:
            print(f"  {qid}: {verdict!r}  (valid: {', '.join(sorted(VALID))})")
    if unfilled:
        print(f"\n{len(unfilled)} row(s) still blank: {', '.join(unfilled[:12])}"
              f"{' …' if len(unfilled) > 12 else ''}")
        print("The rate above is over the SCORED rows only — do not record it as the "
              "label error rate until every row is filled.")
        return 1

    print(f"\nlabel error rate = {errors}/{total} = {pooled}  (95% CI {pci})")
    if errors == 0:
        print(f"0/{total}: this bounds the rate BELOW {hi * 100:.0f}%, it does not "
              f"establish that it is 0 (rule of three).")
    print("Record this in IMPROVEMENTS.md §F4b with the per-stratum breakdown above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
