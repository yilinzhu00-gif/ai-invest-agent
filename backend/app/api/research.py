"""Research-facing API boundary.

The persisted Agent Run API remains the implementation of research execution.
This module gives the target architecture a stable, domain-oriented import
point without duplicating the existing HTTP/SSE handlers.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.app.api.v1.agent_runs import (
    get_agent_run_service,
    get_development_run_executor,
    get_request_principal,
    require_agent_run_permission,
)
from backend.app.core.errors import get_correlation_id
from backend.app.domain.agent_runs.executor import DevelopmentRunExecutor
from backend.app.domain.agent_runs.schemas import (
    AgentRunEventResponse,
    AgentRunResponse,
    AgentRunStatus,
    ResearchTaskSchema,
)
from backend.app.domain.agent_runs.service import (
    AgentRunNotFoundError,
    AgentRunService,
    RunPrincipal,
)

router = APIRouter(prefix="/research", tags=["research"])
TERMINAL_STATUSES = frozenset(
    status.value
    for status in (
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.REJECTED,
    )
)


@router.get("/capabilities")
def research_capabilities() -> dict[str, object]:
    """Return the capabilities exposed by the current research workflow."""

    return {
        "workflows": ["research", "market_debate"],
        "delivery": ["json", "sse"],
        "evidence_required": True,
    }


@router.post("/tasks", response_model=AgentRunResponse, status_code=202)
async def create_research_task(
    payload: ResearchTaskSchema,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
    executor: Annotated[DevelopmentRunExecutor, Depends(get_development_run_executor)],
) -> AgentRunResponse:
    """Create a typed research task while reusing the durable Agent Run lifecycle."""
    require_agent_run_permission(principal)
    executor_mode = "celery" if request.app.state.settings.app_env == "production" else "development_only"
    run = await service.create(
        principal,
        payload.question(),
        None,
        None,
        get_correlation_id(request),
        executor_mode=executor_mode,
        target=payload.target.value,
        research_type=payload.research_type.value,
        depth=payload.depth.value,
        time_range=payload.persisted_time_range(),
        output_format=payload.output_format.value,
    )
    executor.submit(run.id, principal)
    return AgentRunResponse.from_model(run)


def _sse(sequence: int | None, event_type: str, payload: dict[str, object]) -> bytes:
    lines = []
    if sequence is not None:
        lines.append(f"id: {sequence}")
    lines.extend(
        (
            f"event: {event_type}",
            f"data: {json.dumps(payload, ensure_ascii=False)}",
            "",
        )
    )
    return ("\n".join(lines) + "\n").encode()


@router.get("/{run_id}/stream")
async def stream_research_events(
    run_id: UUID,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Stream a research trace until its durable Run reaches a terminal state."""
    require_agent_run_permission(principal)
    try:
        after_sequence = max(int(last_event_id or "0"), 0)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid Last-Event-ID") from error
    try:
        await service.get(run_id, principal)
    except AgentRunNotFoundError as error:
        raise HTTPException(status_code=404) from error

    async def event_stream() -> AsyncIterator[bytes]:
        nonlocal after_sequence
        while not await request.is_disconnected():
            events = await service.list_events(run_id, principal, after_sequence)
            for event in events:
                body = AgentRunEventResponse.from_model(event)
                after_sequence = max(after_sequence, body.sequence)
                yield _sse(body.sequence, body.event_type, body.payload)
            run = await service.get(run_id, principal)
            if run.status in TERMINAL_STATUSES:
                yield _sse(None, "heartbeat", {"run_id": str(run_id), "status": run.status})
                return
            yield _sse(None, "heartbeat", {"run_id": str(run_id), "status": run.status})
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
