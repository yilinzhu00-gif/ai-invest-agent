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
    RunPrincipal,
)
from backend.app.domain.identity.repository import WorkspaceMembershipRepository
from backend.app.security.authentication import JwtValidationError, OidcJwtValidator
from backend.app.security.authorization import AuthorizationError, require_permission
from backend.app.security.principal import Principal

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


async def get_authenticated_principal(
    request: Request,
    session: AsyncSession,
    authorization: str | None = None,
    workspace_id: str | None = None,
    development_principal_id: str | None = None,
    development_workspace_id: str | None = None,
) -> RunPrincipal:
    """Resolve a development identity locally or an OIDC identity plus local membership."""
    if request.app.state.settings.app_env != "production":
        if not development_principal_id or not development_workspace_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return DevelopmentPrincipal(
            principal_id=development_principal_id, workspace_id=development_workspace_id
        )
    if not authorization or not authorization.startswith("Bearer ") or not workspace_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    validator = request.app.state.oidc_validator
    if not isinstance(validator, OidcJwtValidator):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        claims = validator.validate(authorization.removeprefix("Bearer ").strip())
    except JwtValidationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from error
    membership = await WorkspaceMembershipRepository(session).get_active(
        workspace_id=workspace_id, user_id=str(claims["sub"])
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return Principal(
        user_id=str(claims["sub"]),
        active_workspace_id=workspace_id,
        roles=frozenset({membership.role}),
        permissions=frozenset(str(claims["scope"]).split()),
        token_id=str(claims["jti"]),
        authentication_method="oidc",
        is_human=membership.is_human,
    )


async def get_request_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    workspace_id: Annotated[str | None, Header(alias="X-Workspace-ID")] = None,
    development_principal_id: Annotated[
        str | None, Header(alias="X-Development-Principal-ID")
    ] = None,
    development_workspace_id: Annotated[
        str | None, Header(alias="X-Development-Workspace-ID")
    ] = None,
) -> RunPrincipal:
    return await get_authenticated_principal(
        request=request,
        session=session,
        authorization=authorization,
        workspace_id=workspace_id,
        development_principal_id=development_principal_id,
        development_workspace_id=development_workspace_id,
    )


def require_agent_run_permission(principal: RunPrincipal) -> None:
    if isinstance(principal, Principal):
        try:
            require_permission(principal, "agent:run")
        except AuthorizationError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error


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
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
    executor: Annotated[DevelopmentRunExecutor, Depends(get_development_run_executor)],
) -> AgentRunResponse:
    require_agent_run_permission(principal)
    run = await service.create(principal, payload.question, get_correlation_id(request))
    executor.submit(run.id, principal)
    return AgentRunResponse.from_model(run)


@router.get("/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: UUID,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunResponse:
    require_agent_run_permission(principal)
    try:
        return AgentRunResponse.from_model(await service.get(run_id, principal))
    except AgentRunNotFoundError as error:
        raise _not_found() from error


@router.post("/{run_id}/cancel", response_model=AgentRunResponse)
async def cancel_agent_run(
    run_id: UUID,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunResponse:
    require_agent_run_permission(principal)
    try:
        return AgentRunResponse.from_model(await service.cancel(run_id, principal))
    except AgentRunNotFoundError as error:
        raise _not_found() from error


@router.get("/{run_id}/events")
async def stream_agent_run_events(
    run_id: UUID,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    require_agent_run_permission(principal)
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
