"""Workspace-scoped APIs for explicit user and research memory."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.agent_runs import get_request_principal, require_agent_run_permission
from backend.app.db.session import get_db_session
from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.memory.research_memory import ResearchMemoryRecord, ResearchMemoryRepository
from backend.app.memory.user_memory import UserMemoryProfile, UserMemoryRepository

router = APIRouter(prefix="/memory", tags=["memory"])


class UserMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    user_id: str
    investment_preferences: list[str]
    investment_style: str | None
    risk_level: str
    industries: list[str]
    historical_stocks: list[str]


class ResearchMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    user_id: str | None
    report_title: str
    report_date: date
    confidence: float
    content: str | None
    source_run_id: UUID | None
    research_type: str | None
    user_feedback: str | None
    symbol: str | None


class ResearchMemoryFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: str = Field(min_length=1, max_length=2_000)


class UserMemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investment_preferences: list[str] = Field(default_factory=list, max_length=64)
    investment_style: str | None = Field(default=None, max_length=128)
    risk_level: str = Field(default="unknown", min_length=1, max_length=32)
    industries: list[str] = Field(default_factory=list, max_length=64)
    historical_stocks: list[str] = Field(default_factory=list, max_length=128)


class ResearchMemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_title: str = Field(min_length=1, max_length=512)
    report_date: date
    confidence: float = Field(ge=0.0, le=1.0)
    content: str | None = None
    source_run_id: UUID | None = None
    research_type: str | None = Field(default=None, max_length=32)
    symbol: str | None = Field(default=None, max_length=6)


async def _set_rls(session: AsyncSession, principal: RunPrincipal) -> None:
    from sqlalchemy import text

    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": principal.workspace_id},
    )


@router.get("/user", response_model=UserMemoryResponse | None)
async def get_user_memory(
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserMemoryResponse | None:
    require_agent_run_permission(principal)
    await _set_rls(session, principal)
    memory = await UserMemoryRepository(session).get(principal_id=principal.principal_id, workspace_id=principal.workspace_id)
    return UserMemoryResponse.model_validate(memory) if memory else None


@router.post("/user", response_model=UserMemoryResponse)
async def save_user_memory(
    payload: UserMemoryUpdate,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserMemoryResponse:
    require_agent_run_permission(principal)
    profile = UserMemoryProfile(
        workspace_id=principal.workspace_id,
        user_id=principal.principal_id,
        **payload.model_dump(),
    )
    await _set_rls(session, principal)
    memory = await UserMemoryRepository(session).upsert(profile)
    await session.commit()
    await session.refresh(memory)
    return UserMemoryResponse.model_validate(memory)


@router.get("/research", response_model=list[ResearchMemoryResponse])
async def list_research_memory(
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    symbol: str | None = None,
    limit: int = 20,
) -> list[ResearchMemoryResponse]:
    require_agent_run_permission(principal)
    await _set_rls(session, principal)
    memories = await ResearchMemoryRepository(session).list(
        workspace_id=principal.workspace_id,
        principal_id=principal.principal_id,
        symbol=symbol,
        limit=limit,
    )
    return [ResearchMemoryResponse.model_validate(memory) for memory in memories]


@router.post("/research", response_model=ResearchMemoryResponse, status_code=status.HTTP_201_CREATED)
async def save_research_memory(
    payload: ResearchMemoryCreate,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResearchMemoryResponse:
    require_agent_run_permission(principal)
    record = ResearchMemoryRecord(
        workspace_id=principal.workspace_id,
        user_id=principal.principal_id,
        **payload.model_dump(),
    )
    await _set_rls(session, principal)
    memory = await ResearchMemoryRepository(session).create(record)
    await session.commit()
    await session.refresh(memory)
    return ResearchMemoryResponse.model_validate(memory)


@router.post("/research/{memory_id}/feedback", response_model=ResearchMemoryResponse)
async def save_research_feedback(
    memory_id: UUID,
    payload: ResearchMemoryFeedback,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResearchMemoryResponse:
    require_agent_run_permission(principal)
    await _set_rls(session, principal)
    repository = ResearchMemoryRepository(session)
    memory = await repository.get(workspace_id=principal.workspace_id, memory_id=memory_id)
    if memory is None or memory.user_id not in {None, principal.principal_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    memory.user_feedback = payload.feedback.strip()
    memory.user_id = principal.principal_id
    await session.commit()
    await session.refresh(memory)
    return ResearchMemoryResponse.model_validate(memory)
