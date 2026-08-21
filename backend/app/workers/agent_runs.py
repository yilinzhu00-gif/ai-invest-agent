"""Durable Agent Run worker lifecycle, independent of the HTTP process."""

import asyncio
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.agent.events import AgentEventType
from backend.app.agents.factory import build_research_flow
from backend.app.agents.report_agent import ReportAgent
from backend.app.agents.runtime import run_with_runtime
from backend.app.agents.schemas import (
    AgentRuntime,
    Citation,
    ResearchRequest,
    ReviewVerdict,
)
from backend.app.core.config import Settings
from backend.app.db.session import create_session_factory
from backend.app.domain.agent_runs.document_research import (
    document_evidence,
    document_result_payload,
    insufficient_evidence_payload,
)
from backend.app.domain.agent_runs.flow_observer import (
    PersistedFlowObserver,
    persisted_event_emitter,
)
from backend.app.domain.agent_runs.institutional_report import ReportGenerationError
from backend.app.domain.agent_runs.market_debate import (
    MarketDebateRunError,
    execute_market_debate_run,
)
from backend.app.domain.agent_runs.market_research import (
    market_result_payload,
    market_snapshot_citation,
)
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, DevelopmentPrincipal
from backend.app.domain.knowledge.repository import DocumentRepository
from backend.app.domain.knowledge.service import KnowledgeService
from backend.app.ingestion.parser import DocumentParser
from backend.app.memory.context import load_memory_context, save_research_memory
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
                memory_context = await load_memory_context(session, principal, symbol=run.symbol)
                legacy_memories = await service.list_memory(principal)
                plan = memory_context.plan(run.question, run.symbol)
                trace = persisted_event_emitter(service, parsed_run_id, principal)
                await trace.emit(
                    AgentEventType.PLANNING_START,
                    "Planner Agent started",
                    run_id=parsed_run_id,
                    metadata={
                        "question_length": len(run.question),
                        "workflow": run.workflow,
                        "steps": list(plan.steps),
                        "memory_used": list(plan.memory_used),
                    },
                )
                await service.append_event(parsed_run_id, principal, "step.started", {"step": 1})
                if run.workflow == "market_debate":
                    return await execute_market_debate_run(
                        run_id=parsed_run_id,
                        principal=principal,
                        run=run,
                        service=service,
                        settings=settings,
                    )
                document_items = []
                snapshot = None
                document_id = run.document_id
                if document_id is not None:
                    await trace.emit(
                        AgentEventType.TOOL_CALL_START,
                        "Evidence search started",
                        run_id=parsed_run_id,
                        metadata={"tool": "knowledge_search"},
                    )
                    results = await KnowledgeService(
                        DocumentRepository(session), DocumentParser()
                    ).search(
                        principal=principal,
                        query=run.question,
                        document_id=document_id,
                        limit=10,
                    )
                    await trace.emit(
                        AgentEventType.TOOL_CALL_END,
                        "Evidence search completed",
                        run_id=parsed_run_id,
                        metadata={"tool": "knowledge_search", "result_count": len(results)},
                    )
                    document_items = document_evidence(results)
                    if not document_items:
                        payload = insufficient_evidence_payload(document_id)
                        await service.append_event(
                            parsed_run_id, principal, "research.evidence_result", payload
                        )
                        await service.record_assistant_message(
                            parsed_run_id, principal, str(payload["summary"])
                        )
                        terminal = await service.transition(
                            parsed_run_id,
                            principal,
                            AgentRunStatus.REJECTED,
                            "run.rejected",
                            {"reason": "key_announcement_evidence_missing", "revision_count": 0},
                        )
                        return terminal.status
                    evidence = [item.citation for item in document_items]
                else:
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
                    memory=memory_context.as_agent_memories(legacy_memories),
                    require_structured_conclusion=document_id is not None,
                )
                outcome = await run_with_runtime(
                    AgentRuntime(settings.agent_runtime),
                    build_research_flow(
                        settings,
                        observer=PersistedFlowObserver(service, parsed_run_id, principal),
                    ),
                    request,
                )
                await trace.emit(
                    AgentEventType.REPORT_GENERATE_START,
                    "Report generation started",
                    run_id=parsed_run_id,
                    metadata={"claim_count": len(outcome.draft.claims) if outcome.draft else 0},
                )
                report_content: str | None = None
                if outcome.validation.passed and outcome.draft is not None:
                    try:
                        report = ReportAgent().generate(
                            target=run.target or run.symbol or "Research Target",
                            draft=outcome.draft,
                            evidence=evidence,
                        )
                    except ReportGenerationError as error:
                        await service.append_event(
                            parsed_run_id,
                            principal,
                            "research.report_unavailable",
                            {"reason": str(error)},
                        )
                    else:
                        report_content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
                        await service.append_event(
                            parsed_run_id,
                            principal,
                            "research.report",
                            report.model_dump(mode="json"),
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
                if document_items and outcome.validation.passed and outcome.draft is not None:
                    await service.append_event(
                        parsed_run_id,
                        principal,
                        "research.evidence_result",
                        document_result_payload(
                            summary=summary,
                            claims=outcome.draft.claims,
                            evidence=document_items,
                            conclusion=outcome.draft.conclusion,
                            status=(
                                "supported"
                                if outcome.verdict is ReviewVerdict.APPROVE
                                else "human_review"
                            ),
                        ),
                    )
                elif document_items:
                    assert document_id is not None
                    summary = "证据不足：草稿未通过引用校验，未生成结论。"
                    await service.append_event(
                        parsed_run_id,
                        principal,
                        "research.evidence_result",
                        insufficient_evidence_payload(document_id, summary=summary),
                    )
                elif snapshot is not None:
                    await service.append_event(
                        parsed_run_id,
                        principal,
                        "research.result",
                        market_result_payload(snapshot, summary),
                    )
                await save_research_memory(
                    session,
                    principal,
                    run_id=parsed_run_id,
                    title=f"{run.target or run.symbol or 'Research'} research task",
                    summary=report_content or summary,
                    symbol=run.symbol,
                    research_type=run.research_type,
                    confidence=1.0 if outcome.verdict is ReviewVerdict.APPROVE else 0.5,
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
                if outcome.verdict is ReviewVerdict.REJECT:
                    rejected = await service.transition(
                        parsed_run_id,
                        principal,
                        AgentRunStatus.REJECTED,
                        "run.rejected",
                        {"reason": "research_conclusion_invalid", "revision_count": outcome.revision_count},
                    )
                    return rejected.status
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
    except MarketDebateRunError as error:
        await fail_agent_run(
            run_id=run_id,
            workspace_id=workspace_id,
            principal_id=principal_id,
            error_code=str(error),
            settings=settings,
        )
        return "failed"
    except TimeoutError as error:
        # The task entrypoint persists the retry transition before broker redelivery.
        raise RetryableWorkerError("run_timeout") from error
