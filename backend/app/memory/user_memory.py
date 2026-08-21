"""Structured investment preferences for one user in one workspace."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, DateTime, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def _clean_items(value: list[str]) -> list[str]:
    """Normalize preference values while keeping order and removing duplicates."""
    result: list[str] = []
    for item in value:
        normalized = item.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


class UserMemoryProfile(BaseModel):
    """Validated user memory payload persisted by :class:`UserMemoryRepository`."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(
        min_length=1,
        max_length=128,
        validation_alias=AliasChoices("user_id", "principal_id"),
    )
    investment_preferences: list[str] = Field(default_factory=list, max_length=64)
    investment_style: str | None = Field(default=None, max_length=128)
    risk_level: str = Field(default="unknown", min_length=1, max_length=32)
    industries: list[str] = Field(default_factory=list, max_length=64)
    historical_stocks: list[str] = Field(default_factory=list, max_length=128)

    @field_validator("investment_preferences", "industries", "historical_stocks")
    @classmethod
    def normalize_items(cls, value: list[str]) -> list[str]:
        return _clean_items(value)

    @field_validator("risk_level")
    @classmethod
    def normalize_risk_level(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("risk_level must not be blank")
        return value


class UserMemory(Base):
    """Current investment profile; one row is kept per workspace/user pair."""

    __tablename__ = "user_memories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_user_memories_workspace_user"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    investment_preferences: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    investment_style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    industries: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    historical_stocks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def principal_id(self) -> str:
        """Compatibility alias for the API's principal terminology."""
        return self.user_id


class UserMemoryRepository:
    """PostgreSQL repository for workspace-isolated user profiles."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        principal_id: str | None = None,
    ) -> UserMemory | None:
        resolved_user_id = user_id or principal_id
        if not resolved_user_id:
            raise ValueError("user_id or principal_id is required")
        statement = select(UserMemory).where(
            UserMemory.workspace_id == workspace_id,
            UserMemory.user_id == resolved_user_id,
        )
        return await self.session.scalar(statement)

    async def upsert(self, profile: UserMemoryProfile) -> UserMemory:
        """Insert or replace a profile atomically on the workspace/user key."""
        values = profile.model_dump()
        statement = (
            insert(UserMemory)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[UserMemory.workspace_id, UserMemory.user_id],
                set_={
                    "investment_preferences": values["investment_preferences"],
                    "investment_style": values["investment_style"],
                    "risk_level": values["risk_level"],
                    "industries": values["industries"],
                    "historical_stocks": values["historical_stocks"],
                    "updated_at": func.now(),
                },
            )
            .returning(UserMemory)
        )
        memory = await self.session.scalar(statement)
        if memory is None:  # pragma: no cover - PostgreSQL RETURNING always yields one row
            raise RuntimeError("user memory upsert did not return a row")
        return memory

    save = upsert
    get_profile = get
    save_profile = upsert
