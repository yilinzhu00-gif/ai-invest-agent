"""Durable Agent Run worker lifecycle, independent of the HTTP process."""

import asyncio
from contextlib import suppress
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.agents.benchmark import BaselineAnalyst, BaselineReviewer
from backend.app.agents.flow import ControlledResearchFlow
from backend.app.agents.runtime import run_with_runtime
from backend.app.agents.schemas import AgentRuntime, Citation, ResearchRequest
from backend.app.core.config import Settings
from backend.app.db.session import create_session_factory
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, DevelopmentPrincipal


class RetryableWorkerError(Exception):
    """A provider or network failure that is explicitly safe for Celery redelivery."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


async def schedule_agent_run_retry(
    *, run_id: str, workspace_id: str, principal_id: str, error_code: str, settings: Settings
) -> bool:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        return await AgentRunService(AgentRunRepository(session)).schedule_retry(
            UUID(run_id),
            DevelopmentPrincipal(principal_id=principal_id, workspace_id=workspace_id),
            error_code=error_code,
        )


async def fail_agent_run(
    *, run_id: str, workspace_id: str, principal_id: str, error_code: str, settings: Settings
) -> None:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        await AgentRunService(AgentRunRepository(session)).transition(
            UUID(run_id),
            DevelopmentPrincipal(principal_id=principal_id, workspace_id=workspace_id),
            AgentRunStatus.FAILED,
            "run.failed",
            {"error_code": error_code},
        )


async def execute_claimed_agent_run(
    *, run_id: str, workspace_id: str, principal_id: str, settings: Settings
) -> str:
    """Claim a queued run, respect cancellation checkpoints, and persist its terminal state."""
    principal = DevelopmentPrincipal(principal_id=principal_id, workspace_id=workspace_id)
    session_factory = create_session_factory(settings)
    parsed_run_id = UUID(run_id)
    try:
        async with asyncio.timeout(settings.agent_run_timeout_seconds):
            async with session_factory() as session:
                service = AgentRunService(AgentRunRepository(session))
                run = await service.claim(parsed_run_id, principal)
                if run is None:
                    return "not_claimed"
                if not await service.is_running(parsed_run_id, principal):
                    return "cancelled"
                await service.append_event(parsed_run_id, principal, "step.started", {"step": 1})
                request = ResearchRequest(
                    run_id=parsed_run_id,
                    workspace_id=uuid5(NAMESPACE_URL, f"worker-workspace:{workspace_id}"),
                    question=run.question,
                    evidence=[
                        Citation(
                            id="worker-run-input",
                            source="celery-worker",
                            locator="run-question",
                            text=run.question,
                        )
                    ],
                )
                outcome = await run_with_runtime(
                    AgentRuntime(settings.agent_runtime),
                    ControlledResearchFlow(BaselineAnalyst(), BaselineReviewer()),
                    request,
                )
                if not await service.is_running(parsed_run_id, principal):
                    return "cancelled"
                await service.append_event(
                    parsed_run_id,
                    principal,
                    "validation.finished",
                    {"passed": outcome.validation.passed, "errors": outcome.validation.errors},
                )
                await service.append_event(
                    parsed_run_id,
                    principal,
                    "text.delta",
                    {"text": outcome.draft.summary if outcome.draft else "worker 未生成草稿。"},
                )
                terminal = await service.transition(
                    parsed_run_id, principal, AgentRunStatus.COMPLETED, "run.completed"
                )
                return terminal.status
    except TimeoutError:
        async with session_factory() as session:
            service = AgentRunService(AgentRunRepository(session))
            with suppress(Exception):
                await service.transition(parsed_run_id, principal, AgentRunStatus.FAILED, "run.failed")
        return "failed"
