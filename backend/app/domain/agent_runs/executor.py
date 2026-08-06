"""Explicitly non-production in-process executor for P2 development only."""

import asyncio
from contextlib import suppress
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.agents.benchmark import BaselineAnalyst, BaselineReviewer
from backend.app.agents.flow import ControlledResearchFlow
from backend.app.agents.runtime import run_with_runtime
from backend.app.agents.schemas import AgentRuntime, Citation, ResearchRequest
from backend.app.core.config import Settings
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, RunPrincipal


class DevelopmentRunExecutor:
    """Run a deterministic development sequence; P3 replaces this with a worker."""

    development_only = True

    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.tasks: set[asyncio.Task[None]] = set()

    def submit(self, run_id: UUID, principal: RunPrincipal) -> None:
        task = asyncio.create_task(self._execute(run_id, principal))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _execute(self, run_id: UUID, principal: RunPrincipal) -> None:
        try:
            async with asyncio.timeout(self.settings.agent_run_timeout_seconds):
                async with self.session_factory() as session:
                    service = AgentRunService(AgentRunRepository(session))
                    run = await service.transition(
                        run_id, principal, AgentRunStatus.RUNNING, "run.started"
                    )
                    if run.status == AgentRunStatus.CANCELLED.value:
                        return
                    await self.wait_before_first_step()
                    await service.append_event(run_id, principal, "step.started", {"step": 1})
                    request = ResearchRequest(
                        run_id=run_id,
                        workspace_id=uuid5(NAMESPACE_URL, f"development-workspace:{principal.workspace_id}"),
                        question=run.question,
                        evidence=[
                            Citation(
                                id="development-run-input",
                                source="development-executor",
                                locator="run-question",
                                text=run.question,
                            )
                        ],
                    )
                    outcome = await run_with_runtime(
                        AgentRuntime(self.settings.agent_runtime),
                        ControlledResearchFlow(BaselineAnalyst(), BaselineReviewer()),
                        request,
                    )
                    await service.append_event(
                        run_id,
                        principal,
                        "validation.finished",
                        {"passed": outcome.validation.passed, "errors": outcome.validation.errors},
                    )
                    await service.append_event(
                        run_id,
                        principal,
                        "text.delta",
                        {"text": outcome.draft.summary if outcome.draft else "开发执行器未生成草稿。"},
                    )
                    await service.append_event(
                        run_id, principal, "review.required", {"verdict": outcome.verdict.value}
                    )
                    await service.transition(
                        run_id, principal, AgentRunStatus.COMPLETED, "run.completed"
                    )
        except TimeoutError:
            async with self.session_factory() as session:
                service = AgentRunService(AgentRunRepository(session))
                with suppress(Exception):
                    await service.transition(run_id, principal, AgentRunStatus.FAILED, "run.failed")

    async def wait_before_first_step(self) -> None:
        """Yield at a cancellation/deadline boundary before the first development step."""
        await asyncio.sleep(0)
