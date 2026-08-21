from backend.app.agents.multi_agent import GRAPH_ORDER, run_multi_agent_research
from backend.app.agents.reflection import ReflectionResult
from backend.app.agents.research_contracts import AgentFinding, DebateOutput
from backend.app.agents.schemas import Citation


def _evidence() -> list[Citation]:
    return [
        Citation(id="fin-revenue", source="annual report", locator="p10", text="Revenue 100, profit 20, gross margin 70, growth 30"),
        Citation(id="industry-trend", source="industry report", locator="p2", text="AI industry trend, market size 500"),
        Citation(id="market-price", source="market quote", locator="2026-08-21", text="Price 200 change 5 RSI 55 moving average 190"),
        Citation(id="valuation", source="valuation report", locator="p3", text="PE 35"),
        Citation(id="sentiment", source="news sentiment", locator="2026-08-21", text="sentiment positive"),
    ]


def test_multi_agent_graph_runs_all_six_roles_and_preserves_citations() -> None:
    result = run_multi_agent_research(
        "分析英伟达投资价值",
        symbol="NVDA",
        evidence=_evidence(),
        financial_report={
            "symbol": "NVDA",
            "report_period": "2026-Q2",
            "revenue": 100,
            "profit": 20,
            "gross_margin": 70,
            "growth_rate": 30,
            "source": "annual report",
        },
        industry_data={
            "trend": "AI infrastructure demand is expanding",
            "competition": "GPU suppliers compete on ecosystem and performance",
            "market_size": 500,
            "market_size_unit": "B USD",
            "source": "industry report",
        },
        stock_data={"symbol": "NVDA", "price": 200, "change_percent": 5, "pe": 35, "rsi": 55, "ma_20": 190, "source": "market quote"},
        market_data={"sentiment": "positive", "source": "news sentiment"},
    )

    assert tuple(result["plan"].steps) == (
        "分析公司基本面",
        "分析AI行业趋势",
        "分析竞争格局",
        "分析估值",
        "总结风险",
    )
    assert isinstance(result["financial_analysis"], AgentFinding)
    assert isinstance(result["industry_analysis"], AgentFinding)
    assert isinstance(result["market_analysis"], AgentFinding)
    assert isinstance(result["debate"], DebateOutput)
    assert isinstance(result["reflection"], ReflectionResult)
    assert result["reflection"].accuracy == 10
    assert result["reflection"].score is not None
    assert result["reflection"].score.accuracy == 10
    assert result["reflection"].missing == ()


def test_reflection_reports_missing_valuation_data_instead_of_inventing_it() -> None:
    result = run_multi_agent_research(
        "分析英伟达投资价值",
        symbol="NVDA",
        evidence=_evidence()[:2],
        financial_report={"symbol": "NVDA", "revenue": 100, "profit": 20},
        industry_data={"trend": "AI demand"},
        stock_data={"symbol": "NVDA", "price": 200},
    )
    reflection = result["reflection"]
    assert isinstance(reflection, ReflectionResult)
    assert "valuation_data" in reflection.missing
    assert reflection.accepted is False


def test_graph_order_is_explicit_for_auditing() -> None:
    assert GRAPH_ORDER == (
        "planner",
        "financial_analyst",
        "industry_analyst",
        "market_analyst",
        "debate",
        "reflection",
    )
