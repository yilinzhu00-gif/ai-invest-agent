"""Announcement-bound, observed market-reaction API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.v1.agent_runs import get_request_principal
from backend.app.api.v1.documents import _require_permission, get_knowledge_service
from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.domain.knowledge.service import KnowledgeService
from backend.app.tools.event_study import (
    MarketReactionRequest,
    MarketReactionResponse,
    MarketReactionUnavailableError,
    fetch_market_reaction,
)

router = APIRouter(prefix="/documents", tags=["market-reactions"])


@router.post("/{document_id}/market-reaction", response_model=MarketReactionResponse)
async def market_reaction(
    document_id: UUID,
    payload: MarketReactionRequest,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> MarketReactionResponse:
    _require_permission(principal, "document:read")
    document = await service.get_ready_announcement(principal=principal, document_id=document_id)
    if document is None or document.symbol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ready_announcement_not_found")
    try:
        return await fetch_market_reaction(symbol=document.symbol, request=payload)
    except MarketReactionUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error
