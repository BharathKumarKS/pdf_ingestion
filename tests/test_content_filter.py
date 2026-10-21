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


# ── Signals 4 and 5 — added 2026-10-21, after the re-ingest zeroed the page bounds ────────────
#
# Real rows from doc `7ba61432`. The band boundaries are MEASURED, not assumed: the TOC is
# pages 22-34 (77 chunks). §I39's band table records 19 chunks on pages 20-26 and counts the rest
# as *body*, which is why its "0 body false positives" claim did not reproduce — a false-positive
# count over "pages 31-900" includes ~55 genuine TOC chunks.

# TOC rows (p33 idx120, p34 idx121) — dot-leader listings: no keyword, no index heading, no pipes.
TOC_ROW = ("37-1 Atomic mechanics . . . . . . . . . . . . . . ., 1 = . . . . . . . . . . . . . . . . "
           "37-1. 37-2 An experiment with bullets . . . . . . . . .")
TOC_ROW2 = ("The Relation of Wave and Particle Viewpoints, 1 = . 38-1 Probability wave amplitudes "
            ". . . . . . . . . . . . . . ., 1 = . . . . . . . . . . . . . . . . 38-1. 38-2")
# Real BODY prose a bare dot-leader signal would wrongly drop (p661 idx2522) — the reason signal 4
# also requires a section number.
PROSE_DOT_RUN = ("Something like: click . . . . . click-click . . . click . . . . . . . . click . . . . "
                 "click-click . . . . . . click . . .")
# Real index rows (p938 idx3610, idx3611) — NOT pipe tables, so signals 2 and 3 both miss them.
INDEX_DENSE = ("Transformation of \u223c , III-6-1 ff, 1 = and parity conservation, III-18-5. "
               "Analog computer, 25-15, 1 = Attenuation, 31-15. Angle, 1 = Avogadro's number, "
               "41-18, II-8-9.")
INDEX_DENSE2 = ("Brewster's \u223c , 33-10, 1 = Axial vector, 20-6, 52-10 ff, 52-17. of incidence, "
                "26-6, II-33-1 of precession, II-34-7, III-34-7, 1 = B. of reflection, 26-6, "
                "II-33-1, 1 = Bar (unit), 47-7. Angstrom (unit),")


def test_toc_listings_are_not_content():
    assert cf.is_toc_layout(TOC_ROW) is True
    assert cf.is_content(TOC_ROW) is False
    assert cf.is_content(TOC_ROW2) is False


def test_dot_leader_run_alone_is_not_enough():
    """Real prose with a dot-leader run must stay content — p661's ratchet discussion."""
    assert cf.is_toc_layout(PROSE_DOT_RUN) is False
    assert cf.is_content(PROSE_DOT_RUN) is True


def test_index_rows_without_a_pipe_table_are_not_content():
    """Signals 2 and 3 fire on ZERO chunks of this corpus; signal 5 is what carries the index."""
    assert cf.is_index_layout(INDEX_DENSE) is False
    assert cf.is_index_layout(INDEX_DENSE2) is False
    assert cf.is_index_density(INDEX_DENSE) is True
    assert cf.is_content(INDEX_DENSE) is False
    assert cf.is_content(INDEX_DENSE2) is False


def test_prose_citing_a_page_reference_stays_content():
    """The density threshold is what keeps ordinary prose that mentions a section number out."""
    assert cf.is_content("As we saw in Chapter 27-12, the field falls off as 1/r2.") is True


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
