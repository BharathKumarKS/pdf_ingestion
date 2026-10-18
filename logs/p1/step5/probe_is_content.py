"""Evidence pack for the E5 ``is_content`` independent review (P1 Step 5).

One command, one JSON object, one key per claim. Run from the repo root:

    uv run python logs/p1/step5/probe_is_content.py

Oracle: the real corpus (``data/synapse.db``) plus a page-region ground truth that is
*independent of the classifier* — pages >= 937 are back matter and pages < 34 front matter
(the §E5 facts), and on the mixed page 936 the chunk ids 4669..4683 are the index run while
4660..4668 are the chapter ending. The classifier never sees these page numbers.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from src.pdf_ingestion import content_filter as cf
from src.pdf_ingestion.chunker import SemanticChunker
from src.pdf_ingestion.models import ParentChunk
from src.core.config import Settings

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "data" / "synapse.db"

BACK_MATTER_PAGE = 937   # §E5: the trailing index run starts at p937 for Vol 1
FRONT_MATTER_PAGE = 34   # §E5: the TOC tail runs to ~p33
MIXED_PAGE = 936
MIXED_INDEX_RUN = range(4669, 4684)   # chunks 4669..4683 are the index rows on p936


def corpus_claims() -> dict:
    con = sqlite3.connect(DB)
    rows = con.execute("select chunk_index, page_number, text from chunks order by chunk_index").fetchall()
    con.close()

    fn, fp = [], []          # fn = content the rule dropped; fp = non-content the rule kept
    page936 = {}
    for ci, pg, text in rows:
        classified_content = cf.is_content(text)
        if pg == MIXED_PAGE:
            page936[ci] = classified_content
        if pg is None:
            truth = ci != 0
        elif pg >= BACK_MATTER_PAGE or pg < FRONT_MATTER_PAGE:
            truth = False
        else:
            truth = ci not in MIXED_INDEX_RUN
        if truth and not classified_content:
            fn.append({"chunk_index": ci, "page": pg, "head": text[:60]})
        if not truth and classified_content:
            fp.append({"chunk_index": ci, "page": pg, "head": text[:60]})

    return {
        "n_chunks": len(rows),
        "false_negatives_content_dropped": len(fn),
        "false_negative_samples": fn,
        "false_positives_noncontent_kept": len(fp),
        "false_positive_sample_count": len(fp),
        # The acceptance test from the plan: page 936 splits.
        "page_936_content_chunks_kept": [ci for ci, c in page936.items() if c],
        "page_936_index_chunks_dropped": [ci for ci, c in page936.items() if not c],
    }


def guard_claims() -> dict:
    """Cases that must NOT be dropped (content) and the mixed-page split (from real rows)."""
    return {
        "refractive_index_heading_is_content": cf.is_content("## The Origin of the Refractive Index"),
        "chapter_31_1_index_of_refraction_is_content": cf.is_content("## 31-1 The index of refraction"),
        "content_trig_table_is_content": cf.is_content("| 60 \u25e6 | 40-1 / 2 \u25e6 | 60 \u25e6 | 40-1 / 2 \u25e6 |"),
        "numeric_data_table_is_content": cf.is_content("| 11 | 17 | 17 | 12 | 20 | 23 |\n| 16 | 12 | 15 | 10 | 18 | 17 |"),
        "index_heading_is_not_content": cf.is_content("## Index -1\n\n| Transformation of \u223c , III-6-1 ff | and parity conservation, III-18-5 |"),
        "copyright_is_not_content": cf.is_content("Copyright \u00a9 2010 by the California Institute of Technology."),
        "separator_furniture_is_not_content": cf.is_content("|" + "-" * 200 + "|"),
    }


def wiring_claims() -> dict:
    """The flag is actually produced by the chunker, not just by the helper."""
    ch = SemanticChunker(Settings(semantic_threshold=0.8, chunk_size=512, min_chunk_tokens=0))
    index_row = ("| Angle                    | Avogadro's number, 41-18, II-8-9                    |\n"
                 "| Brewster's \u223c , 33-10    | Axial vector, 20-6, 52-10 ff, 52-17                  |")
    prose = ("The total energy of the system is conserved in all interactions. " * 6)
    idx_children = ch.chunk_parents("d", "global", [ParentChunk(parent_id=0, text=index_row, page_map={0: 936})])
    prose_children = ch.chunk_parents("d", "global", [ParentChunk(parent_id=1, text=prose, page_map={0: 1})])
    return {
        "chunker_tags_index_children_non_content": all(c.is_content is False for c in idx_children),
        "chunker_tags_prose_children_content": all(c.is_content is True for c in prose_children),
        "index_child_count": len(idx_children),
        "prose_child_count": len(prose_children),
    }


def main() -> None:
    print(json.dumps({
        "corpus": corpus_claims(),
        "guards": guard_claims(),
        "wiring": wiring_claims(),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
