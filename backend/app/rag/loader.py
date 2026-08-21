"""Load financial source files into citation-preserving retrieval chunks.

The loader is deliberately independent from the HTTP upload boundary.  It is
useful for an ingestion worker, a local evaluation, or a one-off index build,
while preserving the source file and PDF page for every chunk.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

from backend.app.domain.knowledge.chunker import chunk_text

SUPPORTED_SUFFIXES = {".pdf", ".md", ".html", ".htm", ".csv", ".txt"}


@dataclass(frozen=True)
class DocumentChunk:
    """One searchable excerpt and the metadata needed to cite it."""

    id: str
    text: str
    source_path: str
    source_sha256: str
    page_number: int
    document_type: str = "other"
    symbol: str | None = None
    workspace_id: str | None = None
    allowed_principals: frozenset[str] = frozenset()
    metadata: dict[str, object] = field(default_factory=dict)


def load_document(
    path: str | Path,
    *,
    document_type: str = "other",
    symbol: str | None = None,
    workspace_id: str | None = None,
    allowed_principals: frozenset[str] = frozenset(),
    max_characters: int = 800,
    overlap: int = 100,
) -> list[DocumentChunk]:
    """Parse one supported file and split each page into bounded chunks.

    PDF extraction uses ``pypdf`` and keeps real page boundaries.  A scanned
    PDF yields no chunks until the existing OCR worker supplies text; this is
    preferable to inventing citations for a page that was not extracted.
    """

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported document type: {suffix or '<none>'}")
    if not source.is_file():
        raise ValueError("document is not a regular file")
    if max_characters < 1 or overlap < 0 or overlap >= max_characters:
        raise ValueError("overlap must be non-negative and smaller than max_characters")

    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    pages = _extract_pages(source)
    chunks: list[DocumentChunk] = []
    for page_number, page_text in pages:
        for index, text in enumerate(
            chunk_text(page_text, max_characters=max_characters, overlap=overlap)
        ):
            chunk_id = f"{source_hash[:16]}:p{page_number}:c{index}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    text=text,
                    source_path=str(source),
                    source_sha256=source_hash,
                    page_number=page_number,
                    document_type=document_type,
                    symbol=symbol,
                    workspace_id=workspace_id,
                    allowed_principals=allowed_principals,
                    metadata={
                        "filename": source.name,
                        "page_number": page_number,
                        "chunk_index": index,
                        "document_type": document_type,
                        "symbol": symbol,
                        "workspace_id": workspace_id,
                    },
                )
            )
    return chunks


def load_documents(
    paths: Iterable[str | Path],
    *,
    document_type: str = "other",
    symbol: str | None = None,
    workspace_id: str | None = None,
    allowed_principals: frozenset[str] = frozenset(),
    max_characters: int = 800,
    overlap: int = 100,
) -> list[DocumentChunk]:
    """Load several files in stable path order for reproducible indexing."""

    return [
        chunk
        for path in sorted((Path(item) for item in paths), key=lambda item: str(item))
        for chunk in load_document(
            path,
            document_type=document_type,
            symbol=symbol,
            workspace_id=workspace_id,
            allowed_principals=allowed_principals,
            max_characters=max_characters,
            overlap=overlap,
        )
    ]


def _extract_pages(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        return [
            (number, page.extract_text() or "")
            for number, page in enumerate(reader.pages, start=1)
        ]

    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        raw = _strip_html(raw)
    elif path.suffix.lower() == ".csv":
        rows = csv.reader(raw.splitlines())
        raw = "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
    return [(1, raw)]


def _strip_html(value: str) -> str:
    value = re.sub(
        r"<script\b[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL
    )
    value = re.sub(
        r"<style\b[^>]*>.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL
    )
    value = re.sub(r"<[^>]+>", " ", value)
    return unescape(value)


__all__ = ["SUPPORTED_SUFFIXES", "DocumentChunk", "load_document", "load_documents"]
