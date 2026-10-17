"""E2 — Docling → parent chunks **with per-character page provenance**.

The repo already parses with Docling (``parser.py``), but it flattens the document to pages
and discards both the heading hierarchy and the per-element provenance. This module keeps
them:

* ``HybridChunker`` splits on heading/section boundaries up to ``parent_max_tokens`` — the
  *parents* the semantic chunker (E1) and the late-chunk embedder (E3) draw context from.
* each parent carries a **char → page map** built from ``meta.doc_items[].prov[].charspan`` /
  ``page_no``, so a child's page number is the page its characters actually came from rather
  than the chunk-start fuzz of ``chunker._page_for_offset`` (§D4).

Docling semantics this relies on (verified against Docling 2.117, 2026-10-17):
``Prov.charspan`` is relative to the **item's own** text, and an item that crosses a page
break carries one ``prov`` entry per page, partitioning its text — which is exactly the
boundary information the map needs. Formula items carry no text (``<!-- formula-not-decoded -->``
after serialisation) but do carry provenance, so they are placed zero-width at the cursor.

Wraps ``Labs/Week_6/sv_rag_pipeline/src/svrag/document_converter.py`` (which returns bare
Docling chunks with no provenance) with the page map and a settings-driven parent size.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.models import ParentChunk


class ParentChunker:
    """Docling ``DocumentConverter`` + ``HybridChunker``, returning parents with provenance."""

    def __init__(
        self,
        settings: Settings | None = None,
        converter: Any = None,
        chunker: Any = None,
    ) -> None:
        self._cfg = settings or get_settings()
        self._converter = converter  # injectable for tests
        self._chunker = chunker

    # -- Lazily-built Docling pieces (mirror parser.PDFParser) ------------------

    def _get_converter(self):
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            opts = PdfPipelineOptions()
            opts.do_ocr = False           # the textbook PDFs carry a text layer
            opts.do_table_structure = True
            self._converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
            )
            logger.info("Docling DocumentConverter ready (OCR=False, table structure=True)")
        return self._converter

    def _get_chunker(self):
        if self._chunker is None:
            from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
            from docling_core.transforms.chunker.tokenizer.huggingface import (
                HuggingFaceTokenizer,
            )

            # The modern constructor takes a tokenizer object; the legacy ``max_tokens=``
            # shorthand is deprecated and will be removed. The tokenizer model below is
            # Docling's own default, so chunk boundaries are unchanged by the migration.
            tokenizer = HuggingFaceTokenizer.from_pretrained(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                max_tokens=self._cfg.parent_max_tokens,
            )
            self._chunker = HybridChunker(tokenizer=tokenizer)
            logger.info("HybridChunker ready (max_tokens={})", self._cfg.parent_max_tokens)
        return self._chunker

    # -- Public API ------------------------------------------------------------

    def convert(self, pdf_path: str | Path) -> tuple[Any, list[ParentChunk]]:
        """Convert ``pdf_path`` and return ``(DoclingDocument, ParentChunk[])``.

        The document is returned alongside the parents because the downstream E1/E3 stages
        need it too (the serialiser and the doc-wide element table live on it).
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        logger.info("Converting for parent chunks: {}", path.name)
        doc = self._get_converter().convert(str(path)).document
        raw_chunks = list(self._get_chunker().chunk(doc))
        item_texts = _item_texts(doc)

        parents = [_to_parent(i, chunk, item_texts) for i, chunk in enumerate(raw_chunks)]
        logger.success(
            "Parent chunks for '{}': {} parents, {} pages",
            path.name, len(parents), len(getattr(doc, "pages", {})),
        )
        return doc, parents


# -- Internals -----------------------------------------------------------------

def _item_texts(doc) -> dict[str, str]:
    """``self_ref`` → text for every text-bearing element (formula items have none)."""
    texts: dict[str, str] = {}
    for element, _level in doc.iterate_items():
        text = getattr(element, "text", None)
        if text:
            texts[element.self_ref] = text
    return texts


def _to_parent(index: int, doc_chunk, item_texts: dict[str, str]) -> ParentChunk:
    page_map = _build_page_map(doc_chunk, item_texts)
    if not page_map:
        # Loud, not silent. A parent with no provenance yields children whose page_number is
        # None, which breaks page citations downstream; P0's "silent fallbacks killed" pass
        # exists precisely so this class of degradation does not reappear unannounced.
        logger.warning(
            "Parent {} has no page provenance — its children will carry no page_number "
            "({} chars, {} elements)",
            index, len(doc_chunk.text), len(doc_chunk.meta.doc_items),
        )
    return ParentChunk(
        parent_id=index,
        text=doc_chunk.text,
        headings=list(doc_chunk.meta.headings or []),
        page_map=page_map,
    )


def _build_page_map(doc_chunk, item_texts: dict[str, str]) -> dict[int, int]:
    """Map a char offset in ``doc_chunk.text`` to its PDF page, from element provenance.

    Walks the chunk's elements in order, locating each one's text in the serialised chunk
    text with a forward-only cursor (the serialiser emits them in document order), then
    translates that element's per-page ``prov`` charspans — which are relative to the
    element's own text — into chunk-text offsets.
    """
    text = doc_chunk.text
    page_map: dict[int, int] = {}
    cursor = 0

    for item in doc_chunk.meta.doc_items:
        item_text = item_texts.get(item.self_ref, "")
        pos = text.find(item_text, cursor) if item_text else -1
        if pos < 0:
            # A formula (text=None) or an element the serialiser reordered: place it
            # zero-width at the cursor so its page is still recorded, and leave the cursor
            # where it is — the next element is found by searching forward past it anyway.
            pos, span = cursor, 0
        else:
            span = len(item_text)
            cursor = pos + span

        for prov in item.prov:
            start = prov.charspan[0]
            if span and start >= span:
                continue  # charspan beyond the text we located — nothing to attribute
            page_map[pos + start] = prov.page_no

    if page_map and 0 not in page_map:
        # No element claimed offset 0: anchor the first page there so page_for_offset has a
        # floor and every parent reports at least one page.
        page_map[0] = page_map[min(page_map)]
    return page_map
