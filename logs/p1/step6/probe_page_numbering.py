"""Step 6 evidence — does the parent-aware path collapse the §D4 page-number offset?

§D4: the *old* ingest path's chunk ``page_number`` was inferred from a chunk's start offset
(``chunker._page_for_offset``), which is off by 0/−1 on ~45% of pages because the chunker merged
across page boundaries. The parent-aware path (E2/E1) takes ``page_number`` from Docling's
per-element provenance instead, so the offset should collapse to 0.

**The claim under test is precise:** ``page_number`` is the page of the chunk's *start* (the
convention every ``page_number`` in this codebase follows). So the measurement uses the chunk's
**head** — its opening words — as the original ``logs/p0-9/measure_page_offset.py`` did.

**Both paths are measured on the SAME unit.** An independent reviewer flagged that comparing
"first chunk per page" (the old tool's sampling) against "every child" (the natural new-path
sampling) is not apples-to-apples. So the probe measures *both* samplings for *both* paths:

* ``all_chunks`` — every chunk / every child (the primary: the same unit on both sides);
* ``first_per_page`` — the first chunk for each distinct page (the old tool's unit, kept for
  continuity with the recorded §D4 baseline).

The oracle is the PDF page text extracted by PyMuPDF (``PageStore``) — a different extractor from
Docling, and it never sees the page numbers under test. For each chunk the head's opening words are
searched on the PDF pages within ±3 of the claimed page; a unique hit gives the offset
(``page_number − PDF page``).

A chunk's head can be *unlocatable* in the PyMuPDF text (Docling serialises a bullet outline
differently — verified on test_book.pdf chunks 2/5/8/17, whose tails sit exactly on the claimed
page). Those are recorded separately as ``head_not_locatable`` and are **not** evidence about the
page number; a mid/tail fallback is reported for them so nothing is hidden.

The Docling parse of the 968-page book dominates the runtime, so the new-path children are cached
to ``--children-cache`` and reused on later runs.

    uv run python logs/p1/step6/probe_page_numbering.py --pdf data/base_textbooks/test_book.pdf
    uv run python logs/p1/step6/probe_page_numbering.py --children-cache logs/p1/step6/children.json
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import re
import sqlite3
from pathlib import Path

from src.core.config import Settings
from src.pdf_ingestion.chunker import SemanticChunker
from src.pdf_ingestion.parent_chunker import ParentChunker

ROOT = Path(__file__).resolve().parents[3]
REAL_PDF = ROOT / "data" / "base_textbooks" / "feynman-lectures-on-physics-volume1.pdf"
DB = ROOT / "data" / "synapse.db"
WINDOW = 3
MIN_NEEDLE = 30


def _norm(s: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]", " ", " ".join(s.split()).lower()) + " "


def _slices(text: str) -> dict[str, str]:
    """Head/mid/tail needles from a chunk (≥MIN_NEEDLE normalised chars)."""
    body = _norm(text).strip()
    if len(body) < MIN_NEEDLE:
        return {}
    out = {"head": body[:70]}
    if len(body) > 140:
        mid = (len(body) - 70) // 2
        out["mid"] = body[mid:mid + 70]
        out["tail"] = body[-70:]
    return {k: v for k, v in out.items() if len(v) >= MIN_NEEDLE}


def _offset_for(needle: str, claimed: int, pdf_norm: dict[int, str]) -> list[int]:
    """Offsets in ±WINDOW whose PDF page contains ``needle``."""
    return [off for off in range(-WINDOW, WINDOW + 1)
            if claimed + off >= 1 and needle in pdf_norm.get(claimed + off, "")]


def _locate_slice(needle: str, claimed: int, pdf_norm: dict[int, str]):
    """The offset if exactly one PDF page in the window contains ``needle``, else None."""
    hits = _offset_for(needle, claimed, pdf_norm)
    return hits[0] if len(hits) == 1 else None


def _load_pagestore():
    spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts" / "validate_eval_calibration.py")
    vec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vec)
    return vec.PageStore


def _dist(offsets: collections.Counter, total: int) -> dict:
    return {f"{off:+d}": n for off, n in sorted(offsets.items(), key=lambda x: -x[1])} | {"located": total}


def _score(text: str, claimed: int, pdf_norm: dict[int, str]):
    """(head_offset | None, fallback_offset | None, fallback_slice | None)."""
    sl = _slices(text)
    head_off = _locate_slice(sl["head"], claimed, pdf_norm) if "head" in sl else None
    fb_off = fb_slice = None
    for name in ("mid", "tail"):
        if name in sl:
            off = _locate_slice(sl[name], claimed, pdf_norm)
            if off is not None:
                fb_off, fb_slice = off, name
                break
    return head_off, fb_off, fb_slice


def _sample(items: list[tuple[int | None, str]], mode: str) -> list[tuple[int | None, str]]:
    """``all_chunks`` → every item; ``first_per_page`` → the first item per claimed page."""
    if mode == "all_chunks":
        return items
    seen: set[int | None] = set()
    out: list[tuple[int | None, str]] = []
    for page, text in items:
        if page not in seen:
            seen.add(page)
            out.append((page, text))
    return out


def _measure(items: list[tuple[int | None, str]], pdf_norm: dict[int, str]) -> dict:
    """Score (claimed_page, text) pairs; returns the head/fallback breakdown."""
    head: collections.Counter = collections.Counter()
    fb: collections.Counter = collections.Counter()
    n = {"considered": len(items), "head_located": 0, "head_not_locatable": 0,
         "no_page_number": 0, "too_short": 0, "fallback_located": 0, "fallback_unlocatable": 0}
    samples = []
    for page, text in items:
        if page is None:
            n["no_page_number"] += 1
            continue
        if not _slices(text):
            n["too_short"] += 1
            continue
        head_off, fb_off, _fb_slice = _score(text, page, pdf_norm)
        if head_off is not None:
            head[head_off] += 1
            n["head_located"] += 1
        else:
            n["head_not_locatable"] += 1
            if fb_off is not None:
                fb[fb_off] += 1
                n["fallback_located"] += 1
                if fb_off != 0 and len(samples) < 8:
                    samples.append({"claimed_page": page, "fallback_offset": fb_off})
            else:
                n["fallback_unlocatable"] += 1
    return {
        **n,
        "head_offset_distribution": _dist(head, n["head_located"]),
        "head_offset_zero_fraction": round(head.get(0, 0) / max(n["head_located"], 1), 4),
        "unlocatable_head_fallback_offsets": _dist(fb, n["fallback_located"]),
        "fallback_offset_nonzero_samples": samples,
    }


def new_path_items(pdf_path: Path, cache_path: Path | None) -> list[tuple[int | None, str]]:
    """(page_number, text) for every parent-aware child — parsed once, then cached."""
    if cache_path is not None and cache_path.exists():
        return [(r["page"], r["text"]) for r in json.loads(cache_path.read_text())]
    cfg = Settings()
    _doc, parents = ParentChunker(cfg).convert(str(pdf_path))
    children = SemanticChunker(cfg).chunk_parents("probe", "global", parents)
    items = [(c.page_number, c.text) for c in children]
    if cache_path is not None:
        cache_path.write_text(json.dumps([{"page": p, "text": t} for p, t in items]))
    return items


def old_path_items() -> list[tuple[int | None, str]]:
    """(page_number, text) for every chunk in the deployed DB — the old path's output."""
    if not DB.exists():
        return []
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT page_number, text FROM chunks WHERE page_number IS NOT NULL ORDER BY chunk_index"
    ).fetchall()
    con.close()
    return [(p, t) for p, t in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(REAL_PDF))
    ap.add_argument("--no-db", action="store_true", help="skip the old-path (DB) half")
    ap.add_argument("--children-cache", default=None,
                    help="cache the parsed parent-aware children here (avoids re-parsing)")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    cache_path = Path(args.children_cache) if args.children_cache else None
    PageStore = _load_pagestore()
    store = PageStore(str(pdf_path))
    try:
        pdf_norm = {p: _norm(store.text(p)) for p in range(1, store.n_pages + 1)}
        new_items = new_path_items(pdf_path, cache_path)
        old_items = [] if args.no_db else old_path_items()
        out = {
            "pdf": pdf_path.name,
            "new_path_parent_aware": {
                mode: _measure(_sample(new_items, mode), pdf_norm)
                for mode in ("all_chunks", "first_per_page")
            },
            "old_path_deployed_db": (
                {"skipped": "--no-db"} if args.no_db else
                {mode: _measure(_sample(old_items, mode), pdf_norm)
                 for mode in ("all_chunks", "first_per_page")}
            ),
        }
    finally:
        store.close()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
