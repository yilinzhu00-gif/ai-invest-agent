"""Planner Agent implemented as a small, deterministic LangGraph.

The first graph is intentionally narrow: it decomposes an investment question
into auditable research tasks and does not call a model or claim that any task
has already been completed. Later Researcher/Reviewer nodes can consume the
same ``ResearchPlan`` state.
"""

from collections.abc import Sequence
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from backend.app.memory.research_memory import ResearchMemoryRecord
from backend.app.memory.user_memory import UserMemoryProfile


class ResearchPlan(BaseModel):
    """The bounded plan passed between API and agent orchestration layers."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    symbol: str | None = Field(default=None, min_length=1, max_length=16)
    steps: tuple[str, ...] = ("retrieve_evidence", "validate", "review")
    memory_used: tuple[str, ...] = ()


INVESTMENT_STEPS: tuple[str, ...] = (
    "分析公司基本面",
    "分析AI行业趋势",
    "分析竞争格局",
    "分析估值",
    "总结风险",
)
AI_INDUSTRY_STEP = "分析AI行业趋势"


class PlannerState(TypedDict, total=False):
    question: str
    symbol: str | None
    user_memory: UserMemoryProfile | None
    research_memories: Sequence[ResearchMemoryRecord]
    plan: ResearchPlan


def _is_investment_question(question: str) -> bool:
    markers = ("投资", "估值", "基本面", "股票", "公司分析", "投资价值", "买入", "卖出")
    return any(marker in question for marker in markers)


def _memory_mentions_ai(user_memory: UserMemoryProfile | None) -> bool:
    if user_memory is None:
        return False
    values = [*user_memory.industries, *user_memory.investment_preferences]
    return any(any(marker in value.casefold() for marker in ("ai", "人工智能", "半导体", "芯片")) for value in values)


def make_plan(
    question: str,
    symbol: str | None = None,
    *,
    user_memory: UserMemoryProfile | None = None,
    research_memories: Sequence[ResearchMemoryRecord] = (),
) -> ResearchPlan:
    normalized = question.strip()
    steps = INVESTMENT_STEPS if _is_investment_question(normalized) else ResearchPlan.model_fields["steps"].default
    memory_used: list[str] = []
    if _memory_mentions_ai(user_memory):
        memory_used.append("user_memory:ai_interest")
    if user_memory and user_memory.historical_stocks:
        memory_used.append("user_memory:historical_stocks")
    if research_memories:
        memory_used.append("research_memory:previous_reports")
    return ResearchPlan(
        question=normalized,
        symbol=symbol.strip().upper() if symbol else None,
        steps=steps,
        memory_used=tuple(memory_used),
    )


def build_planner_graph() -> Any:
    """Return a LangGraph ``StateGraph`` whose only node is the Planner."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(PlannerState)

    def planner_node(state: PlannerState) -> dict[str, ResearchPlan]:
        return {"plan": make_plan(
            state["question"],
            state.get("symbol"),
            user_memory=state.get("user_memory"),
            research_memories=state.get("research_memories", ()),
        )}

    graph.add_node("planner", planner_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", END)
    return graph.compile()


def plan_with_langgraph(
    question: str,
    symbol: str | None = None,
    *,
    user_memory: UserMemoryProfile | None = None,
    research_memories: Sequence[ResearchMemoryRecord] = (),
) -> ResearchPlan:
    """Run the Planner graph synchronously and return its typed plan."""
    result = build_planner_graph().invoke({
        "question": question,
        "symbol": symbol,
        "user_memory": user_memory,
        "research_memories": research_memories,
    })
    return ResearchPlan.model_validate(result["plan"])
