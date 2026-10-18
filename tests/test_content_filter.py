"""Tests for the E5 chunk-level front/back-matter classifier (``content_filter.py``).

Every string here is either a real corpus row (``data/synapse.db``, page 936 / 954 / 22) or a
synthetic minimal shape of one, so the tests pin the *measured* behaviour of the rule rather
than a guess. The acceptance test from the plan — "the known mixed page (DB 936) splits
correctly" — is ``test_page_936_splits_content_from_index``.
"""
from __future__ import annotations

from src.pdf_ingestion import content_filter as cf
from src.pdf_ingestion.chunker import SemanticChunker
from src.pdf_ingestion.models import ParentChunk

# ── Real page-936 rows (verbatim from the corpus) ─────────────────────────────

# The last content chunk of the chapter (chunk 4660) — prose, must stay content.
CONTENT_PROSE = (
    "The marvelous thing about it all is that for such a wide range of important, strong "
    "phenomena we have found a principle which is almost valid."
)
# The boundary chunk 4668: prose, but its text ends with the index heading.
BOUNDARY = CONTENT_PROSE + "\n\n## Index\n"
# Index rows (chunks 4669, 4672, 4673) — two-column table, "term, page-ref" entries.
INDEX_ROW = (
    "| A Aberration, 27-12 ff, 34-18 ff Chromatic \u223c , 27-13 Spherical \u223c , 27-13, "
    "36-6 of an electron microscope, II-29-10 Absolute zero, 1-8, 2-10, 44-19, 44-22 |"
)
INDEX_ROW2 = (
    "| Angle                    | Avogadro's number, 41-18, II-8-9                    |\n"
    "| Brewster's \u223c , 33-10    | Axial vector, 20-6, 52-10 ff, 52-17                  |"
)
# The index heading chunk (4671) and a Name-Index heading chunk (4951).
INDEX_HEADING = "## Index -1\n\n| Transformation of \u223c , III-6-1 ff | and parity conservation, III-18-5 |"
NAME_INDEX_HEADING = "## Name Index\n\n| A Adams, John C. (1819-92), 7-10 |"
# Table furniture: a separator row (chunk 4670) — no alphanumerics.
FURNITURE = "|" + "-" * 200 + "|"


# ── Signal 1: keyword front/back matter ───────────────────────────────────────

def test_copyright_and_isbn_are_not_content():
    assert cf.is_content("Copyright \u00a9 2010 by the California Institute of Technology.") is False
    assert cf.is_content("ISBN 978-0-465-02494-1\nLibrary of Congress Cataloging") is False


def test_table_of_contents_marker_is_not_content():
    assert cf.is_content("Table of Contents\n\nChapter 1. Atoms in Motion ...") is False


def test_plain_prose_is_content():
    assert cf.is_content(CONTENT_PROSE) is True


# ── Signal 2: index heading (whole line, not substring) ───────────────────────

def test_index_heading_variants_are_not_content():
    for text in (INDEX_HEADING, NAME_INDEX_HEADING, "## Subject Index\n\n| term, 1-2 |"):
        assert cf.is_content(text) is False, text


def test_refractive_index_chapter_heading_stays_content():
    # A real chapter (page 533/534) — "Index" as a substring of a content heading.
    assert cf.is_content("## The Origin of the Refractive Index") is True
    assert cf.is_content("## 31-1 The index of refraction") is True
    assert cf.is_index_heading("## The Origin of the Refractive Index") is False


# ── Signal 3: index-table layout ──────────────────────────────────────────────

def test_index_entry_rows_are_not_content():
    assert cf.is_content(INDEX_ROW) is False
    assert cf.is_content(INDEX_ROW2) is False


def test_content_table_of_bare_numbers_stays_content():
    # A real data table (page 454): pipes + reference-looking tokens, but no "term, ref".
    assert cf.is_content("| 60 \u25e6 | 40-1 / 2 \u25e6 | 60 \u25e6 | 40-1 / 2 \u25e6 |") is True


def test_numeric_data_table_stays_content():
    # Page 122: a table of numbers with no words — still content (carries data).
    assert cf.is_content("| 11 | 17 | 17 | 12 | 20 | 23 |\n| 16 | 12 | 15 | 10 | 18 | 17 |") is True


# ── Furniture + degenerate input ──────────────────────────────────────────────

def test_pure_table_furniture_is_not_content():
    assert cf.is_content(FURNITURE) is False


def test_empty_text_is_not_content():
    assert cf.is_content("") is False
    assert cf.is_content("   \n  ") is False


# ── Acceptance: the mixed page 936 splits ─────────────────────────────────────

def test_page_936_splits_content_from_index():
    # In document order, exactly as the chunker emits them.
    assert cf.is_content(CONTENT_PROSE) is True          # 4660-4667: chapter ending
    assert cf.is_content(BOUNDARY) is False              # 4668: prose + trailing index heading
    assert cf.is_content(INDEX_ROW) is False             # 4669: index body
    assert cf.is_content(FURNITURE) is False             # 4670: separator
    assert cf.is_content(INDEX_HEADING) is False         # 4671: index heading + rows
    assert cf.is_content(INDEX_ROW2) is False            # 4672-4683: index body


# ── Wired into the chunker ────────────────────────────────────────────────────

def _chunker() -> SemanticChunker:
    from src.core.config import Settings

    return SemanticChunker(Settings(semantic_threshold=0.8, chunk_size=512, min_chunk_tokens=0))


def test_chunker_tags_index_children_non_content():
    parent = ParentChunk(parent_id=0, text=INDEX_ROW + "\n\n" + INDEX_ROW2, page_map={0: 936})
    children = _chunker().chunk_parents("doc", "global", [parent])
    assert children
    assert all(c.is_content is False for c in children)


def test_chunker_tags_prose_children_content():
    prose = (CONTENT_PROSE + " ") * 6
    parent = ParentChunk(parent_id=0, text=prose, page_map={0: 1})
    children = _chunker().chunk_parents("doc", "global", [parent])
    assert children
    assert all(c.is_content is True for c in children)
