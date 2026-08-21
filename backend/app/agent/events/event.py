"""The stable event contract for observable Agent execution.

Events deliberately contain stage metadata and user-safe messages only. They are
not a chain-of-thought transport and must not be used to persist prompts or raw
provider responses.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class AgentEventType(StrEnum):
    PLANNING_START = "PLANNING_START"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_END = "TOOL_CALL_END"
    AGENT_START = "AGENT_START"
    AGENT_END = "AGENT_END"
    REFLECTION_START = "REFLECTION_START"
    REPORT_GENERATE_START = "REPORT_GENERATE_START"


# Convenient module-level names for node code and integrations that do not
# need to import the enum class explicitly.
PLANNING_START = AgentEventType.PLANNING_START
TOOL_CALL_START = AgentEventType.TOOL_CALL_START
TOOL_CALL_END = AgentEventType.TOOL_CALL_END
AGENT_START = AgentEventType.AGENT_START
AGENT_END = AgentEventType.AGENT_END
REFLECTION_START = AgentEventType.REFLECTION_START
REPORT_GENERATE_START = AgentEventType.REPORT_GENERATE_START


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """A transport-neutral event that can be persisted or streamed as SSE."""

    event_type: AgentEventType
    message: str
    run_id: UUID | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_payload(self) -> dict[str, object]:
        return {
            "type": self.event_type.value,
            "message": self.message,
            "run_id": str(self.run_id) if self.run_id else None,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }
