"""Docling-based PDF parser with memory-safe page iteration and GPU support."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch
from loguru import logger


# -- Data contracts ------------------------------------------------------------

@dataclass
class PageContent:
    page_number: int
    text: str
    tables: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    document_id: str
    filename: str
    full_text: str
    pages: list[PageContent]
    page_count: int
    char_count: int
    title: Optional[str] = None
    subject: Optional[str] = None


# -- Parser --------------------------------------------------------------------

class PDFParser:
    """
    Wraps Docling DocumentConverter.
    - Preserves heading hierarchy and table content.
    - GPU-accelerated when use_gpu=True (requires docling>=2.x with CUDA).
    - Memory-safe: clears CUDA cache after each document on GPU systems.
    - Falls back to plain text extraction on Docling error.
    """

    def __init__(
        self,
        do_ocr: bool = False,
        do_table_structure: bool = True,
        use_gpu: bool = False,
    ) -> None:
        self._do_ocr = do_ocr
        self._do_table_structure = do_table_structure
        self._use_gpu = use_gpu
        self._converter = None  # lazy-loaded

    def _get_converter(self):
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            opts = PdfPipelineOptions()
            opts.do_ocr = self._do_ocr
            opts.do_table_structure = self._do_table_structure

            if self._use_gpu and torch.cuda.is_available():
                try:
                    from docling.datamodel.pipeline_options import (
                        AcceleratorDevice,
                        AcceleratorOptions,
                    )
                    opts.accelerator_options = AcceleratorOptions(
                        device=AcceleratorDevice.CUDA,
                        num_threads=4,
                    )
                    logger.info("Docling: GPU acceleration enabled (CUDA)")
                except ImportError:
                    logger.warning(
                        "Docling AcceleratorOptions not available -- falling back to CPU"
                    )

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=opts)
                }
            )
            logger.info(
                "Docling DocumentConverter initialised (OCR={}, GPU={})",
                self._do_ocr,
                self._use_gpu and torch.cuda.is_available(),
            )
        return self._converter

    def parse(self, pdf_path: str | Path) -> ParsedDocument:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        logger.info("Parsing PDF: {}", path.name)
        document_id = str(uuid.uuid4())

        try:
            result = self._get_converter().convert(str(path))
            doc = result.document

            full_text = doc.export_to_markdown()
            page_count = len(doc.pages) if hasattr(doc, "pages") else 1
            pages = self._extract_pages(doc, page_count, full_text)
            title = self._extract_title(doc)

            parsed = ParsedDocument(
                document_id=document_id,
                filename=path.name,
                full_text=full_text,
                pages=pages,
                page_count=page_count,
                char_count=len(full_text),
                title=title,
            )
            logger.success(
                "Parsed '{}': {} pages, {:,} chars",
                path.name, page_count, len(full_text),
            )
            return parsed

        except Exception as exc:
            logger.warning("Docling failed ({}), using plain text fallback", exc)
            return self._fallback_parse(path, document_id)
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    # -- Internals -------------------------------------------------------------

    def _extract_pages(self, doc, page_count: int, full_text: str) -> list[PageContent]:
        """
        Build per-page text by inspecting element provenance.
        Falls back to splitting full_text evenly if provenance is unavailable.
        """
        try:
            page_buckets: dict[int, list[str]] = {i: [] for i in range(1, page_count + 1)}
            for element, _ in doc.iterate_items():
                text = getattr(element, "text", None)
                if not text:
                    continue
                prov = getattr(element, "prov", [])
                if prov:
                    for p in prov:
                        pg = getattr(p, "page_no", 1)
                        page_buckets.setdefault(pg, []).append(text)
                else:
                    page_buckets[1].append(text)

            return [
                PageContent(page_number=pg, text="\n".join(texts))
                for pg, texts in sorted(page_buckets.items())
                if texts
            ]
        except Exception:
            lines = full_text.splitlines()
            chunk_size = max(1, len(lines) // max(page_count, 1))
            pages = []
            for i in range(page_count):
                segment = "\n".join(lines[i * chunk_size : (i + 1) * chunk_size])
                pages.append(PageContent(page_number=i + 1, text=segment))
            return pages

    def _extract_title(self, doc) -> Optional[str]:
        try:
            for element, level in doc.iterate_items():
                from docling.datamodel.document import SectionHeaderItem
                if isinstance(element, SectionHeaderItem) and level == 1:
                    return element.text[:200]
        except Exception:
            pass
        return None

    @staticmethod
    def _fallback_parse(path: Path, document_id: str) -> ParsedDocument:
        """Plain-text extraction when Docling fails -- keeps pipeline alive."""
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                pages = [
                    PageContent(page_number=i + 1, text=p.extract_text() or "")
                    for i, p in enumerate(pdf.pages)
                ]
                full_text = "\n\n".join(pg.text for pg in pages)
                return ParsedDocument(
                    document_id=document_id,
                    filename=path.name,
                    full_text=full_text,
                    pages=pages,
                    page_count=len(pages),
                    char_count=len(full_text),
                )
        except Exception:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
            return ParsedDocument(
                document_id=document_id,
                filename=path.name,
                full_text=text,
                pages=[PageContent(page_number=1, text=text)],
                page_count=1,
                char_count=len(text),
            )
