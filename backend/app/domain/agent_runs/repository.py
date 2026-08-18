"""Database operations for Agent Runs; authorization stays in the service layer."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.agent_runs.models import (
    AgentMemory,
    AgentRun,
    AgentRunEvent,
    ConversationMessage,
)


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        *,
        workspace_id: str,
        principal_id: str,
        question: str,
        symbol: str | None,
        correlation_id: str,
        executor_mode: str,
    ) -> AgentRun:
        run = AgentRun(
            workspace_id=workspace_id,
            principal_id=principal_id,
            question=question,
            symbol=symbol,
            status="queued",
            executor_mode=executor_mode,
            correlation_id=correlation_id,
        )
        self.session.add(run)
        await self.session.flush()
        self.session.add(ConversationMessage(run_id=run.id, role="user", content=question))
        await self.session.flush()
        return run

    async def get_run(self, run_id: UUID, *, lock: bool = False) -> AgentRun | None:
        statement = select(AgentRun).where(AgentRun.id == run_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def claim_queued_run(self, run_id: UUID) -> AgentRun | None:
        """Claim a run exactly once even when a broker redelivers its task."""
        statement = (
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.status == "queued")
            .values(status="running")
            .returning(AgentRun)
        )
        return await self.session.scalar(statement)

    async def append_event(self, run: AgentRun, event_type: str, payload: dict[str, object]) -> AgentRunEvent:
        event = AgentRunEvent(
            run_id=run.id,
            sequence=run.next_sequence,
            event_type=event_type,
            payload=payload,
        )
        run.next_sequence += 1
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(self, run_id: UUID, after_sequence: int) -> list[AgentRunEvent]:
        statement = (
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run_id, AgentRunEvent.sequence > after_sequence)
            .order_by(AgentRunEvent.sequence)
        )
        return list((await self.session.scalars(statement)).all())

    async def append_message(self, run_id: UUID, role: str, content: str) -> ConversationMessage:
        message = ConversationMessage(run_id=run_id, role=role, content=content)
        self.session.add(message)
        await self.session.flush()
        return message

    async def latest_message(self, run_id: UUID, role: str) -> ConversationMessage | None:
        statement = (
            select(ConversationMessage)
            .where(ConversationMessage.run_id == run_id, ConversationMessage.role == role)
            .order_by(ConversationMessage.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def create_memory(
        self, *, workspace_id: str, principal_id: str, source_run_id: UUID, content: str
    ) -> AgentMemory:
        memory = AgentMemory(
            workspace_id=workspace_id,
            principal_id=principal_id,
            source_run_id=source_run_id,
            content=content,
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def list_memories(
        self, *, workspace_id: str, principal_id: str, limit: int
    ) -> list[AgentMemory]:
        statement = (
            select(AgentMemory)
            .where(
                AgentMemory.workspace_id == workspace_id,
                AgentMemory.principal_id == principal_id,
            )
            .order_by(AgentMemory.created_at.desc(), AgentMemory.id.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
