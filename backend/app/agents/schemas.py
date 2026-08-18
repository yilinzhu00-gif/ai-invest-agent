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


class ResearchMemory(BaseModel):
    """Human-approved, workspace-scoped context from an earlier research run.

    Memories are deliberately not citations.  They can help retain a user's
    stated research context, but cannot support a factual claim in a draft.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    content: str = Field(min_length=1, max_length=2_000)


class ResearchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10_000)
    citation_ids: list[str] = Field(min_length=1, max_length=8)
    numeric_values: list[float] = Field(default_factory=list, max_length=32)
    calculations: list["NumericCalculation"] = Field(default_factory=list, max_length=16)

    @field_validator("numeric_values")
    @classmethod
    def require_finite_numbers(cls, values: list[float]) -> list[float]:
        if not all(isfinite(value) for value in values):
            raise ValueError("numeric values must be finite")
        return values


class CalculationOperator(str, Enum):
    SUM = "sum"
    DIFFERENCE = "difference"
    RATIO = "ratio"
    PERCENT_CHANGE = "percent_change"


class NumericCalculation(BaseModel):
    """A recomputable numeric assertion made by the Analyst.

    Operands must come from the cited excerpts.  The independent numeric
    validator recomputes ``result``; a model is never trusted to do arithmetic.
    """

    model_config = ConfigDict(extra="forbid")

    operator: CalculationOperator
    operands: list[float] = Field(
        min_length=2,
        max_length=8,
        description=(
            "sum uses all operands; difference and ratio use first minus/divided by second; "
            "percent_change uses [starting_value, ending_value]."
        ),
    )
    result: float

    @field_validator("operands")
    @classmethod
    def require_finite_operands(cls, values: list[float]) -> list[float]:
        if not all(isfinite(value) for value in values):
            raise ValueError("calculation operands must be finite")
        return values

    @field_validator("result")
    @classmethod
    def require_finite_result(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("calculation result must be finite")
        return value


class ConclusionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResearchConclusion(BaseModel):
    """The fixed, evidence-first output contract for announcement research."""

    model_config = ConfigDict(extra="forbid")

    confirmed_transaction_facts: list[ResearchClaim] = Field(default_factory=list, max_length=6)
    post_announcement_market_reaction: list[ResearchClaim] = Field(default_factory=list, max_length=6)
    possible_impact_mechanisms: list[ResearchClaim] = Field(default_factory=list, max_length=6)
    positive_factors: list[ResearchClaim] = Field(default_factory=list, max_length=6)
    risks_and_uncertainties: list[ResearchClaim] = Field(default_factory=list, max_length=6)
    missing_information: list[str] = Field(default_factory=list, max_length=16)
    confidence: ConclusionConfidence
    confidence_rationale: str = Field(min_length=1, max_length=2_000)
    # The Analyst must explicitly name the announcement blocks on which the
    # conclusion depends.  Losing one invalidates the conclusion rather than
    # silently substituting a different excerpt.
    required_evidence_ids: list[str] = Field(min_length=1, max_length=32)

    def claims_in_display_order(self) -> list[ResearchClaim]:
        return [
            *self.confirmed_transaction_facts,
            *self.post_announcement_market_reaction,
            *self.possible_impact_mechanisms,
            *self.positive_factors,
            *self.risks_and_uncertainties,
        ]


class ResearchDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=10_000)
    claims: list[ResearchClaim] = Field(min_length=1, max_length=32)
    conclusion: ResearchConclusion | None = None
    requested_tool_permissions: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def conclusion_claims_must_match_flat_claims(self) -> "ResearchDraft":
        if self.conclusion is not None and self.claims != self.conclusion.claims_in_display_order():
            raise ValueError("claims must exactly match the conclusion sections in display order")
        return self


class ReviewVerdict(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"
    HUMAN_REVIEW = "human_review"


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: ReviewVerdict
    claim_citation_ids: list[str] = Field(default_factory=list, max_length=32)
    claim_reviews: list["ClaimCitationReview"] = Field(default_factory=list, max_length=32)
    revision_notes: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def require_auditable_review_targets(self) -> "ReviewDecision":
        if self.verdict in {ReviewVerdict.APPROVE, ReviewVerdict.REVISE} and not self.claim_citation_ids:
            raise ValueError("approve/revise decisions must cite at least one claim citation")
        if self.verdict is ReviewVerdict.REVISE and not self.revision_notes:
            raise ValueError("revise decisions must include targeted notes")
        return self


class ClaimCitationReview(BaseModel):
    """Reviewer check for one concrete claim--citation pair."""

    model_config = ConfigDict(extra="forbid")

    claim_index: int = Field(ge=0)
    citation_id: str = Field(min_length=1, max_length=128)
    supported: bool


class ValidationResult(BaseModel):
    passed: bool
    errors: list[str] = Field(default_factory=list)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    workspace_id: UUID
    question: str = Field(min_length=1, max_length=4_000)
    evidence: list[Citation] = Field(default_factory=list, max_length=200)
    memory: list[ResearchMemory] = Field(default_factory=list, max_length=8)
    require_structured_conclusion: bool = False


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
