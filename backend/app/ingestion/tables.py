import re

from backend.app.ingestion.schemas import ParsedTable, TableCell

UNIT_PATTERN = re.compile(r"(?:人民币|美元)?(?:万|亿|千)?元|%|股|吨")


def build_table(
    *, page_number: int, rows: list[list[str]], bbox: list[float] | None = None
) -> ParsedTable:
    """Keep every source cell verbatim; normalized values belong to later consumers."""
    cells = [
        TableCell(row=row_index, column=column_index, text=value, is_header=row_index == 0)
        for row_index, row in enumerate(rows)
        for column_index, value in enumerate(row)
    ]
    units = sorted({match.group(0) for cell in cells for match in UNIT_PATTERN.finditer(cell.text)})
    return ParsedTable(
        page_number=page_number,
        cells=cells,
        header_rows=[0] if rows else [],
        units=units,
        bbox=bbox,
        source_pages=[page_number],
    )
