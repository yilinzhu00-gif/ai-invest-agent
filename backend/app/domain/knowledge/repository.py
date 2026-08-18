"""PostgreSQL persistence for immutable document evidence blocks."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.knowledge.models import Document, PersistentDocumentBlock
from backend.app.domain.knowledge.query_terms import retrieval_query_terms
from backend.app.ingestion.schemas import ParsedDocument


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        workspace_id: str,
        filename: str,
        symbol: str | None,
        document_type: str,
        source_url: str | None,
        source_sha256: str,
        parsed: ParsedDocument,
        status: str,
    ) -> tuple[Document, int]:
        previous_version = await self.session.scalar(
            select(func.coalesce(func.max(Document.version), 0)).where(
                Document.workspace_id == workspace_id,
                Document.filename == filename,
            )
        )
        document = Document(
            workspace_id=workspace_id,
            filename=filename,
            symbol=symbol,
            document_type=document_type,
            source_url=source_url,
            source_sha256=source_sha256,
            version=int(previous_version or 0) + 1,
            parser_version=parsed.parser_version,
            status=status,
            page_count=parsed.page_count,
        )
        self.session.add(document)
        await self.session.flush()
        blocks = [
            PersistentDocumentBlock(
                document_id=document.id,
                page_number=block.page_number,
                block_type=block.block_type,
                text=block.text,
                bbox=block.bbox,
                parser=block.parser,
                confidence=block.confidence,
            )
            for block in parsed.blocks
        ]
        self.session.add_all(blocks)
        await self.session.flush()
        await self.session.commit()
        return document, len(blocks)

    async def search(
        self, *, workspace_id: str, query: str, document_id: UUID | None, limit: int
    ) -> list[tuple[Document, PersistentDocumentBlock]]:
        terms = retrieval_query_terms(query)
        predicates = [func.lower(PersistentDocumentBlock.text).contains(term, autoescape=True) for term in terms]
        statement = (
            select(Document, PersistentDocumentBlock)
            .join(PersistentDocumentBlock, PersistentDocumentBlock.document_id == Document.id)
            .where(Document.workspace_id == workspace_id, Document.status == "ready")
            .order_by(Document.created_at.desc(), PersistentDocumentBlock.page_number, PersistentDocumentBlock.id)
            .limit(limit * 4)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if predicates:
            statement = statement.where(or_(*predicates))
        rows = list((await self.session.execute(statement)).tuples())

        def relevance(row: tuple[Document, PersistentDocumentBlock]) -> tuple[int, int, int]:
            text = row[1].text.lower()
            return (-sum(term in text for term in terms), row[1].page_number, row[1].id)

        return sorted(rows, key=relevance)[:limit]

    async def list_ready(self, *, workspace_id: str, limit: int = 100) -> list[tuple[Document, int]]:
        statement = (
            select(Document, func.count(PersistentDocumentBlock.id))
            .outerjoin(PersistentDocumentBlock, PersistentDocumentBlock.document_id == Document.id)
            .where(Document.workspace_id == workspace_id)
            .group_by(Document.id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        return [(document, int(block_count)) for document, block_count in (await self.session.execute(statement)).all()]

    async def get_ready_announcement_blocks(
        self, *, workspace_id: str, document_id: UUID
    ) -> tuple[Document, list[PersistentDocumentBlock]] | None:
        """Return one workspace-scoped ready announcement and its immutable blocks."""
        document = await self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.document_type == "announcement",
                Document.status == "ready",
            )
        )
        if document is None:
            return None
        blocks = list(
            await self.session.scalars(
                select(PersistentDocumentBlock)
                .where(PersistentDocumentBlock.document_id == document.id)
                .order_by(PersistentDocumentBlock.page_number, PersistentDocumentBlock.id)
            )
        )
        return document, blocks

    async def get_ready_announcement(
        self, *, workspace_id: str, document_id: UUID
    ) -> Document | None:
        return await self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
                Document.document_type == "announcement",
                Document.status == "ready",
            )
        )
