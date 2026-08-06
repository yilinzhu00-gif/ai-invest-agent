from pydantic import BaseModel, ConfigDict, Field


class DocumentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    block_type: str = Field(pattern="^(text|table)$")
    text: str
    bbox: list[float] | None = None
    parser: str
    confidence: float = Field(ge=0, le=1)


class TableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=0)
    column: int = Field(ge=0)
    text: str
    bbox: list[float] | None = None
    is_header: bool = False


class ParsedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    cells: list[TableCell] = Field(min_length=1)
    header_rows: list[int] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    bbox: list[float] | None = None
    source_pages: list[int] = Field(default_factory=list)
    merge_confidence: float = Field(default=1, ge=0, le=1)
    needs_review: bool = False

    @property
    def retrieval_text(self) -> str:
        return "\n".join(cell.text for cell in self.cells)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_version: str
    blocks: list[DocumentBlock] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
