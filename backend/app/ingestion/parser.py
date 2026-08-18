import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.app.ingestion.normalizer import normalize_retrieval_text
from backend.app.ingestion.ocr import OCRExtractor
from backend.app.ingestion.page_classifier import PageKind, classify_page
from backend.app.ingestion.schemas import DocumentBlock, ParsedDocument

SUPPORTED_SUFFIXES = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".md", ".html", ".csv", ".png", ".jpg", ".jpeg"
}


class DocumentSafetyError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    native_text: str
    image_bytes: bytes | None = None


class DocumentParser:
    parser_version = "p2-05-docling-v1"

    def __init__(
        self,
        *,
        ocr: OCRExtractor | None = None,
        extractor: Callable[[Path], Sequence[ExtractedPage]] | None = None,
        max_bytes: int = 50 * 1024 * 1024,
        max_pages: int = 500,
    ) -> None:
        self.ocr = ocr
        self.extractor = extractor or _extract_pages
        self.max_bytes = max_bytes
        self.max_pages = max_pages

    async def parse_path(self, path: Path) -> ParsedDocument:
        self._validate_file(path)
        pages = list(self.extractor(path))
        if len(pages) > self.max_pages:
            raise DocumentSafetyError(f"document exceeds {self.max_pages} pages")
        blocks: list[DocumentBlock] = []
        for page in pages:
            kind = classify_page(page.native_text)
            if kind is PageKind.NATIVE:
                text, confidence, parser = page.native_text, 1.0, "native"
            elif self.ocr is not None and page.image_bytes is not None:
                text, confidence = await self.ocr.extract(page.page_number, page.image_bytes)
                parser = "ocr"
            else:
                text, confidence, parser = page.native_text, 0.0, "native_sparse"
            normalized = normalize_retrieval_text(text)
            if normalized:
                blocks.append(
                    DocumentBlock(
                        page_number=page.page_number,
                        block_type="text",
                        text=normalized,
                        parser=parser,
                        confidence=confidence,
                    )
                )
        return ParsedDocument(
            parser_version=self.parser_version,
            page_count=len(pages),
            blocks=blocks,
        )

    def _validate_file(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise DocumentSafetyError("unsupported document type")
        if not path.is_file():
            raise DocumentSafetyError("document is not a regular file")
        if path.stat().st_size > self.max_bytes:
            raise DocumentSafetyError("document exceeds 50 MiB")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_pages(path: Path) -> Sequence[ExtractedPage]:
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_pages(path)
    if path.suffix.lower() in {".md", ".html", ".csv"}:
        return [ExtractedPage(1, path.read_text(encoding="utf-8"))]
    return _extract_with_docling(path)


def _extract_pdf_pages(path: Path) -> Sequence[ExtractedPage]:
    """Keep the PDF's real page boundaries for reproducible citations.

    OCR remains an explicit worker concern.  A scanned page therefore has no
    invented text here and is surfaced to the caller as needing OCR.
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [
        ExtractedPage(page_number=index, native_text=page.extract_text() or "")
        for index, page in enumerate(reader.pages, start=1)
    ]


def _extract_with_docling(path: Path) -> Sequence[ExtractedPage]:
    """Worker-only Docling adapter; model downloads/configuration stay outside the API image."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as error:
        raise RuntimeError("install the document-worker extra to parse this file type") from error
    converted = DocumentConverter().convert(path)
    return [ExtractedPage(1, converted.document.export_to_markdown())]
