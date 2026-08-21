"""Load and project durable memory into a run-local, model-safe context."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.planner import ResearchPlan, make_plan
from backend.app.agents.schemas import ResearchMemory as AgentResearchMemory
from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.memory.research_memory import (
    ResearchMemory,
    ResearchMemoryRecord,
    ResearchMemoryRepository,
)
from backend.app.memory.user_memory import UserMemory, UserMemoryProfile, UserMemoryRepository


class DurableMemoryContext:
    def __init__(
        self,
        *,
        user: UserMemory | None,
        research: list[ResearchMemory],
    ) -> None:
        self.user = user
        self.research = research

    @property
    def profile(self) -> UserMemoryProfile | None:
        if self.user is None:
            return None
        return UserMemoryProfile.model_validate({
            "workspace_id": self.user.workspace_id,
            "user_id": self.user.user_id,
            "investment_preferences": self.user.investment_preferences,
            "investment_style": self.user.investment_style,
            "risk_level": self.user.risk_level,
            "industries": self.user.industries,
            "historical_stocks": self.user.historical_stocks,
        })

    def plan(self, question: str, symbol: str | None) -> ResearchPlan:
        memories = [
            ResearchMemoryRecord(
                workspace_id=item.workspace_id,
                report_title=item.report_title,
                report_date=item.report_date,
                confidence=item.confidence,
                content=item.content,
                source_run_id=item.source_run_id,
                research_type=item.research_type,
                user_feedback=item.user_feedback,
                user_id=item.user_id,
                symbol=item.symbol,
            )
            for item in self.research
        ]
        return make_plan(question, symbol, user_memory=self.profile, research_memories=memories)

    def as_agent_memories(self, legacy: list[Any] | None = None) -> list[AgentResearchMemory]:
        """Expose memory as context only; it never becomes a factual citation."""
        output = [
            AgentResearchMemory(
                id=uuid5(NAMESPACE_URL, f"user-memory:{self.user.workspace_id}:{self.user.user_id}"),
                content=json.dumps({
                    "kind": "user_profile",
                    "industries": self.user.industries,
                    "investment_preferences": self.user.investment_preferences,
                    "investment_style": self.user.investment_style,
                    "risk_level": self.user.risk_level,
                    "historical_stocks": self.user.historical_stocks,
                }, ensure_ascii=False),
            )
        ] if self.user is not None else []
        output.extend(
            AgentResearchMemory(
                id=item.id,
                content=json.dumps({
                    "kind": "research_memory",
                    "report_title": item.report_title,
                    "report_date": item.report_date.isoformat(),
                    "symbol": item.symbol,
                    "research_type": item.research_type,
                    "content": item.content,
                    "user_feedback": item.user_feedback,
                }, ensure_ascii=False),
            )
            for item in self.research[:8]
        )
        output.extend(
            AgentResearchMemory(id=item.id, content=item.content)
            for item in (legacy or [])
            if item.id not in {memory.id for memory in output}
        )
        return output[:16]


async def load_memory_context(
    session: AsyncSession,
    principal: RunPrincipal,
    *,
    symbol: str | None = None,
) -> DurableMemoryContext:
    user = await UserMemoryRepository(session).get(
        workspace_id=principal.workspace_id,
        principal_id=principal.principal_id,
    )
    research = await ResearchMemoryRepository(session).list(
        workspace_id=principal.workspace_id,
        principal_id=principal.principal_id,
        symbol=symbol,
        limit=8,
    )
    return DurableMemoryContext(user=user, research=research)


async def save_research_memory(
    session: AsyncSession,
    principal: RunPrincipal,
    *,
    run_id: UUID,
    title: str,
    summary: str,
    symbol: str | None,
    research_type: str | None,
    confidence: float,
) -> ResearchMemory:
    repository = ResearchMemoryRepository(session)
    existing = await repository.get_by_source_run(
        workspace_id=principal.workspace_id,
        source_run_id=run_id,
    )
    if existing is not None:
        return existing
    return await repository.create(
        ResearchMemoryRecord(
            workspace_id=principal.workspace_id,
            user_id=principal.principal_id,
            report_title=title[:512],
            report_date=datetime.now(UTC).date(),
            confidence=max(0.0, min(1.0, confidence)),
            content=summary[:20_000],
            source_run_id=run_id,
            research_type=research_type,
            symbol=symbol,
        )
    )
