"""Explicitly non-production in-process executor for P2 development only."""

import asyncio
import json
from contextlib import suppress
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

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
from backend.app.domain.agent_runs.service import AgentRunService, RunPrincipal
from backend.app.domain.knowledge.repository import DocumentRepository
from backend.app.domain.knowledge.service import KnowledgeService
from backend.app.ingestion.parser import DocumentParser
from backend.app.memory.context import load_memory_context, save_research_memory
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
                    memory_context = await load_memory_context(session, principal, symbol=run.symbol)
                    legacy_memories = await service.list_memory(principal)
                    plan = memory_context.plan(run.question, run.symbol)
                    trace = persisted_event_emitter(service, run_id, principal)
                    await trace.emit(
                        AgentEventType.PLANNING_START,
                        "Planner Agent started",
                        run_id=run_id,
                        metadata={
                            "question_length": len(run.question),
                            "workflow": run.workflow,
                            "steps": list(plan.steps),
                            "memory_used": list(plan.memory_used),
                        },
                    )
                    await self.wait_before_first_step()
                    await service.append_event(run_id, principal, "step.started", {"step": 1})
                    if run.workflow == "market_debate":
                        await execute_market_debate_run(
                            run_id=run_id,
                            principal=principal,
                            run=run,
                            service=service,
                            settings=self.settings,
                        )
                        return
                    document_items = []
                    snapshot = None
                    document_id = run.document_id
                    try:
                        await trace.emit(
                            AgentEventType.TOOL_CALL_START,
                            "Evidence search started",
                            run_id=run_id,
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
                            run_id=run_id,
                            metadata={"tool": "knowledge_search", "result_count": len(results)},
                        )
                    except SQLAlchemyError:
                        if document_id is not None:
                            raise
                        # A free-form research question may still use the
                        # existing market-data path when the optional evidence
                        # library is unavailable in local development.
                        results = []
                    document_items = document_evidence(results)
                    if document_id is not None:
                        if not document_items:
                            payload = insufficient_evidence_payload(document_id)
                            await service.append_event(
                                run_id, principal, "research.evidence_result", payload
                            )
                            await service.record_assistant_message(
                                run_id, principal, str(payload["summary"])
                            )
                            await service.transition(
                                run_id,
                                principal,
                                AgentRunStatus.REJECTED,
                                "run.rejected",
                                {"reason": "key_announcement_evidence_missing", "revision_count": 0},
                            )
                            return
                        evidence = [item.citation for item in document_items]
                    elif document_items:
                        # A research Run without a pinned document can still use
                        # the workspace evidence library.  This is the Agent's
                        # document-research path for questions such as "护城河";
                        # the repository applies workspace scoping before the
                        # excerpts become model citations.
                        evidence = [item.citation for item in document_items]
                    else:
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
                        memory=memory_context.as_agent_memories(legacy_memories),
                        require_structured_conclusion=bool(document_items),
                    )
                    outcome = await run_with_runtime(
                        AgentRuntime(self.settings.agent_runtime),
                        build_research_flow(
                            self.settings,
                            observer=PersistedFlowObserver(service, run_id, principal),
                        ),
                        request,
                    )
                    await trace.emit(
                        AgentEventType.REPORT_GENERATE_START,
                        "Report generation started",
                        run_id=run_id,
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
                                run_id,
                                principal,
                                "research.report_unavailable",
                                {"reason": str(error)},
                            )
                        else:
                            report_content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
                            await service.append_event(
                                run_id,
                                principal,
                                "research.report",
                                report.model_dump(mode="json"),
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
                    if document_items and outcome.validation.passed and outcome.draft is not None:
                        await service.append_event(
                            run_id,
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
                        summary = "证据不足：草稿未通过引用校验，未生成结论。"
                        if document_id is not None:
                            payload = insufficient_evidence_payload(document_id, summary=summary)
                        else:
                            payload = {
                                "status": "insufficient_evidence",
                                "summary": summary,
                                "claims": [],
                                "conclusion": None,
                                "boundary": "工作区材料未通过引用校验，未以行情或模型记忆替代文档证据。",
                            }
                        await service.append_event(run_id, principal, "research.evidence_result", payload)
                    elif snapshot is not None:
                        await service.append_event(
                            run_id, principal, "research.result", market_result_payload(snapshot, summary)
                        )
                    await save_research_memory(
                        session,
                        principal,
                        run_id=run_id,
                        title=f"{run.target or run.symbol or 'Research'} research task",
                        summary=report_content or summary,
                        symbol=run.symbol,
                        research_type=run.research_type,
                        confidence=1.0 if outcome.verdict is ReviewVerdict.APPROVE else 0.5,
                    )
                    await service.record_assistant_message(run_id, principal, summary)
                    if outcome.verdict is ReviewVerdict.HUMAN_REVIEW:
                        await service.append_event(
                            run_id, principal, "review.required", {"verdict": outcome.verdict.value}
                        )
                        await service.request_confirmation(
                            run_id, principal, verdict=outcome.verdict.value
                        )
                    elif outcome.verdict is ReviewVerdict.REJECT:
                        await service.transition(
                            run_id,
                            principal,
                            AgentRunStatus.REJECTED,
                            "run.rejected",
                            {"reason": "research_conclusion_invalid", "revision_count": outcome.revision_count},
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
        except MarketDebateRunError as error:
            async with self.session_factory() as session:
                service = AgentRunService(AgentRunRepository(session))
                with suppress(Exception):
                    await service.transition(
                        run_id,
                        principal,
                        AgentRunStatus.FAILED,
                        "run.failed",
                        {"error_code": str(error), "recoverable": False},
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
        except Exception:  # noqa: BLE001 - terminal guard for a user-visible development Run
            # A development executor must not strand a user-visible Run in
            # "running" when an unexpected schema or persistence error occurs.
            async with self.session_factory() as session:
                service = AgentRunService(AgentRunRepository(session))
                with suppress(Exception):
                    await service.transition(
                        run_id,
                        principal,
                        AgentRunStatus.FAILED,
                        "run.failed",
                        {"error_code": "development_execution_error", "recoverable": True},
                    )
                    await service.append_event(
                        run_id, principal, "run.recovery_required", {"action": "recover"}
                    )

    async def wait_before_first_step(self) -> None:
        """Yield at a cancellation/deadline boundary before the first development step."""
        await asyncio.sleep(0)
