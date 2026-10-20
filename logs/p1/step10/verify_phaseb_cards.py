#!/usr/bin/env python3
"""Phase B / B4 — verify the CARDS, in SQLite. Exit 0 = PASS.

Counts in the store, never from the run's own summary line (the recurring failure mode here is a
phase that reports success while writing nothing).

  1. the run's OWN failure counters, read from the log: the generator's closing line
     (`Generated N cards for M chunks (X chunks with a failed card type, Y failed card-type calls,
     Z LLM failures of C calls)`) must be **present** and must read **0 / 0 / 0**, and the
     "Card types that failed at least once" warning must be **absent**. **This replaces the old
     check, which looked for a `Failed:` row and was VACUOUS (§I25)** — `run_phase2.py` prints a
     `Failed:` row only when the whole document raises, while the generator swallows failures one
     level deeper, per card type. Measured on the aborted 2026-10-19 run: 16 `LLM CALL FAILED`
     ERRORs, 16 card-type failures, **zero `Failed:` rows**. A missing closing line is itself a
     FAIL: it means the run never reached the end of the card phase.
     The `Failed:` row check is kept as a secondary signal;
  2. active cards exist for the document, and EVERY card's chunk_id resolves to a chunk of that
     same document (a card pointing at an old-doc chunk means the wrong document was processed);
  3. the distinct card_type set == the 8 in `CardType` exactly;
  4. the cards-per-content-chunk ratio is in family — RECORDED, not asserted (a ratio near zero is
     the §I9 signature);
  5. the per-type distribution is printed, because `question` (qa_pairs) and `factoid` (factoids)
     are MULTI-card parsers: a flat 8-per-chunk would mean those two silently degraded;
  6. the other document's active cards are untouched — `_deactivate_cards` is keyed on document_id
     and Phase B must not deactivate another document's cards.

    uv run python logs/p1/step10/verify_phaseb_cards.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
BEFORE = ROOT / "logs/p1/step10/phaseb_before.json"
OUT = ROOT / "logs/p1/step10/phaseb_cards_verify.json"
LOG = ROOT / "logs/p1/step10/phaseb_run.log"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"
DOC_OLD = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"

# The generator's closing line (§I25's fix emits it). Captures the three failure counts.
_CLOSING_RE = re.compile(
    r"Generated (?P<cards>\d+) cards for (?P<chunks>\d+) chunks "
    r"\((?P<failed_chunks>\d+) chunks with a failed card type, "
    r"(?P<failed_calls>\d+) failed card-type calls, "
    r"(?P<llm_failures>\d+) LLM failures of (?P<llm_calls>\d+) calls\)"
)


def _rel(path: Path) -> str:
    """A short display path, tolerating one outside the repo (a self-test's temp log)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    from src.pdf_ingestion.card_generator import CardType

    before = json.loads(BEFORE.read_text()) if BEFORE.exists() else {}
    content_chunks = before.get("chunks_content")
    old_active_before = before.get("old_doc_active_cards")

    failures: list[str] = []
    log_summary: dict = {}
    print("=" * 92)
    print("Phase B / B4 — card verifier")
    print("=" * 92)

    # ── 1. the run's own failure counters (§I25 — the guard that is NOT vacuous) ──
    print("\n[1] the run log's failure counters")
    if not LOG.exists():
        print(f"      !! {_rel(LOG)} not found")
        failures.append("run log missing; the failure counters could not be read")
    else:
        text = LOG.read_text()
        match = _CLOSING_RE.search(text)
        failed_rows = [ln.strip() for ln in text.splitlines() if "Failed:" in ln]
        type_warnings = [ln.strip() for ln in text.splitlines()
                         if "Card types that failed at least once" in ln]

        print(f"      {_rel(LOG)}: {len(text.splitlines())} lines")
        if match is None:
            print("      !! the generator's closing summary line is ABSENT — the card phase did "
                  "not reach the end (aborted, or the line was changed)")
            failures.append("no 'Generated N cards for M chunks (…)' closing line in the run log")
        else:
            log_summary = {k: int(v) for k, v in match.groupdict().items()}
            print(f"      closing line : {log_summary['cards']} cards / "
                  f"{log_summary['chunks']} chunks;  "
                  f"failed chunks {log_summary['failed_chunks']}, "
                  f"failed card-type calls {log_summary['failed_calls']}, "
                  f"LLM failures {log_summary['llm_failures']} of "
                  f"{log_summary['llm_calls']} calls")
            if log_summary["failed_chunks"]:
                failures.append(
                    f"{log_summary['failed_chunks']} chunk(s) had a failed card type")
            if log_summary["failed_calls"]:
                failures.append(
                    f"{log_summary['failed_calls']} card-type call(s) failed")
            if log_summary["llm_failures"]:
                failures.append(
                    f"{log_summary['llm_failures']} LLM call(s) failed after their retries")
            if not (log_summary["failed_chunks"] or log_summary["failed_calls"]
                    or log_summary["llm_failures"]):
                print("      counters clean: 0 / 0 / 0")

        if type_warnings:
            print(f"      !! {len(type_warnings)} 'Card types that failed' warning(s):")
            for ln in type_warnings[:3]:
                print(f"         {ln[-120:]}")
            failures.append("the generator logged 'Card types that failed at least once'")

        print(f"      secondary: 'Failed:' rows in the run table = {len(failed_rows)}")
        for ln in failed_rows[:5]:
            print(f"        !! {ln[:100]}")
        if failed_rows:
            failures.append(f"{len(failed_rows)} 'Failed:' row(s) in the run table")

    # ── 2..6 ──────────────────────────────────────────────────────────────
    con = sqlite3.connect(DB)
    total = con.execute(
        "SELECT count(*) FROM cards WHERE document_id = ? AND is_active = 1", (DOC_NEW,)
    ).fetchone()[0]
    by_type = dict(con.execute(
        "SELECT card_type, count(*) FROM cards WHERE document_id = ? AND is_active = 1 "
        "GROUP BY card_type", (DOC_NEW,)).fetchall())
    # every card's chunk must belong to this document
    orphan = con.execute(
        "SELECT count(*) FROM cards c WHERE c.document_id = ? AND c.is_active = 1 "
        "AND NOT EXISTS (SELECT 1 FROM chunks ch WHERE ch.id = c.chunk_id "
        "                AND ch.document_id = ?)", (DOC_NEW, DOC_NEW)).fetchone()[0]
    foreign = con.execute(
        "SELECT count(*) FROM cards c JOIN chunks ch ON ch.id = c.chunk_id "
        "WHERE c.document_id = ? AND c.is_active = 1 AND ch.document_id <> ?",
        (DOC_NEW, DOC_NEW)).fetchone()[0]
    old_active = con.execute(
        "SELECT count(*) FROM cards WHERE document_id = ? AND is_active = 1", (DOC_OLD,)
    ).fetchone()[0]
    chunks_used = con.execute(
        "SELECT count(DISTINCT chunk_id) FROM cards WHERE document_id = ? AND is_active = 1",
        (DOC_NEW,)).fetchone()[0]
    con.close()

    print(f"\n[2] cards for {DOC_NEW[:8]}…")
    print(f"      active cards        : {total}")
    print(f"      distinct chunks used: {chunks_used}"
          f"{f' / {content_chunks}' if content_chunks else ''}")
    print(f"      cards with no resolving chunk: {orphan}")
    print(f"      cards resolving to ANOTHER doc's chunk: {foreign}")
    if total == 0:
        failures.append("ZERO active cards — the run wrote nothing (§I9 signature)")
    if orphan:
        failures.append(f"{orphan} cards have a chunk_id that does not resolve")
    if foreign:
        failures.append(f"{foreign} cards point at a chunk of a DIFFERENT document")

    print(f"\n[3] card types")
    expected = [t.value for t in CardType]
    present = sorted(by_type)
    missing = [t for t in expected if t not in by_type]
    print(f"      present ({len(present)}) : {present}")
    print(f"      missing         : {missing or 'none'}")
    if missing:
        failures.append(f"card types missing: {missing}")

    print(f"\n[4] volume")
    if content_chunks:
        ratio = total / content_chunks
        print(f"      cards / content chunk : {ratio:.2f}  ({total} / {content_chunks})")
        print("      expected family: ~16-20, because 'question' and 'factoid' are multi-card")
        if ratio < 1.0:
            failures.append(f"only {ratio:.2f} cards per content chunk — far below family")
    else:
        print("      (no before-snapshot: re-run probe_phaseb_scope.py to get the denominator)")

    print(f"\n[5] per-type distribution (multi-card parsers first)")
    for t in ("question", "factoid"):
        n = by_type.get(t, 0)
        print(f"      {t:14} {n:>7}   {'MULTI-card' if n else '!! EMPTY — parser degraded'}")
        if n == 0 and total:
            failures.append(f"'{t}' produced no cards — a multi-card parser degraded silently")
    for t in expected:
        if t in ("question", "factoid"):
            continue
        print(f"      {t:14} {by_type.get(t, 0):>7}")

    print(f"\n[6] the other document is untouched")
    print(f"      {DOC_OLD[:8]}… active cards now: {old_active}"
          f"{f'  (before: {old_active_before})' if old_active_before else ''}")
    if old_active_before is not None and old_active != old_active_before:
        failures.append(
            f"the OLD document's active card count changed: {old_active_before} -> {old_active}")

    OUT.write_text(json.dumps({
        "document_id": DOC_NEW, "active_cards": total, "by_type": by_type,
        "chunks_used": chunks_used, "orphan_cards": orphan, "foreign_doc_cards": foreign,
        "old_doc_active_cards": old_active, "log_summary": log_summary,
        "failures": failures,
        "verdict": "FAIL" if failures else "PASS",
    }, indent=2))
    print(f"\n  wrote {_rel(OUT)}")

    print()
    print("=" * 92)
    if failures:
        print("B4 VERDICT: FAIL")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 92)
        return 1
    print("B4 VERDICT: PASS — cards written, typed, resolving to this document")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    sys.exit(main())
