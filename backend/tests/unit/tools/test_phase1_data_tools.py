import pytest

from backend.app.agents.planner import INVESTMENT_STEPS, plan_with_langgraph
from backend.app.tools import financial_tool, news_tool, stock_tool
from backend.app.tools.data_registry import build_data_tool_registry
from backend.app.tools.policy import ToolPrincipal


@pytest.mark.asyncio
async def test_stock_tool_maps_chart_and_summary_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url: str) -> dict[str, object]:
        if "/chart/" in url:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 200.0,
                                "previousClose": 195.0,
                                "currency": "USD",
                                "longName": "Apple Inc.",
                            },
                            "timestamp": [1_723_680_000],
                            "indicators": {"quote": [{"open": [199], "high": [202], "low": [198], "close": [200], "volume": [1000]}]},
                        }
                    ]
                }
            }
        return {"quoteSummary": {"result": [{"marketCap": {"raw": 3_000_000_000_000}, "trailingPE": {"raw": 35.0}}]}}

    monkeypatch.setattr(stock_tool, "_request_json", fake_request)
    output = await stock_tool.get_stock_price("aapl")
    assert output["name"] == "Apple Inc."
    assert output["price"] == 200.0
    assert output["market_cap"] == "3.00T"
    assert output["pe"] == 35.0
    assert output["history"][0]["close"] == 200.0


@pytest.mark.asyncio
async def test_financial_tool_returns_explicit_metrics_and_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url: str) -> dict[str, object]:
        if "fundamentals-timeseries" in url:
            return {
                "timeseries": {
                    "result": [
                        {"meta": {"type": ["annualTotalRevenue"]}, "annualTotalRevenue": [{"asOfDate": "2025-12-31", "reportedValue": {"raw": 100.0}}]},
                        {"meta": {"type": ["annualNetIncome"]}, "annualNetIncome": [{"asOfDate": "2025-12-31", "reportedValue": {"raw": 20.0}}]},
                        {"meta": {"type": ["annualGrossProfit"]}, "annualGrossProfit": [{"asOfDate": "2025-12-31", "reportedValue": {"raw": 40.0}}]},
                    ]
                }
            }
        return {"quoteSummary": {"result": [{"price": {"longName": {"raw": "Apple Inc."}}, "revenueGrowth": {"raw": 0.1}}]}}

    monkeypatch.setattr(financial_tool, "_request_json", fake_request)
    output = await financial_tool.get_financial_report("AAPL")
    assert output["revenue"] == 100.0
    assert output["profit"] == 20.0
    assert output["gross_margin"] == 40.0
    assert output["growth_rate"] == 10.0
    assert "eps" in output["missing_fields"]


@pytest.mark.asyncio
async def test_news_parser_returns_required_attribution_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    rss = b"""<rss><channel><item><title>NVIDIA results</title><link>https://example.com/nvda</link><description>&lt;b&gt;Revenue grew&lt;/b&gt;</description><source>Example</source><pubDate>Thu, 21 Aug 2026 00:00:00 GMT</pubDate></item></channel></rss>"""
    monkeypatch.setattr(news_tool, "_fetch_rss", lambda query: rss)
    items = await news_tool.search_news("NVIDIA 最近新闻", limit=1)
    assert items == [{"title": "NVIDIA results", "summary": "Revenue grew", "source": "Example", "date": "2026-08-21T00:00:00Z"}]


@pytest.mark.asyncio
async def test_data_registry_exposes_phase1_names_and_policy() -> None:
    registry = build_data_tool_registry()
    assert registry.names == frozenset({"get_stock_price", "get_financial_report", "search_news", "search_web"})
    with pytest.raises(Exception, match="tool_not_authorized"):
        await registry.invoke("get_stock_price", {"symbol": "AAPL"}, ToolPrincipal("w", frozenset()), 0)


def test_planner_graph_decomposes_investment_question() -> None:
    plan = plan_with_langgraph("分析英伟达投资价值")
    assert plan.steps == INVESTMENT_STEPS
