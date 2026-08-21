from datetime import date, datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.domain.agent_runs.models import AgentRun, AgentRunEvent


class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class AgentRunWorkflow(str, Enum):
    RESEARCH = "research"
    MARKET_DEBATE = "market_debate"


class ConfirmationDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ResearchTarget(str, Enum):
    NVDA = "NVDA"
    AAPL = "AAPL"
    TSMC = "TSMC"


class ResearchType(str, Enum):
    INVESTMENT_VALUE = "investment_value"
    FINANCIAL = "financial"
    INDUSTRY = "industry"
    COMPETITIVE = "competitive"
    RISK = "risk"


class ResearchDepth(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP_RESEARCH = "deep_research"


class ResearchTimeRange(str, Enum):
    RECENT_1Y = "recent_1y"
    RECENT_3Y = "recent_3y"
    CUSTOM = "custom"


class ResearchOutputFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    PPT = "ppt"


class ResearchTaskSchema(BaseModel):
    """Validated configuration for a professional research task."""

    model_config = ConfigDict(extra="forbid")

    target: ResearchTarget
    research_type: ResearchType
    depth: ResearchDepth = ResearchDepth.STANDARD
    time_range: ResearchTimeRange = ResearchTimeRange.RECENT_1Y
    output_format: ResearchOutputFormat = ResearchOutputFormat.MARKDOWN
    custom_start: date | None = None
    custom_end: date | None = None

    @model_validator(mode="after")
    def validate_custom_range(self) -> "ResearchTaskSchema":
        if self.time_range is ResearchTimeRange.CUSTOM:
            if self.custom_start is None or self.custom_end is None:
                raise ValueError("custom time_range requires custom_start and custom_end")
            if self.custom_start > self.custom_end:
                raise ValueError("custom_start must not be after custom_end")
        elif self.custom_start is not None or self.custom_end is not None:
            raise ValueError("custom dates are only valid with time_range=custom")
        return self

    def persisted_time_range(self) -> str:
        if self.time_range is not ResearchTimeRange.CUSTOM:
            return self.time_range.value
        assert self.custom_start is not None and self.custom_end is not None
        return f"custom:{self.custom_start.isoformat()}..{self.custom_end.isoformat()}"

    def question(self) -> str:
        return (
            f"请完成{self.research_type.value}研究：{self.target.value}；"
            f"时间范围={self.persisted_time_range()}；研究深度={self.depth.value}。"
        )


# Short import name for API consumers.
ResearchTask = ResearchTaskSchema


class CreateAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    workflow: AgentRunWorkflow = AgentRunWorkflow.RESEARCH
    symbol: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    document_id: UUID | None = None

    @model_validator(mode="after")
    def validate_workflow_inputs(self) -> "CreateAgentRunRequest":
        if self.workflow is AgentRunWorkflow.MARKET_DEBATE and self.symbol is None:
            raise ValueError("market_debate requires symbol")
        if self.workflow is AgentRunWorkflow.MARKET_DEBATE and self.document_id is not None:
            raise ValueError("market_debate does not accept document_id")
        return self


class ConfirmAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ConfirmationDecision


class AgentRunResponse(BaseModel):
    id: UUID
    status: AgentRunStatus
    executor_mode: str
    workflow: AgentRunWorkflow = AgentRunWorkflow.RESEARCH
    symbol: str | None = None
    document_id: UUID | None = None
    target: str | None = None
    research_type: str | None = None
    depth: str = "standard"
    time_range: str = "recent_1y"
    output_format: str = "markdown"
    created_at: datetime | None = None

    @classmethod
    def from_model(cls, run: AgentRun) -> "AgentRunResponse":
        return cls(
            id=run.id,
            status=AgentRunStatus(run.status),
            executor_mode=run.executor_mode,
            workflow=AgentRunWorkflow(getattr(run, "workflow", AgentRunWorkflow.RESEARCH.value)),
            symbol=getattr(run, "symbol", None),
            document_id=getattr(run, "document_id", None),
            target=getattr(run, "target", None),
            research_type=getattr(run, "research_type", None),
            depth=getattr(run, "depth", "standard"),
            time_range=getattr(run, "time_range", "recent_1y"),
            output_format=getattr(run, "output_format", "markdown"),
            created_at=run.created_at,
        )


class AgentRunEventResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, object]

    @classmethod
    def from_model(cls, event: AgentRunEvent) -> "AgentRunEventResponse":
        return cls(sequence=event.sequence, event_type=event.event_type, payload=event.payload)
