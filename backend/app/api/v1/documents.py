"""Researcher-facing evidence library endpoints; they never fetch arbitrary URLs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.agent_runs import get_request_principal
from backend.app.db.session import get_db_session
from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.domain.knowledge.repository import DocumentRepository
from backend.app.domain.knowledge.schemas import (
    DocumentResponse,
    DocumentType,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    TransactionFactsResponse,
)
from backend.app.domain.knowledge.service import DocumentUploadError, KnowledgeService
from backend.app.ingestion.parser import DocumentParser
from backend.app.security.authorization import AuthorizationError, require_permission
from backend.app.security.principal import Principal

router = APIRouter(tags=["knowledge"])


def _require_permission(principal: RunPrincipal, permission: str) -> None:
    if isinstance(principal, Principal):
        try:
            require_permission(principal, permission)
        except AuthorizationError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error


async def get_knowledge_service(
    session: Annotated[AsyncSession, Depends(get_db_session)], request: Request
) -> KnowledgeService:
    settings = request.app.state.settings
    return KnowledgeService(
        DocumentRepository(session),
        DocumentParser(max_bytes=settings.document_upload_max_bytes, max_pages=settings.document_max_pages),
    )


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    content: Annotated[bytes, Body(media_type="application/octet-stream")],
    filename: Annotated[str, Query(min_length=1, max_length=512)],
    document_type: Annotated[DocumentType, Query()] = "other",
    # A document may describe an A-share, an overseas ticker, or an industry
    # policy without a ticker.  Market-data endpoints keep their stricter
    # six-digit A-share contract; the evidence library does not.
    symbol: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9.-]{1,6}$")] = None,
    source_url: Annotated[str | None, Query(max_length=2048)] = None,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)] = None,  # type: ignore[assignment]
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)] = None,  # type: ignore[assignment]
) -> DocumentResponse:
    _require_permission(principal, "document:write")
    try:
        return await service.upload(
            principal=principal,
            filename=filename,
            content=content,
            symbol=symbol,
            document_type=document_type,
            source_url=source_url,
        )
    except DocumentUploadError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY) from error


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> list[DocumentResponse]:
    _require_permission(principal, "document:read")
    return await service.list_documents(principal=principal)


@router.post("/documents/{document_id}/transaction-facts", response_model=TransactionFactsResponse)
async def extract_transaction_facts(
    document_id: UUID,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> TransactionFactsResponse:
    _require_permission(principal, "document:read")
    facts = await service.extract_transaction_facts(principal=principal, document_id=document_id)
    if facts is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ready_announcement_not_found")
    return facts


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeSearchResponse:
    _require_permission(principal, "document:read")
    return KnowledgeSearchResponse(
        results=await service.search(
            principal=principal,
            query=str(payload.query),
            document_id=payload.document_id,
            limit=payload.limit,
        )
    )
