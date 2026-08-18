"""Persist minimal, replayable role-stage events for an Agent Run."""

from dataclasses import dataclass
from uuid import UUID

from backend.app.domain.agent_runs.service import AgentRunService, RunPrincipal


@dataclass
class PersistedFlowObserver:
    service: AgentRunService
    run_id: UUID
    principal: RunPrincipal

    async def on_stage(self, role: str, status: str, payload: dict[str, object]) -> None:
        # The stage contract is intentionally metadata-only. Evidence/draft text is
        # delivered as the existing final text event and never duplicated into logs.
        await self.service.append_event(
            self.run_id,
            self.principal,
            f"agent.{role}.{status}",
            payload,
        )
