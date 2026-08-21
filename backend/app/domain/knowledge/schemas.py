"""Public contracts for uploaded evidence and citation-preserving search."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DocumentType = Literal[
    "financial_report",
    "announcement",
    "research_report",
    "broker_report",
    "industry_report",
    "policy",
    "other",
]


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    symbol: str | None
    document_type: DocumentType
    source_url: str | None
    version: int
    status: str
    page_count: int
    parsed_block_count: int
    created_at: datetime | None = None


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    document_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=30)


class EvidenceSearchResult(BaseModel):
    """One immutable RAG block with a stable, citation-friendly shape.

    ``text``/``filename``/``page_number`` remain for existing clients.  The
    normalized fields are deliberately emitted as well so every retrieval
    consumer can use the same ``content/source/page/date`` contract.
    """

    evidence_id: str
    document_id: UUID
    document_version: int
    filename: str
    source_url: str | None
    page_number: int
    block_id: str
    text: str
    parser: str
    confidence: float
    bbox: list[float] | None
    content: str | None = None
    source: str | None = None
    page: int | None = None
    date: str | None = None

    @model_validator(mode="after")
    def normalize_citation_fields(self) -> "EvidenceSearchResult":
        if self.content is None:
            self.content = self.text
        if self.source is None:
            self.source = self.filename
        if self.page is None:
            self.page = self.page_number
        return self


class KnowledgeSearchResponse(BaseModel):
    results: list[EvidenceSearchResult]


class TransactionFactEvidence(BaseModel):
    """An unchanged announcement excerpt backing one transaction-fact field."""

    page_number: int
    block_id: str
    text: str


class TransactionFactRow(BaseModel):
    """A fixed research field, never populated from inference or external data."""

    field: str
    value: str
    evidence: list[TransactionFactEvidence]


class TransactionFactsResponse(BaseModel):
    document_id: UUID
    filename: str
    document_version: int
    rows: list[TransactionFactRow]
    boundary: str
