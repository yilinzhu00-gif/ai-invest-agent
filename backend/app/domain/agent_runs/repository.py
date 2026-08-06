"""Database operations for Agent Runs; authorization stays in the service layer."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.agent_runs.models import AgentRun, AgentRunEvent, ConversationMessage


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self, *, workspace_id: str, principal_id: str, question: str, correlation_id: str
    ) -> AgentRun:
        run = AgentRun(
            workspace_id=workspace_id,
            principal_id=principal_id,
            question=question,
            status="queued",
            executor_mode="development_only",
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
