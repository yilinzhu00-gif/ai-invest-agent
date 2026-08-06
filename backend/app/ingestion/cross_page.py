from dataclasses import dataclass

from backend.app.ingestion.schemas import ParsedTable


@dataclass(frozen=True)
class TableMergeResult:
    merged: ParsedTable | None
    merge_confidence: float
    needs_review: bool


def merge_adjacent_tables(
    previous: ParsedTable, candidate: ParsedTable, *, threshold: float = 0.90
) -> TableMergeResult:
    """Merge only adjacent pages with continuous shape/header/unit evidence."""
    if candidate.page_number != previous.page_number + 1:
        return TableMergeResult(None, 0, True)
    previous_columns = max(cell.column for cell in previous.cells) + 1
    candidate_columns = max(cell.column for cell in candidate.cells) + 1
    same_columns = previous_columns == candidate_columns
    same_headers = _header_text(previous) == _header_text(candidate)
    same_units = set(previous.units) == set(candidate.units)
    confidence = (0.40 if same_columns else 0) + (0.35 if same_headers else 0) + (0.25 if same_units else 0)
    if confidence < threshold:
        return TableMergeResult(None, confidence, True)
    return TableMergeResult(
        ParsedTable(
            page_number=previous.page_number,
            cells=[*previous.cells, *candidate.cells],
            header_rows=previous.header_rows,
            units=previous.units,
            bbox=previous.bbox,
            source_pages=[previous.page_number, candidate.page_number],
            merge_confidence=confidence,
        ),
        confidence,
        False,
    )


def _header_text(table: ParsedTable) -> tuple[str, ...]:
    return tuple(cell.text for cell in table.cells if cell.row in table.header_rows)
