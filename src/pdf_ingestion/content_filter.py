"""Chunk-level front/back-matter classification — E5 (``is_content``).

At ingest every chunk is tagged ``is_content: True/False`` from **its own text**, the flag
rides in the Qdrant payload, and retrieval filters on it. This is what *replaces* the
page-number bounds (``min_content_page`` / ``max_content_page``, ``IMPROVEMENTS.md`` §E5):

* the payload ``page_number`` and the PDF page index are offset by 0/−1 on ~45% of pages, so
  a page bound lands differently in the two coordinate systems;
* one page can hold both — DB page 936 carries the last chapter's ending **and** the first
  ~15 index chunks (``## Index -1``), which no single page bound can split.

A text rule is book-agnostic and immune to that ±1 offset. It is *seeded* with the
``_NON_CHAPTER`` keyword list that used to live in ``store.py`` (and was wired only into the
RAPTOR rebuild) and **extended with a structural index rule**, because the keyword list alone
does not catch the book's index: measured on the real corpus (``data/synapse.db``, 5,048
chunks) none of the index rows on page 936 contain a keyword — they are pipe-table rows like
``| Angle | Avogadro's number, 41-18, II-8-9 |`` and the separator rows ``|---…---|``. The
structural rule is what makes the plan's acceptance test (page 936 splits) pass; see
``IMPROVEMENTS.md`` §E5 for the measured precision/recall.

Three text signals, cheapest first:

1. **Keyword** — a front/back-matter marker in the first 500 characters (the promoted
   ``_NON_CHAPTER`` list: TOC, preface, bibliography, errata, copyright, ISBN, …).
2. **Index heading** — a line that is *exactly* an index heading (``## Index -1``,
   ``## Name Index``, ``## Subject Index``). Matched on the whole line, not as a substring:
   ``## The Origin of the Refractive Index`` is a real chapter and must stay content.
3. **Index layout** — the chunk is a two-column table whose rows are index *entries*: a term,
   a comma, then a page reference (``Aberration, 27-12``). Requires the pipe-table shape so a
   content table of bare numbers (``| 10 ◦ | 8 ◦ |``) is not caught.

Plus a trivial fourth: a chunk with no alphanumeric character at all is pure table furniture
(``|---…---|``) and carries nothing, so it is not content. (It keeps numeric tables —
``| 11 | 17 |`` — which *are* content.)

And two signals added 2026-10-21 after the re-ingest zeroed the page bounds (measured on doc
``7ba61432``, 3,796 chunks — see each signal's own comment for the full measurement):

4. **TOC layout** — a dot-leader *run* plus at least one section number (``37-1``). Catches
   72/77 TOC chunks with zero collateral; a bare dot-leader run is rejected because it fires on
   real prose ellipses.
5. **Index density** — ≥⅓ of non-blank lines are ``term, page-ref`` entries, whatever the
   layout. Catches 186/187 index chunks with zero body false positives. This is what carries
   this corpus: signals 2 and 3 fire on **zero** chunks of it.

⚠️ **The known gap has narrowed but not closed.** Signals 1–3 alone caught 5 chunks of this
document. With 4 and 5 added, the TOC (pages 22-34) and the index (pages 937-968) are covered;
what remains is **front-matter prose** — the preface and publisher's note carry no keyword and no
structural marker, and the page bounds that used to cover them are gone (the re-ingest zeroed
them). Recorded as the §E5/§I39 follow-up; do not assume the 242-chunk recall gap measured
pre-re-ingest is still that number — re-measure it per corpus.
"""
from __future__ import annotations

import re

# ── Signal 1: front/back-matter keyword markers ───────────────────────────────
#
# Promoted verbatim from store.py's ``_NON_CHAPTER`` (P0-9 §E5) so the RAPTOR rebuild and
# the ingest-time classifier use one list. Matched case-insensitively against the first 500
# characters, exactly as the old ``_is_chapter`` did.
NON_CHAPTER_MARKERS: tuple[str, ...] = (
    "table of contents", "## preface", "\npreface\n",
    "## bibliography", "bibliography\n", "## subject index",
    "## index\n", "## acknowledgment", "## references\n",
    "list of figures", "list of tables",
    "errata\n", "## errata", "erratum", "typographical error",
    "all rights reserved", "copyright ©", "© 20", "© 19",
    "printed in the united states", "isbn ", "library of congress",
)

_KEYWORD_SAMPLE = 500

# ── Signal 2: an index heading line ───────────────────────────────────────────
#
# ``## Index``, ``## Index -1``, ``## Name Index -2``, ``## Subject Index`` — the whole line,
# optionally with a numeric suffix, and nothing else. ``## The Origin of the Refractive
# Index`` (a real chapter, page 533) does not match.
_INDEX_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:name\s+|subject\s+)?index(?:\s*[-\u2013]?\s*\d+)?\s*$"
)

