"""LangGraph orchestration for the Phase 2 six-role research workflow.

The graph is intentionally model-agnostic. Phase 1 tools or a future retrieval
layer provide ``financial_report``, ``industry_data``, ``stock_data`` and
``market_data``; specialist nodes only transform those inputs into cited,
structured findings. This keeps an offline run reproducible and prevents a
missing public provider from being silently replaced by model memory.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.debate_agent import DebateAgent
from backend.app.agents.financial_analyst import FinancialAnalystAgent
from backend.app.agents.industry_analyst import IndustryAnalystAgent
from backend.app.agents.market_analyst import MarketAnalystAgent
from backend.app.agents.planner import make_plan
from backend.app.agents.reflection_agent import ReflectionAgent
from backend.app.agents.research_contracts import MultiAgentState
from backend.app.agents.schemas import Citation

GRAPH_ORDER = (
    "planner",
    "financial_analyst",
    "industry_analyst",
    "market_analyst",
    "debate",
    "reflection",
)


def _evidence(state: MultiAgentState) -> list[Citation]:
    raw = state.get("evidence", [])
    return [item if isinstance(item, Citation) else Citation.model_validate(item) for item in raw]


def _payload(state: MultiAgentState, key: str) -> dict[str, object]:
    raw = state.get(key)  # type: ignore[literal-required]
    return dict(raw) if isinstance(raw, dict) else {}


def build_multi_agent_graph() -> Any:
    """Compile the Planner -> specialists -> Debate -> Reflection graph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(MultiAgentState)
    financial = FinancialAnalystAgent()
    industry = IndustryAnalystAgent()
    market = MarketAnalystAgent()
    debate = DebateAgent()
    reflection = ReflectionAgent()

    def planner_node(state: MultiAgentState) -> dict[str, object]:
        return {"plan": make_plan(
            state["question"],
            state.get("symbol"),
            user_memory=state.get("user_memory"),
            research_memories=state.get("research_memories", []),
        )}

    def financial_node(state: MultiAgentState) -> dict[str, object]:
        finding = financial.analyze(
            symbol=state.get("symbol"),
            report=_payload(state, "financial_report"),
            evidence=_evidence(state),
        )
        return {"financial_analysis": finding}

    def industry_node(state: MultiAgentState) -> dict[str, object]:
        finding = industry.analyze(
            symbol=state.get("symbol"),
            data=_payload(state, "industry_data"),
            evidence=_evidence(state),
        )
        return {"industry_analysis": finding}

    def market_node(state: MultiAgentState) -> dict[str, object]:
        finding = market.analyze(
            symbol=state.get("symbol"),
            stock_data=_payload(state, "stock_data"),
            market_data=_payload(state, "market_data"),
            evidence=_evidence(state),
        )
        return {"market_analysis": finding}

    def debate_node(state: MultiAgentState) -> dict[str, object]:
        findings = [
            state["financial_analysis"],
            state["industry_analysis"],
            state["market_analysis"],
        ]
        return {"debate": debate.run(findings=findings)}

    def reflection_node(state: MultiAgentState) -> dict[str, object]:
        findings = [
            state["financial_analysis"],
            state["industry_analysis"],
            state["market_analysis"],
        ]
        return {
            "reflection": reflection.run(
                findings=findings,
                debate=state["debate"],
                evidence=_evidence(state),
            )
        }

    graph.add_node("planner", planner_node)
    graph.add_node("financial_analyst", financial_node)
    graph.add_node("industry_analyst", industry_node)
    graph.add_node("market_analyst", market_node)
    graph.add_node("debate", debate_node)
    graph.add_node("reflection", reflection_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "financial_analyst")
    graph.add_edge("financial_analyst", "industry_analyst")
    graph.add_edge("industry_analyst", "market_analyst")
    graph.add_edge("market_analyst", "debate")
    graph.add_edge("debate", "reflection")
    graph.add_edge("reflection", END)
    return graph.compile()


def run_multi_agent_research(
    question: str,
    *,
    symbol: str | None = None,
    evidence: list[Citation] | None = None,
    financial_report: dict[str, object] | None = None,
    industry_data: dict[str, object] | None = None,
    stock_data: dict[str, object] | None = None,
    market_data: dict[str, object] | None = None,
    user_memory: object | None = None,
    research_memories: list[object] | None = None,
) -> dict[str, object]:
    """Run one deterministic graph using only caller-supplied observations."""
    state: MultiAgentState = {
        "question": question,
        "symbol": symbol,
        "evidence": evidence or [],
        "financial_report": financial_report or {},
        "industry_data": industry_data or {},
        "stock_data": stock_data or {},
        "market_data": market_data or {},
        "user_memory": user_memory,
        "research_memories": research_memories or [],
    }
    return dict(build_multi_agent_graph().invoke(state))


async def arun_multi_agent_research(
    question: str,
    *,
    symbol: str | None = None,
    evidence: list[Citation] | None = None,
    financial_report: dict[str, object] | None = None,
    industry_data: dict[str, object] | None = None,
    stock_data: dict[str, object] | None = None,
    market_data: dict[str, object] | None = None,
    user_memory: object | None = None,
    research_memories: list[object] | None = None,
) -> dict[str, object]:
    """Async counterpart for FastAPI/worker callers."""
    state: MultiAgentState = {
        "question": question,
        "symbol": symbol,
        "evidence": evidence or [],
        "financial_report": financial_report or {},
        "industry_data": industry_data or {},
        "stock_data": stock_data or {},
        "market_data": market_data or {},
        "user_memory": user_memory,
        "research_memories": research_memories or [],
    }
    return dict(await build_multi_agent_graph().ainvoke(state))
