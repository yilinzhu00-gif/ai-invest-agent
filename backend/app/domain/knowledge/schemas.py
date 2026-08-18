"""Public contracts for uploaded evidence and citation-preserving search."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DocumentType = Literal["announcement", "research_report", "other"]


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
