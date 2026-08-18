"""Explicitly non-production in-process executor for P2 development only."""

import asyncio
from contextlib import suppress
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.agents.factory import build_research_flow
from backend.app.agents.runtime import run_with_runtime
from backend.app.agents.schemas import (
    AgentRuntime,
    Citation,
    ResearchMemory,
    ResearchRequest,
    ReviewVerdict,
)
from backend.app.core.config import Settings
from backend.app.domain.agent_runs.flow_observer import PersistedFlowObserver
from backend.app.domain.agent_runs.market_research import (
    market_result_payload,
    market_snapshot_citation,
)
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, RunPrincipal
from backend.app.tools.market_snapshot import MarketSnapshotUnavailableError, fetch_market_snapshot


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
                    memories = await service.list_memory(principal)
                    snapshot = await fetch_market_snapshot(run.symbol) if run.symbol else None
                    evidence = (
                        [market_snapshot_citation(snapshot)]
                        if snapshot is not None
                        else [
                            Citation(
                                id="development-run-input",
                                source="development-executor",
                                locator="run-question",
                                text=run.question,
                            )
                        ]
                    )
                    request = ResearchRequest(
                        run_id=run_id,
                        workspace_id=uuid5(NAMESPACE_URL, f"development-workspace:{principal.workspace_id}"),
                        question=run.question,
                        evidence=evidence,
                        memory=[ResearchMemory(id=memory.id, content=memory.content) for memory in memories],
                    )
                    outcome = await run_with_runtime(
                        AgentRuntime(self.settings.agent_runtime),
                        build_research_flow(
                            self.settings,
                            observer=PersistedFlowObserver(service, run_id, principal),
                        ),
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
                    summary = outcome.draft.summary if outcome.draft else "开发执行器未生成草稿。"
                    if snapshot is not None:
                        await service.append_event(
                            run_id, principal, "research.result", market_result_payload(snapshot, summary)
                        )
                    await service.record_assistant_message(run_id, principal, summary)
                    if outcome.verdict is ReviewVerdict.HUMAN_REVIEW:
                        await service.append_event(
                            run_id, principal, "review.required", {"verdict": outcome.verdict.value}
                        )
                        await service.request_confirmation(
                            run_id, principal, verdict=outcome.verdict.value
                        )
                    else:
                        await service.transition(
                            run_id,
                            principal,
                            AgentRunStatus.COMPLETED,
                            "run.completed",
                            {
                                "verdict": outcome.verdict.value,
                                "revision_count": outcome.revision_count,
                            },
                        )
        except MarketSnapshotUnavailableError as error:
            async with self.session_factory() as session:
                service = AgentRunService(AgentRunRepository(session))
                with suppress(Exception):
                    await service.transition(
                        run_id,
                        principal,
                        AgentRunStatus.FAILED,
                        "run.failed",
                        {"error_code": str(error), "recoverable": True},
                    )
                    await service.append_event(
                        run_id, principal, "run.recovery_required", {"action": "recover"}
                    )
        except TimeoutError:
            async with self.session_factory() as session:
                service = AgentRunService(AgentRunRepository(session))
                with suppress(Exception):
                    await service.transition(
                        run_id,
                        principal,
                        AgentRunStatus.FAILED,
                        "run.failed",
                        {"error_code": "run_timeout", "recoverable": True},
                    )
                    await service.append_event(
                        run_id, principal, "run.recovery_required", {"action": "recover"}
                    )

    async def wait_before_first_step(self) -> None:
        """Yield at a cancellation/deadline boundary before the first development step."""
        await asyncio.sleep(0)
