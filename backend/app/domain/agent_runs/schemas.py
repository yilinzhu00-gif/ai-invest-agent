from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.domain.agent_runs.models import AgentRun, AgentRunEvent


class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ConfirmationDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class CreateAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    symbol: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class ConfirmAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ConfirmationDecision


class AgentRunResponse(BaseModel):
    id: UUID
    status: AgentRunStatus
    executor_mode: str
    symbol: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_model(cls, run: AgentRun) -> "AgentRunResponse":
        return cls(
            id=run.id,
            status=AgentRunStatus(run.status),
            executor_mode=run.executor_mode,
            symbol=getattr(run, "symbol", None),
            created_at=run.created_at,
        )


class AgentRunEventResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, object]

    @classmethod
    def from_model(cls, event: AgentRunEvent) -> "AgentRunEventResponse":
        return cls(sequence=event.sequence, event_type=event.event_type, payload=event.payload)
