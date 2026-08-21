"""Application service for the upload -> parse -> cite -> search evidence path."""

import asyncio
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import text

from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.domain.knowledge.repository import DocumentRepository
from backend.app.domain.knowledge.schemas import (
    DocumentResponse,
    EvidenceSearchResult,
    TransactionFactsResponse,
)
from backend.app.domain.knowledge.transaction_facts import extract_transaction_facts
from backend.app.ingestion.parser import DocumentParser, DocumentSafetyError, sha256_file
from backend.app.security.file_upload import FileRejected, inspect_upload


class DocumentUploadError(ValueError):
    pass


EVIDENCE_LIBRARY_SUFFIXES = {".pdf", ".md", ".html", ".csv"}


class KnowledgeService:
    def __init__(self, repository: DocumentRepository, parser: DocumentParser) -> None:
        self.repository = repository
        self.parser = parser

    async def upload(
        self,
        *,
        principal: RunPrincipal,
        filename: str,
        content: bytes,
        symbol: str | None,
        document_type: str,
        source_url: str | None,
    ) -> DocumentResponse:
        await self._set_rls_context(principal)
        self._validate_filename(filename)
        self._validate_source_url(source_url)
        try:
            quarantined = inspect_upload(filename, content, max_bytes=self.parser.max_bytes)
        except FileRejected as error:
            raise DocumentUploadError(str(error)) from error
        suffix = Path(filename).suffix.lower()
        try:
            with tempfile.TemporaryDirectory(prefix="investment-agent-document-") as temp_dir:
                path = Path(temp_dir) / f"upload{suffix}"
                path.write_bytes(quarantined.content)
                parsed = await self.parser.parse_path(path)
                source_sha256 = await asyncio.to_thread(sha256_file, path)
        except (DocumentSafetyError, RuntimeError, ValueError) as error:
            raise DocumentUploadError(str(error)) from error
        status = "ready" if parsed.blocks else "needs_ocr"
        document, block_count = await self.repository.create(
            workspace_id=principal.workspace_id,
            filename=filename,
            symbol=symbol,
            document_type=document_type,
            source_url=source_url,
            source_sha256=source_sha256,
            parsed=parsed,
            status=status,
        )
        return DocumentResponse(
            id=document.id,
            filename=document.filename,
            symbol=document.symbol,
            document_type=document.document_type,  # type: ignore[arg-type]
            source_url=document.source_url,
            version=document.version,
            status=document.status,
            page_count=document.page_count,
            parsed_block_count=block_count,
            created_at=document.created_at,
        )

    async def search(
        self, *, principal: RunPrincipal, query: str, document_id: UUID | None, limit: int
    ) -> list[EvidenceSearchResult]:
        await self._set_rls_context(principal)
        rows = await self.repository.search(
            workspace_id=principal.workspace_id,
            query=query,
            document_id=document_id,
            limit=limit,
        )
        return [
            EvidenceSearchResult(
                evidence_id=f"document:{document.id}:block:{block.id}",
                document_id=document.id,
                document_version=document.version,
                filename=document.filename,
                source_url=document.source_url,
                page_number=block.page_number,
                block_id=str(block.id),
                text=block.text,
                parser=block.parser,
                confidence=block.confidence,
                bbox=block.bbox,
                content=block.text,
                source=document.filename,
                page=block.page_number,
                date=document.created_at.date().isoformat() if document.created_at else None,
            )
            for document, block in rows
        ]

    async def list_documents(self, *, principal: RunPrincipal) -> list[DocumentResponse]:
        await self._set_rls_context(principal)
        return [
            DocumentResponse(
                id=document.id,
                filename=document.filename,
                symbol=document.symbol,
                document_type=document.document_type,  # type: ignore[arg-type]
                source_url=document.source_url,
                version=document.version,
                status=document.status,
                page_count=document.page_count,
                parsed_block_count=block_count,
                created_at=document.created_at,
            )
            for document, block_count in await self.repository.list_ready(
                workspace_id=principal.workspace_id
            )
        ]

    async def extract_transaction_facts(
        self, *, principal: RunPrincipal, document_id: UUID
    ) -> TransactionFactsResponse | None:
        """Extract a fixed fact table from one ready announcement, never from a search snippet."""
        await self._set_rls_context(principal)
        result = await self.repository.get_ready_announcement_blocks(
            workspace_id=principal.workspace_id, document_id=document_id
        )
        if result is None:
            return None
        document, blocks = result
        return TransactionFactsResponse(
            document_id=document.id,
            filename=document.filename,
            document_version=document.version,
            rows=extract_transaction_facts(blocks),
            boundary="每一项仅展示公告原文和页码；未命中直接披露时标记为“公告未披露”，不以常识、行情或其他材料补全。",
        )

    async def get_ready_announcement(
        self, *, principal: RunPrincipal, document_id: UUID
    ) -> DocumentResponse | None:
        await self._set_rls_context(principal)
        document = await self.repository.get_ready_announcement(
            workspace_id=principal.workspace_id, document_id=document_id
        )
        if document is None:
            return None
        return DocumentResponse(
            id=document.id,
            filename=document.filename,
            symbol=document.symbol,
            document_type=document.document_type,  # type: ignore[arg-type]
            source_url=document.source_url,
            version=document.version,
            status=document.status,
            page_count=document.page_count,
            parsed_block_count=0,
            created_at=document.created_at,
        )

    async def _set_rls_context(self, principal: RunPrincipal) -> None:
        await self.repository.session.execute(
            text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
            {"workspace_id": principal.workspace_id},
        )

    @staticmethod
    def _validate_filename(filename: str) -> None:
        path = Path(filename)
        if (
            not filename
            or path.name != filename
            or "\\" in filename
            or len(filename) > 512
            or path.suffix.lower() not in EVIDENCE_LIBRARY_SUFFIXES
        ):
            raise DocumentUploadError("invalid_filename")

    @staticmethod
    def _validate_source_url(source_url: str | None) -> None:
        if source_url is None:
            return
        parsed = urlparse(source_url)
        if len(source_url) > 2048 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DocumentUploadError("invalid_source_url")
