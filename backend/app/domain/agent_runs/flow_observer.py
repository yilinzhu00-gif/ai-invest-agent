"""Persist minimal, replayable role-stage events for an Agent Run."""

from dataclasses import dataclass
from uuid import UUID

from backend.app.agent.events import AgentEvent, AgentEventEmitter, AgentEventType
from backend.app.domain.agent_runs.service import AgentRunService, RunPrincipal


@dataclass
class PersistedFlowObserver:
    service: AgentRunService
    run_id: UUID
    principal: RunPrincipal

    def __post_init__(self) -> None:
        self.emitter = AgentEventEmitter(self._persist_typed_event)

    async def _persist_typed_event(self, event: AgentEvent) -> None:
        # Keep the existing role events for backwards-compatible consumers and
        # add one normalized trace envelope for the product UI.
        await self.service.append_event(
            self.run_id,
            self.principal,
            "agent.trace",
            event.as_payload(),
        )

    async def on_stage(self, role: str, status: str, payload: dict[str, object]) -> None:
        # The stage contract is intentionally metadata-only. Evidence/draft text is
        # delivered as the existing final text event and never duplicated into logs.
        await self.service.append_event(
            self.run_id,
            self.principal,
            f"agent.{role}.{status}",
            payload,
        )
        if status == "started":
            event_type = (
                AgentEventType.REFLECTION_START
                if role in {"numeric_validator", "reviewer"}
                else AgentEventType.AGENT_START
            )
            message = {
                "analyst": "Financial Agent started",
                "numeric_validator": "Reflection checking result",
                "reviewer": "Reflection reviewer started",
            }.get(role, f"{role} started")
            await self.emitter.emit(
                event_type,
                message,
                run_id=self.run_id,
                metadata={"role": role, **payload},
            )
        elif status in {"completed", "skipped"}:
            await self.emitter.emit(
                AgentEventType.AGENT_END,
                f"{role} {status}",
                run_id=self.run_id,
                metadata={"role": role, **payload},
            )


def persisted_event_emitter(
    service: AgentRunService, run_id: UUID, principal: RunPrincipal
) -> AgentEventEmitter:
    """Build the same normalized trace sink for executor-level lifecycle events."""

    async def persist(event: AgentEvent) -> None:
        await service.append_event(run_id, principal, "agent.trace", event.as_payload())

    return AgentEventEmitter(persist)
