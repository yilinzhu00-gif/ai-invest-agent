"""Durable Agent Run worker lifecycle, independent of the HTTP process."""

import asyncio
from uuid import NAMESPACE_URL, UUID, uuid5

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
from backend.app.db.session import create_session_factory
from backend.app.domain.agent_runs.flow_observer import PersistedFlowObserver
from backend.app.domain.agent_runs.market_research import (
    market_result_payload,
    market_snapshot_citation,
)
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, DevelopmentPrincipal
from backend.app.tools.market_snapshot import MarketSnapshotUnavailableError, fetch_market_snapshot


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
        service = AgentRunService(AgentRunRepository(session))
        principal = DevelopmentPrincipal(principal_id=principal_id, workspace_id=workspace_id)
        await service.transition(
            UUID(run_id),
            principal,
            AgentRunStatus.FAILED,
            "run.failed",
            {"error_code": error_code, "recoverable": True},
        )
        await service.append_event(
            UUID(run_id),
            principal,
            "run.recovery_required",
            {"action": "recover"},
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
                memories = await service.list_memory(principal)
                snapshot = await fetch_market_snapshot(run.symbol) if run.symbol else None
                evidence = (
                    [market_snapshot_citation(snapshot)]
                    if snapshot is not None
                    else [
                        Citation(
                            id="worker-run-input",
                            source="celery-worker",
                            locator="run-question",
                            text=run.question,
                        )
                    ]
                )
                request = ResearchRequest(
                    run_id=parsed_run_id,
                    workspace_id=uuid5(NAMESPACE_URL, f"worker-workspace:{workspace_id}"),
                    question=run.question,
                    evidence=evidence,
                    memory=[ResearchMemory(id=memory.id, content=memory.content) for memory in memories],
                )
                outcome = await run_with_runtime(
                    AgentRuntime(settings.agent_runtime),
                    build_research_flow(
                        settings,
                        observer=PersistedFlowObserver(service, parsed_run_id, principal),
                    ),
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
                summary = outcome.draft.summary if outcome.draft else "worker 未生成草稿。"
                if snapshot is not None:
                    await service.append_event(
                        parsed_run_id,
                        principal,
                        "research.result",
                        market_result_payload(snapshot, summary),
                    )
                await service.record_assistant_message(parsed_run_id, principal, summary)
                if outcome.verdict is ReviewVerdict.HUMAN_REVIEW:
                    await service.append_event(
                        parsed_run_id, principal, "review.required", {"verdict": outcome.verdict.value}
                    )
                    awaiting = await service.request_confirmation(
                        parsed_run_id, principal, verdict=outcome.verdict.value
                    )
                    return awaiting.status
                terminal = await service.transition(
                    parsed_run_id,
                    principal,
                    AgentRunStatus.COMPLETED,
                    "run.completed",
                    {"verdict": outcome.verdict.value, "revision_count": outcome.revision_count},
                )
                return terminal.status
    except MarketSnapshotUnavailableError as error:
        raise RetryableWorkerError(str(error)) from error
    except TimeoutError as error:
        # The task entrypoint persists the retry transition before broker redelivery.
        raise RetryableWorkerError("run_timeout") from error
