from pathlib import Path

import pytest

from backend.app.ingestion.cross_page import merge_adjacent_tables
from backend.app.ingestion.parser import DocumentParser, ExtractedPage
from backend.app.ingestion.schemas import ParsedTable, TableCell


class RecordingOCR:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def extract(self, page_number: int, image_bytes: bytes) -> tuple[str, float]:
        self.calls.append(page_number)
        return "扫描页文字", 0.94


@pytest.mark.asyncio
async def test_native_page_keeps_native_text_and_skips_ocr(tmp_path: Path) -> None:
    document = tmp_path / "native.md"
    document.write_text("# 原生报告\n\n这里有足够的原生正文。")
    ocr = RecordingOCR()
    parser = DocumentParser(ocr=ocr, extractor=lambda _path: [ExtractedPage(1, "原生正文" * 20)])

    result = await parser.parse_path(document)

    assert ocr.calls == []
    assert result.blocks[0].text.startswith("原生正文")
    assert result.blocks[0].parser == "native"


@pytest.mark.asyncio
async def test_low_density_page_uses_ocr_without_duplicate_native_text(tmp_path: Path) -> None:
    document = tmp_path / "scanned.png"
    document.write_bytes(b"not-a-real-image")
    ocr = RecordingOCR()
    parser = DocumentParser(ocr=ocr, extractor=lambda _path: [ExtractedPage(1, "", b"image")])

    result = await parser.parse_path(document)

    assert ocr.calls == [1]
    assert [block.text for block in result.blocks] == ["扫描页文字"]
    assert result.blocks[0].parser == "ocr"
    assert result.blocks[0].confidence == 0.94


def table(page: int, unit: str, header: str = "项目") -> ParsedTable:
    return ParsedTable(
        page_number=page,
        cells=[
            TableCell(row=0, column=0, text=header),
            TableCell(row=0, column=1, text=unit),
            TableCell(row=1, column=0, text="营业收入"),
            TableCell(row=1, column=1, text="-12.5%"),
        ],
        header_rows=[0],
        units=[unit],
        bbox=[0, 0, 100, 30],
    )


def test_table_preserves_cells_units_and_low_confidence_merge_is_reviewable() -> None:
    previous = table(3, "亿元")
    candidate = table(4, "万元")

    result = merge_adjacent_tables(previous, candidate, threshold=0.90)

    assert result.merged is None
    assert result.needs_review is True
    assert result.merge_confidence < 0.90
    assert candidate.cells[3].text == "-12.5%"
