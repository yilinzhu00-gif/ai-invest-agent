"""Authorized state transitions for development Agent Runs."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from backend.app.domain.agent_runs.models import AgentMemory, AgentRun, AgentRunEvent
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.research_brief import (
    ResearchBriefContent,
    ResearchBriefVersion,
    content_sha256,
)
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.security.principal import Principal

TERMINAL_STATUSES = {
    AgentRunStatus.COMPLETED.value,
    AgentRunStatus.FAILED.value,
    AgentRunStatus.CANCELLED.value,
    AgentRunStatus.REJECTED.value,
}


@dataclass(frozen=True)
class DevelopmentPrincipal:
    """Temporary explicit boundary for local/testing until P3 OIDC/RLS."""

    principal_id: str
    workspace_id: str


RunPrincipal = DevelopmentPrincipal | Principal


class AgentRunNotFoundError(Exception):
    """Hide unauthorized resources behind the same not-found result."""


class AgentRunService:
    def __init__(self, repository: AgentRunRepository) -> None:
        self.repository = repository

    async def create(
        self,
        principal: RunPrincipal,
        question: str,
        symbol: str | None,
        document_id: UUID | None,
        correlation_id: str,
        executor_mode: str = "development_only",
        workflow: str = "research",
        target: str | None = None,
        research_type: str | None = None,
        depth: str = "standard",
        time_range: str = "recent_1y",
        output_format: str = "markdown",
    ) -> AgentRun:
        await self._set_rls_context(principal)
        run = await self.repository.create_run(
            workspace_id=principal.workspace_id,
            principal_id=principal.principal_id,
            question=question,
            target=target,
            research_type=research_type,
            depth=depth,
            time_range=time_range,
            output_format=output_format,
            workflow=workflow,
            symbol=symbol,
            document_id=document_id,
            correlation_id=correlation_id,
            executor_mode=executor_mode,
        )
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    async def get(self, run_id: UUID, principal: RunPrincipal) -> AgentRun:
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id)
        self._authorize(run, principal)
        assert run is not None
        return run

    async def claim(self, run_id: UUID, principal: RunPrincipal) -> AgentRun | None:
        """Atomically move a durable queued run to running for one worker delivery."""
        await self._set_rls_context(principal)
        run = await self.repository.claim_queued_run(run_id)
        if run is None:
            await self.repository.session.rollback()
            return None
        await self.repository.append_event(run, "run.started", {})
        await self.repository.session.commit()
        return run

    async def is_running(self, run_id: UUID, principal: RunPrincipal) -> bool:
        run = await self.get(run_id, principal)
        return run.status == AgentRunStatus.RUNNING.value

    async def schedule_retry(
        self, run_id: UUID, principal: RunPrincipal, *, error_code: str
    ) -> bool:
        """Persist a transient failure before Celery asks the broker to redeliver it."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        if run.status != AgentRunStatus.RUNNING.value:
            await self.repository.session.rollback()
            return False
        run.status = AgentRunStatus.QUEUED.value
        run.attempt_count += 1
        await self.repository.append_event(
            run,
            "run.retry_scheduled",
            {"attempt": run.attempt_count, "error_code": error_code},
        )
        await self.repository.session.commit()
        return True

    async def record_assistant_message(
        self, run_id: UUID, principal: RunPrincipal, content: str
    ) -> None:
        """Persist the produced answer once so a later confirmation can choose memory."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        await self.repository.append_message(run.id, "assistant", content)
        await self.repository.session.commit()

    async def request_confirmation(
        self, run_id: UUID, principal: RunPrincipal, *, verdict: str
    ) -> AgentRun:
        """Pause only a Human Review outcome; no memory is written at this point."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        if run.status in TERMINAL_STATUSES or run.status == AgentRunStatus.AWAITING_CONFIRMATION.value:
            return run
        run.status = AgentRunStatus.AWAITING_CONFIRMATION.value
        await self.repository.append_event(
            run,
            "run.awaiting_confirmation",
            {"verdict": verdict, "actions": ["approve", "reject"]},
        )
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    async def confirm(
        self, run_id: UUID, principal: RunPrincipal, *, approve: bool
    ) -> AgentRun:
        """Resolve the one explicit human gate and optionally persist a memory."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        if run.status != AgentRunStatus.AWAITING_CONFIRMATION.value:
            return run
        if approve:
            message = await self.repository.latest_message(run.id, "assistant")
            if message is not None:
                # Bounded and explicit: the user approves only the final assistant summary,
                # never a hidden prompt, raw evidence, secret, or provider response.
                memory = await self.repository.create_memory(
                    workspace_id=principal.workspace_id,
                    principal_id=principal.principal_id,
                    source_run_id=run.id,
                    content=message.content[:2_000],
                )
                await self.repository.append_event(
                    run, "memory.saved", {"memory_id": str(memory.id), "source": "human_confirmation"}
                )
            run.status = AgentRunStatus.COMPLETED.value
            await self.repository.append_event(run, "run.confirmed", {"decision": "approve"})
        else:
            run.status = AgentRunStatus.REJECTED.value
            await self.repository.append_event(run, "run.rejected", {"decision": "reject"})
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    async def recover(self, run_id: UUID, principal: RunPrincipal) -> AgentRun:
        """A human may requeue a failed run from its durable input and event history."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        if run.status != AgentRunStatus.FAILED.value:
            return run
        run.status = AgentRunStatus.QUEUED.value
        await self.repository.append_event(
            run,
            "run.recovery_queued",
            {"attempt": run.attempt_count, "source": "human_confirmation"},
        )
        await self.repository.session.commit()
        await self.repository.session.refresh(run)
        return run

    async def list_memory(self, principal: RunPrincipal, *, limit: int = 8) -> list[AgentMemory]:
        await self._set_rls_context(principal)
        return await self.repository.list_memories(
            workspace_id=principal.workspace_id, principal_id=principal.principal_id, limit=limit
        )

    async def list_events(
        self, run_id: UUID, principal: RunPrincipal, after_sequence: int
    ) -> list[AgentRunEvent]:
        await self.get(run_id, principal)
        return await self.repository.list_events(run_id, after_sequence)

    async def save_brief_version(
        self, run_id: UUID, principal: RunPrincipal, content: ResearchBriefContent
    ) -> ResearchBriefVersion:
        """Append a researcher-authored immutable content snapshot to the Run audit trail."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        events = await self.repository.list_events(run_id, 0)
        existing = [event for event in events if event.event_type == "research.brief_version_saved"]
        version = len(existing) + 1
        saved = ResearchBriefVersion(
            version=version,
            content=content,
            content_sha256=content_sha256(content),
        )
        await self.repository.append_event(
            run,
            "research.brief_version_saved",
            saved.model_dump(mode="json"),
        )
        await self.repository.session.commit()
        return saved

    async def list_brief_versions(
        self, run_id: UUID, principal: RunPrincipal
    ) -> list[ResearchBriefVersion]:
        await self.get(run_id, principal)
        versions: list[ResearchBriefVersion] = []
        for event in await self.repository.list_events(run_id, 0):
            if event.event_type != "research.brief_version_saved":
                continue
            versions.append(ResearchBriefVersion.model_validate(event.payload))
        return versions

    async def decide_brief_version(
        self, run_id: UUID, principal: RunPrincipal, version: int, decision: str
    ) -> None:
        """Record acceptance/rejection without overwriting the saved content version."""
        await self._set_rls_context(principal)
        run = await self.repository.get_run(run_id, lock=True)
        self._authorize(run, principal)
        assert run is not None
        versions = await self.list_brief_versions(run_id, principal)
        if not any(item.version == version for item in versions):
            raise ValueError("brief_version_not_found")
        await self.repository.append_event(
            run,
            "research.brief_decided",
            {"version": version, "decision": decision},
        )
        await self.repository.session.commit()

    async def transition(
        self,
        run_id: UUID,
        principal: RunPrincipal,
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
        principal: RunPrincipal,
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

    async def cancel(self, run_id: UUID, principal: RunPrincipal) -> AgentRun:
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
    def _authorize(run: AgentRun | None, principal: RunPrincipal) -> None:
        if (
            run is None
            or run.workspace_id != principal.workspace_id
            or run.principal_id != principal.principal_id
        ):
            raise AgentRunNotFoundError

    async def _set_rls_context(self, principal: RunPrincipal) -> None:
        await self.repository.session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": principal.principal_id},
        )
        await self.repository.session.execute(
            text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
            {"workspace_id": principal.workspace_id},
        )