# ── Signal 3: index-table layout ──────────────────────────────────────────────
#
# An index entry is "term, <page ref>": a comma immediately followed by a page reference
# (``27-12``, ``II-33-1``). The comma is what separates it from a content table cell
# (``| 7-1 / 2 ◦ |``), where the reference-looking token is not preceded by a comma.
_INDEX_ENTRY_RE = re.compile(r",\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")
# At least one entry line: the big index rows can serialise to a *single* line (chunk 4669 on
# page 936 is one 896-char line of entries), so a higher minimum would miss them. The
# pipe-table + entry-fraction conjunction is what keeps content tables out, not this count.
_INDEX_MIN_ENTRIES = 1
_INDEX_ENTRY_FRACTION = 0.34  # ≥ a third of the lines are entries
_INDEX_PIPE_FRACTION = 0.5    # and it is a pipe table (not prose)

_ALNUM_RE = re.compile(r"[A-Za-z0-9]")


# ── Signal 4: a dot-leader run PLUS a section number = a table of contents ────
#
# The keyword list does not catch this book's TOC (no "table of contents" marker survives in the
# chunks), and neither does an index heading or the index-table shape — its rows are dot-leader
# prose lines: "37-1 Atomic mechanics . . . . . . . 37-1. 37-2 An experiment with bullets . . .".
#
# ⚠️ CORRECTED BOUNDARY (measured 2026-10-21, doc `7ba61432`, 3,796 chunks): the TOC is
# **pages 22-34 = 77 chunks**, not the 19 chunks on pages 20-26 that §I39's band table records —
# ~55 TOC chunks were being counted as *body*, which is why the earlier "0 body false positives"
# claim did not reproduce (a false-positive count over "pages 31-900" includes the TOC itself).
# This rule catches **72 of the 77**, with **zero** collateral outside the TOC.
#
# Two shapes were measured and REJECTED:
#   * a dot-leader run alone — it fires on real prose: "click . . . . . click-click . . . click . . ."
#     (p661, the ratchet discussion) and the preface's quoted ellipses (p7-8). Requiring a section
#     number alongside removes exactly those and keeps all 72 TOC catches.
#   * a bare `N-N, N =` literal — catches only 15/77 TOC and, worse, 133/187 *index* chunks, so it
#     is an index signal, not a TOC one.
_DOT_RUN_RE = re.compile(r"(?:\.\s?){4,}")
_SECTION_NUM_RE = re.compile(r"\b\d{1,2}-\d{1,2}\b")


def is_toc_layout(text: str) -> bool:
    """True if the chunk is a table of contents: a dot-leader run AND a section number."""
    if _SECTION_NUM_RE.search(text) is None:
        return False
    return any(_DOT_RUN_RE.search(line) for line in text.splitlines())


# ── Signal 5: page-reference density = the index, in any layout ──────────────
#
# ⚠️ The two index signals above are DEAD on this corpus. Measured 2026-10-21 on doc `7ba61432`:
# `is_index_heading` fires on **0** chunks (no `## Index -1` line survives the chunker) and
# `is_index_layout` fires on **0** (the index does not come through as pipe rows here). So the
# entire index — **pages 937-968, 187 chunks** — passed as content (§I39). They are kept because
# they are book-agnostic and cost nothing, but they are not what carries this corpus.
#
# What does survive is the entry shape itself: a term, a comma, then a page reference. Requiring
# it on a third of the lines keeps content tables out — `| 60° | 8° |` has no comma before the
# reference-looking token. Measured: **186/187 index chunks, 0 body false positives**.
_PAGE_REF_RE = re.compile(r",\s*(?:[IVX]{1,3}-)?\d{1,3}-\d{1,3}")
_PAGE_REF_MIN_LINES = 1
_PAGE_REF_MIN_DENSITY = 0.34


def is_index_density(text: str) -> bool:
    """True if the chunk is dominated by "term, page-ref" entries, whatever its layout."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < _PAGE_REF_MIN_LINES:
        return False
    hits = sum(1 for ln in lines if _PAGE_REF_RE.search(ln))
    return hits >= _PAGE_REF_MIN_LINES and hits / len(lines) >= _PAGE_REF_MIN_DENSITY


def is_index_heading(text: str) -> bool:
    """True if any line is exactly an index heading (``## Index -1``, ``## Name Index``)."""
    return any(
        _INDEX_HEADING_RE.match(line.strip().lower())
        for line in text.splitlines()
    )


def is_index_layout(text: str) -> bool:
    """True if the chunk is an index *table*: pipe rows dominated by "term, page-ref" entries."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    entries = sum(1 for ln in lines if _INDEX_ENTRY_RE.search(ln))
    pipes = sum(1 for ln in lines if ln.strip().startswith("|"))
    return (
        entries >= _INDEX_MIN_ENTRIES
        and entries / len(lines) >= _INDEX_ENTRY_FRACTION
        and pipes / len(lines) >= _INDEX_PIPE_FRACTION
    )


def is_content(text: str) -> bool:
    """Classify a chunk's own text as content (True) or front/back matter (False).

    The single entry point for E5. Called at ingest (``chunker``) and by the RAPTOR rebuild
    (``store.generate_cards_for_document``), and mirrored by the retrieval filter.
    """
    if not text or not text.strip():
        return False
    if any(marker in text.lower()[:_KEYWORD_SAMPLE] for marker in NON_CHAPTER_MARKERS):
        return False
    if is_index_heading(text):
        return False
    if _ALNUM_RE.search(text) is None:
        return False  # pure table furniture (|---…---|) — carries nothing
    if is_index_layout(text):
        return False
    if is_toc_layout(text):
        return False
    if is_index_density(text):
        return False
    return True
