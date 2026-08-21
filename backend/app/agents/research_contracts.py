"""Shared typed contracts for the Phase 2 specialist-agent graph."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents.debate import DebatePosition
from backend.app.agents.planner import ResearchPlan
from backend.app.agents.reflection import ReflectionResult
from backend.app.agents.schemas import Citation, ResearchClaim
from backend.app.memory.research_memory import ResearchMemoryRecord
from backend.app.memory.user_memory import UserMemoryProfile


class AgentFinding(BaseModel):
    """One specialist's evidence-bounded output."""

    model_config = ConfigDict(extra="forbid")

    agent: Literal["financial", "industry", "market"]
    summary: str = Field(min_length=1, max_length=4_000)
    claims: list[ResearchClaim] = Field(default_factory=list, max_length=12)
    missing_information: list[str] = Field(default_factory=list, max_length=12)
    source: str = Field(min_length=1, max_length=512)


class DebateOutput(BaseModel):
    """Bull/Bear/Moderator result with no actionable trading advice."""

    model_config = ConfigDict(extra="forbid")

    bull: DebatePosition
    bear: DebatePosition
    moderator: DebatePosition
    data_gaps: list[str] = Field(default_factory=list, max_length=12)


class MultiAgentState(TypedDict, total=False):
    question: str
    symbol: str | None
    evidence: list[Citation]
    financial_report: dict[str, object]
    industry_data: dict[str, object]
    stock_data: dict[str, object]
    market_data: dict[str, object]
    user_memory: UserMemoryProfile | None
    research_memories: list[ResearchMemoryRecord]
    plan: ResearchPlan
    financial_analysis: AgentFinding
    industry_analysis: AgentFinding
    market_analysis: AgentFinding
    debate: DebateOutput
    reflection: ReflectionResult
