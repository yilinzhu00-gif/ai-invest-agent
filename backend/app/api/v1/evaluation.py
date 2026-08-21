"""Read-only evaluation summary for the research quality dashboard."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.agent_runs import get_request_principal, require_agent_run_permission
from backend.app.db.session import get_db_session
from backend.app.domain.agent_runs.models import AgentRun, AgentRunEvent
from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.evaluation.evaluator import EvaluationReport, evaluate_dataset, load_report
from backend.app.evaluation.metrics import aggregate_runtime_metrics, score_runtime_run

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class EvaluationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    mode: str
    total_cases: int
    status: str
    metrics: dict[str, object]
    errors: list[str]

    @classmethod
    def from_report(cls, report: EvaluationReport) -> "EvaluationSummaryResponse":
        return cls(
            dataset_version=report.dataset_version,
            mode=report.mode,
            total_cases=report.total_cases,
            status=report.status,
            metrics=report.metrics,
            errors=report.errors,
        )


class RuntimeEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    total_research: int
    success_rate: float | None
    average_latency_seconds: float | None
    average_cost_usd: float | None
    accuracy: float | None
    citation_score: float | None
    tool_success_rate: float | None
    coverage: dict[str, int]


@router.get("/runtime-summary", response_model=RuntimeEvaluationResponse)
async def get_runtime_evaluation_summary(
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RuntimeEvaluationResponse:
    """Return workspace-scoped metrics from persisted Agent Run telemetry."""
    require_agent_run_permission(principal)
    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": principal.workspace_id},
    )
    rows = list(
        (
            await session.execute(
                select(AgentRun, AgentRunEvent)
                .outerjoin(AgentRunEvent, AgentRunEvent.run_id == AgentRun.id)
                .where(
                    AgentRun.workspace_id == principal.workspace_id,
                    AgentRun.principal_id == principal.principal_id,
                )
                .order_by(AgentRun.created_at.desc(), AgentRunEvent.sequence)
            )
        ).all()
    )
    events_by_run: dict[object, list[dict[str, object]]] = {}
    runs: dict[object, AgentRun] = {}
    for run, event in rows:
        runs[run.id] = run
        if event is not None:
            events_by_run.setdefault(run.id, []).append(
                {"event_type": event.event_type, "payload": event.payload}
            )
    scored = [
        score_runtime_run(
            run_id=str(run.id),
            status=run.status,
            created_at=run.created_at,
            updated_at=run.updated_at,
            cost_microusd=run.cost_microusd,
            events=events_by_run.get(run.id, []),
        )
        for run in runs.values()
    ]
    return RuntimeEvaluationResponse(source="agent_runs", **aggregate_runtime_metrics(scored))


@router.get("/summary", response_model=EvaluationSummaryResponse)
def get_evaluation_summary(request: Request) -> EvaluationSummaryResponse:
    settings = request.app.state.settings
    report_path = Path(settings.evaluation_report_path)
    if report_path.exists():
        return EvaluationSummaryResponse.from_report(load_report(report_path))
    dataset_path = Path(settings.evaluation_dataset_path)
    if dataset_path.exists():
        # Do not write from a GET; this keeps the dashboard read-only and safe.
        return EvaluationSummaryResponse.from_report(evaluate_dataset(dataset_path))
    return EvaluationSummaryResponse(
        dataset_version="unknown",
        mode="offline",
        total_cases=0,
        status="UNVERIFIED",
        metrics={
            "accuracy": None,
            "citation_score": None,
            "cost_usd": None,
            "latency_seconds": None,
            "tool_success_rate": None,
            "coverage": {},
        },
        errors=["evaluation dataset/report is not configured"],
    )
