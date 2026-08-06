from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PersistentDocumentBlock(Base):
    __tablename__ = "document_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)
    parser: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class PersistentTableBlock(Base):
    __tablename__ = "table_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_block_id: Mapped[int] = mapped_column(
        ForeignKey("document_blocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cells: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    header_rows: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    units: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_pages: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    merge_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retrieval_text: Mapped[str] = mapped_column(Text, nullable=False)
