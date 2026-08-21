"""Fixed registry for the Phase 1 general-market tools.

The existing ``build_market_tool_registry`` remains unchanged for its tested
A-share contract. This registry is the additive US/global-data surface used by
the Planner/Researcher flow.
"""

from collections.abc import Awaitable, Callable
from typing import cast

from pydantic import BaseModel

from backend.app.tools.base import ToolDefinition
from backend.app.tools.financial_tool import (
    FinancialReportInput,
    FinancialReportOutput,
    financial_tool,
)
from backend.app.tools.news_tool import NewsSearchInput, NewsSearchOutput, news_tool
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.search_tool import SearchInput, SearchOutput, search_tool
from backend.app.tools.stock_tool import StockPriceInput, StockPriceOutput, stock_tool

_Handler = Callable[[BaseModel], Awaitable[BaseModel]]


def build_data_tool_registry() -> ToolRegistry:
    """Build read-only, permissioned Phase 1 tools."""
    return ToolRegistry(
        [
            ToolDefinition(
                name="get_stock_price",
                input_model=StockPriceInput,
                output_model=StockPriceOutput,
                required_permission="tools:market:read",
                data_classification="PUBLIC_MARKET_DATA",
                access="read",
                idempotent=True,
                timeout_seconds=20,
                max_calls_per_run=3,
                handler=cast(_Handler, stock_tool),
            ),
            ToolDefinition(
                name="get_financial_report",
                input_model=FinancialReportInput,
                output_model=FinancialReportOutput,
                required_permission="tools:market:read",
                data_classification="PUBLIC_FINANCIAL_DATA",
                access="read",
                idempotent=True,
                timeout_seconds=30,
                max_calls_per_run=2,
                handler=cast(_Handler, financial_tool),
            ),
            ToolDefinition(
                name="search_news",
                input_model=NewsSearchInput,
                output_model=NewsSearchOutput,
                required_permission="tools:news:read",
                data_classification="PUBLIC_NEWS",
                access="read",
                idempotent=True,
                timeout_seconds=20,
                max_calls_per_run=3,
                handler=cast(_Handler, news_tool),
            ),
            ToolDefinition(
                name="search_web",
                input_model=SearchInput,
                output_model=SearchOutput,
                required_permission="tools:search:read",
                data_classification="PUBLIC_WEB",
                access="read",
                idempotent=True,
                timeout_seconds=20,
                max_calls_per_run=3,
                handler=cast(_Handler, search_tool),
            ),
        ]
    )

