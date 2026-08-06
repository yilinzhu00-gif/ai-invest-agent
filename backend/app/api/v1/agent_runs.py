"""HTTP and SSE endpoints for persisted, development-only Agent Runs."""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import get_correlation_id
from backend.app.db.session import get_db_session, get_request_session_factory
from backend.app.domain.agent_runs.executor import DevelopmentRunExecutor
from backend.app.domain.agent_runs.repository import AgentRunRepository
from backend.app.domain.agent_runs.schemas import (
    AgentRunEventResponse,
    AgentRunResponse,
    CreateAgentRunRequest,
)
from backend.app.domain.agent_runs.service import (
    AgentRunNotFoundError,
    AgentRunService,
    DevelopmentPrincipal,
)

router = APIRouter(prefix="/agent/runs", tags=["agent-runs"])


async def get_development_principal(
    request: Request,
    principal_id: Annotated[str | None, Header(alias="X-Development-Principal-ID")] = None,
    workspace_id: Annotated[str | None, Header(alias="X-Development-Workspace-ID")] = None,
) -> DevelopmentPrincipal:
    if request.app.state.settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not principal_id or not workspace_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return DevelopmentPrincipal(principal_id=principal_id, workspace_id=workspace_id)


async def get_agent_run_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentRunService:
    return AgentRunService(AgentRunRepository(session))


def get_development_run_executor(request: Request) -> DevelopmentRunExecutor:
    executor = request.app.state.agent_run_executor
    if executor is None:
        executor = DevelopmentRunExecutor(
            get_request_session_factory(request), request.app.state.settings
        )
        request.app.state.agent_run_executor = executor
    return executor


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def _encode_event(sequence: int | None, event_type: str, payload: dict[str, object]) -> bytes:
    lines = []
    if sequence is not None:
        lines.append(f"id: {sequence}")
    lines.extend((f"event: {event_type}", f"data: {json.dumps(payload, ensure_ascii=False)}", ""))
    return ("\n".join(lines) + "\n").encode()


@router.post("", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_agent_run(
    payload: CreateAgentRunRequest,
    request: Request,
    principal: Annotated[DevelopmentPrincipal, Depends(get_development_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
    executor: Annotated[DevelopmentRunExecutor, Depends(get_development_run_executor)],
) -> AgentRunResponse:
    run = await service.create(principal, payload.question, get_correlation_id(request))
    executor.submit(run.id, principal)
    return AgentRunResponse.from_model(run)


@router.get("/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: UUID,
    principal: Annotated[DevelopmentPrincipal, Depends(get_development_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunResponse:
    try:
        return AgentRunResponse.from_model(await service.get(run_id, principal))
    except AgentRunNotFoundError as error:
        raise _not_found() from error


@router.post("/{run_id}/cancel", response_model=AgentRunResponse)
async def cancel_agent_run(
    run_id: UUID,
    principal: Annotated[DevelopmentPrincipal, Depends(get_development_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunResponse:
    try:
        return AgentRunResponse.from_model(await service.cancel(run_id, principal))
    except AgentRunNotFoundError as error:
        raise _not_found() from error


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: UUID,
    request: Request,
    principal: Annotated[DevelopmentPrincipal, Depends(get_development_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    try:
        after_sequence = max(int(last_event_id or "0"), 0)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error
    try:
        events = await service.list_events(run_id, principal, after_sequence)
    except AgentRunNotFoundError as error:
        raise _not_found() from error

    async def event_stream() -> AsyncIterator[bytes]:
        for event in events:
            body = AgentRunEventResponse.from_model(event)
            yield _encode_event(body.sequence, body.event_type, body.payload)
        yield _encode_event(None, "heartbeat", {"run_id": str(run_id)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
