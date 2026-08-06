"""Authorized state transitions for development Agent Runs."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from backend.app.domain.agent_runs.models import AgentRun, AgentRunEvent
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import AgentRunStatus

TERMINAL_STATUSES = {
    AgentRunStatus.COMPLETED.value,
    AgentRunStatus.FAILED.value,
    AgentRunStatus.CANCELLED.value,
}


@dataclass(frozen=True)
class DevelopmentPrincipal:
    """Temporary explicit boundary for local/testing until P3 OIDC/RLS."""

    principal_id: str
    workspace_id: str


class AgentRunNotFoundError(Exception):
    """Hide unauthorized resources behind the same not-found result."""


class AgentRunService:
    def __init__(self, repository: AgentRunRepository) -> None:
        self.repository = repository

    async def create(
        self, principal: DevelopmentPrincipal, question: str, correlation_id: str
    ) -> AgentRun:
        await self._set_rls_context(principal)
        run = await self.repository.create_run(
            workspace_id=principal.workspace_id,
            principal_id=principal.principal_id,
            question=question,
            correlation_id=correlation_id,
        )
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    async def get(self, run_id: UUID, principal: DevelopmentPrincipal) -> AgentRun:
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id)
        self._authorize(run, principal)
        assert run is not None
        return run

    async def list_events(
        self, run_id: UUID, principal: DevelopmentPrincipal, after_sequence: int
    ) -> list[AgentRunEvent]:
        await self.get(run_id, principal)
        return await self.repository.list_events(run_id, after_sequence)

    async def transition(
        self,
        run_id: UUID,
        principal: DevelopmentPrincipal,
        status: AgentRunStatus,
        event_type: str,
        payload: dict[str, object] | None = None,
    ) -> AgentRun:
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        if run.status in TERMINAL_STATUSES:
            return run
        run.status = status.value
        await self.repository.append_event(run, event_type, payload or {})
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    async def append_event(
        self,
        run_id: UUID,
        principal: DevelopmentPrincipal,
        event_type: str,
        payload: dict[str, object],
    ) -> AgentRunEvent:
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        event = await self.repository.append_event(run, event_type, payload)
        await self.repository.session.commit()
        return event

    async def cancel(self, run_id: UUID, principal: DevelopmentPrincipal) -> AgentRun:
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        if run.status in TERMINAL_STATUSES:
            return run
        run.status = AgentRunStatus.CANCELLED.value
        await self.repository.append_event(run, "run.cancelled", {})
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    @staticmethod
    def _authorize(run: AgentRun | None, principal: DevelopmentPrincipal) -> None:
        if (
            run is None
            or run.workspace_id != principal.workspace_id
            or run.principal_id != principal.principal_id
        ):
            raise AgentRunNotFoundError

    async def _set_rls_context(self, principal: DevelopmentPrincipal) -> None:
        await self.repository.session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": principal.principal_id},
        )
        await self.repository.session.execute(
            text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
            {"workspace_id": principal.workspace_id},
        )
