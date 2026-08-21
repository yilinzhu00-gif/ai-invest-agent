"""Historical research reports retained as searchable, confidence-scored memory."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Date, DateTime, Float, Index, String, Text, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ResearchMemoryRecord(BaseModel):
    """Input contract for a historical report.

    ``content`` is optional so a report index can be recorded before its full
    body is uploaded.  ``confidence`` is deliberately bounded to [0, 1].
    """

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=128)
    report_title: str = Field(min_length=1, max_length=512)
    report_date: date
    confidence: float = Field(ge=0.0, le=1.0)
    content: str | None = None
    source_run_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("source_run_id", "task_id"),
    )
    research_type: str | None = Field(default=None, max_length=32)
    user_feedback: str | None = Field(
        default=None,
        max_length=2_000,
        validation_alias=AliasChoices("user_feedback", "feedback"),
    )
    user_id: str | None = Field(
        default=None,
        max_length=128,
        validation_alias=AliasChoices("user_id", "principal_id"),
    )
    symbol: str | None = Field(default=None, max_length=6)

    @field_validator("report_title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("report_title must not be blank")
        return value

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ResearchMemory(Base):
    """A historical report entry scoped to a workspace."""

    __tablename__ = "research_memories"
    __table_args__ = (
        Index("ix_research_memories_workspace_date", "workspace_id", "report_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    report_title: Mapped[str] = mapped_column(String(512), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    research_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(6), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def principal_id(self) -> str | None:
        """Compatibility alias for callers using the Agent Run vocabulary."""
        return self.user_id


class ResearchMemoryRepository:
    """CRUD operations with mandatory workspace filtering."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: ResearchMemoryRecord) -> ResearchMemory:
        memory = ResearchMemory(**record.model_dump())
        self.session.add(memory)
        await self.session.flush()
        return memory

    save = create
    save_report = create

    async def get(self, *, workspace_id: str, memory_id: UUID) -> ResearchMemory | None:
        statement = select(ResearchMemory).where(
            ResearchMemory.workspace_id == workspace_id,
            ResearchMemory.id == memory_id,
        )
        return await self.session.scalar(statement)

    async def get_by_source_run(self, *, workspace_id: str, source_run_id: UUID) -> ResearchMemory | None:
        statement = select(ResearchMemory).where(
            ResearchMemory.workspace_id == workspace_id,
            ResearchMemory.source_run_id == source_run_id,
        )
        return await self.session.scalar(statement)

    async def list(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        principal_id: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[ResearchMemory]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        conditions = [ResearchMemory.workspace_id == workspace_id]
        resolved_user_id = user_id or principal_id
        if resolved_user_id is not None:
            conditions.append(ResearchMemory.user_id == resolved_user_id)
        if symbol is not None:
            conditions.append(ResearchMemory.symbol == symbol)
        statement = (
            select(ResearchMemory)
            .where(*conditions)
            .order_by(ResearchMemory.report_date.desc(), ResearchMemory.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    list_reports = list
