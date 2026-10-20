#!/usr/bin/env python3
"""§3a — does the DEPLOYED index's ``page_number`` sit on the true PDF page?

Step 6 (`logs/p1/step6/README.md`) verified the parent-aware *code path* in isolation and recorded
"not yet deployed — ``store.ingest_document`` still calls the legacy path". Step 8 deployed it.
This probe re-runs the **same** measurement against what is actually in the deployed SQLite:

    chunks.page_number  for doc 7ba61432   (the re-ingested document, what the funnel reads)
    chunks.page_number  for doc 6d55c52b   (the old document, still the deployed index)

Both are measured on the **same unit** (all chunks, and first-per-page), because Step 6's
independent reviewer established that comparing unequal samplings is not apples-to-apples.

The oracle is unchanged: PyMuPDF page text via ``PageStore``, a different extractor from Docling,
which never sees the page numbers under test. The measurement helpers are **imported from the Step 6
probe** rather than re-implemented, so the two cannot drift.

⚠️ The Step 6 probe's own ``old_path_items()`` has no ``document_id`` filter; with two documents now
in SQLite it would silently mix 5,048 old chunks into the "new" half. That is why this is a separate
probe with an explicit filter rather than a re-run.

    uv run python logs/p1/step10/probe_deployed_page_numbering.py

Exit 0 = the deployed index passes the §D4 verifier (0 chunks without a page; offset 0 on >=99% of
located heads; no +/-1 cluster).
"""
from __future__ import annotations

import collections
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

PDF = ROOT / "data" / "base_textbooks" / "feynman-lectures-on-physics-volume1.pdf"
DB = ROOT / "data" / "synapse.db"
OUT = ROOT / "logs/p1/step10/page_numbering_deployed.json"

DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"
DOC_OLD = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"

HEAD_ZERO_FLOOR = 0.99


def _load_step6():
    """Import the Step 6 probe so the oracle and the measurement code are literally the same."""
    spec = importlib.util.spec_from_file_location(
        "step6_probe", ROOT / "logs" / "p1" / "step6" / "probe_page_numbering.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def deployed_items(con: sqlite3.Connection, doc_id: str) -> list[tuple[int | None, str]]:
    """(page_number, text) for every chunk of ONE document, in ingest order."""
    rows = con.execute(
        "SELECT page_number, text FROM chunks WHERE document_id = ? ORDER BY chunk_index",
        (doc_id,),
    ).fetchall()
    return [(p, t) for p, t in rows]


def main() -> int:
    probe = _load_step6()

    if not PDF.exists():
        print(f"!! PDF not found: {PDF}")
        return 1

    PageStore = probe._load_pagestore()
    store = PageStore(str(PDF))
    con = sqlite3.connect(DB)

    failures: list[str] = []
    try:
        pdf_norm = {p: probe._norm(store.text(p)) for p in range(1, store.n_pages + 1)}
        print("=" * 88)
        print("§3a — DEPLOYED page_number vs the PyMuPDF oracle")
        print("=" * 88)
        print(f"  PDF pages: {store.n_pages}   oracle: PageStore (PyMuPDF), window ±{probe.WINDOW}")

        result: dict = {"pdf_pages": store.n_pages, "documents": {}}
        for label, doc_id in (("new (7ba61432)", DOC_NEW), ("old (6d55c52b)", DOC_OLD)):
            is_new = doc_id == DOC_NEW
            items = deployed_items(con, doc_id)
            n_null = sum(1 for p, _ in items if p is None)
            distinct = len({p for p, _ in items if p is not None})
            print(f"\n  [{label}] chunks={len(items)}  page_number NULL={n_null}  "
                  f"distinct pages={distinct}")
            # The OLD document is the BASELINE, not the thing under test: its ±1 cluster is the
            # §D4 defect this fix removed, so it is reported, never asserted on.
            if n_null and is_new:
                failures.append(f"{label}: {n_null} chunks have no page_number")

            per_mode = {}
            for mode in ("all_chunks", "first_per_page"):
                m = probe._measure(probe._sample(items, mode), pdf_norm)
                per_mode[mode] = m
                dist = m["head_offset_distribution"]
                top = ", ".join(f"{k}:{v}" for k, v in list(dist.items())[:6] if k != "located")
                print(f"      {mode:16} n={m['considered']:5}  head located={m['head_located']:5}  "
                      f"unlocatable={m['head_not_locatable']:5}  "
                      f"offset0={m['head_offset_zero_fraction']:.4f}   [{top}]")
                if mode == "all_chunks" and is_new and \
                        m["head_offset_zero_fraction"] < HEAD_ZERO_FLOOR:
                    failures.append(
                        f"{label}: offset 0 on only "
                        f"{m['head_offset_zero_fraction']:.4f} of located heads "
                        f"(floor {HEAD_ZERO_FLOOR}) — the ±1 cluster did not collapse")
            if not is_new:
                print("      (baseline only — the old path's ±1 cluster is the §D4 defect, "
                      "not a regression; not asserted on)")
            result["documents"][label] = {
                "doc_id": doc_id, "chunks": len(items), "page_number_null": n_null,
                "distinct_pages": distinct, "modes": per_mode,
                "asserted_on": is_new,
            }

        new_all = result["documents"]["new (7ba61432)"]["modes"]["all_chunks"]
        old_all = result["documents"]["old (6d55c52b)"]["modes"]["all_chunks"]
        print("\n  ── the comparison the fix predicted ──")
        print(f"      old path, all chunks : offset0 = {old_all['head_offset_zero_fraction']:.4f}")
        print(f"      new path, all chunks : offset0 = {new_all['head_offset_zero_fraction']:.4f}")

        result["verdict"] = "FAIL" if failures else "PASS"
        OUT.write_text(json.dumps(result, indent=2))
        print(f"\n  wrote {OUT.relative_to(ROOT)}")
    finally:
        store.close()
        con.close()

    print()
    print("=" * 88)
    if failures:
        print("§3a VERDICT: FAIL")
        for f in failures:
            print(f"  !! {f}")
        print("=" * 88)
        return 1
    print("§3a VERDICT: PASS — the deployed index speaks PDF-page coordinates")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
