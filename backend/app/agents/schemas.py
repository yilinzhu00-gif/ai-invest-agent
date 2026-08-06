from enum import Enum
from math import isfinite
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentRuntime(str, Enum):
    LANGGRAPH = "langgraph"
    CREWAI = "crewai"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=512)
    locator: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1, max_length=20_000)


class ResearchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10_000)
    citation_ids: list[str] = Field(min_length=1, max_length=8)
    numeric_values: list[float] = Field(default_factory=list, max_length=32)

    @field_validator("numeric_values")
    @classmethod
    def require_finite_numbers(cls, values: list[float]) -> list[float]:
        if not all(isfinite(value) for value in values):
            raise ValueError("numeric values must be finite")
        return values


class ResearchDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=10_000)
    claims: list[ResearchClaim] = Field(min_length=1, max_length=32)
    requested_tool_permissions: list[str] = Field(default_factory=list, max_length=0)


class ReviewVerdict(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"
    HUMAN_REVIEW = "human_review"


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: ReviewVerdict
    claim_citation_ids: list[str] = Field(default_factory=list, max_length=32)
    revision_notes: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def require_auditable_review_targets(self) -> "ReviewDecision":
        if self.verdict in {ReviewVerdict.APPROVE, ReviewVerdict.REVISE} and not self.claim_citation_ids:
            raise ValueError("approve/revise decisions must cite at least one claim citation")
        if self.verdict is ReviewVerdict.REVISE and not self.revision_notes:
            raise ValueError("revise decisions must include targeted notes")
        return self


class ValidationResult(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    workspace_id: UUID
    question: str = Field(min_length=1, max_length=4_000)
    evidence: list[Citation] = Field(default_factory=list, max_length=200)


class FlowState(BaseModel):
    """Auditable state; agents receive copies and cannot mutate request evidence."""

    request: ResearchRequest
    draft: ResearchDraft | None = None
    validation: ValidationResult | None = None
    review: ReviewDecision | None = None
    revision_count: int = 0


class FlowOutcome(BaseModel):
    draft: ResearchDraft | None
    validation: ValidationResult
    review: ReviewDecision | None
    revision_count: int
    verdict: ReviewVerdict
