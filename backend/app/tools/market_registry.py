"""Application registrations for the first public market-data tools."""

from collections.abc import Awaitable, Callable
from typing import cast

from pydantic import BaseModel

from backend.app.tools.base import ToolDefinition
from backend.app.tools.market_data import (
    MarketFinancialsInput,
    MarketFinancialsOutput,
    MarketQuoteInput,
    MarketQuoteOutput,
    MarketValuationInput,
    MarketValuationOutput,
    financials_tool,
    quote_tool,
    valuation_tool,
)
from backend.app.tools.registry import ToolRegistry

_Handler = Callable[[BaseModel], Awaitable[BaseModel]]


def build_market_tool_registry() -> ToolRegistry:
    """Build a fixed whitelist of read-only public market tools."""
    return ToolRegistry(
        [
            ToolDefinition(
                name="market.quote",
                input_model=MarketQuoteInput,
                output_model=MarketQuoteOutput,
                required_permission="tools:market:read",
                data_classification="PUBLIC_MARKET_DATA",
                access="read",
                idempotent=True,
                timeout_seconds=15,
                max_calls_per_run=2,
                handler=cast(_Handler, quote_tool),
            ),
            ToolDefinition(
                name="market.valuation",
                input_model=MarketValuationInput,
                output_model=MarketValuationOutput,
                required_permission="tools:market:read",
                data_classification="PUBLIC_MARKET_DATA",
                access="read",
                idempotent=True,
                timeout_seconds=30,
                max_calls_per_run=1,
                handler=cast(_Handler, valuation_tool),
            ),
            ToolDefinition(
                name="market.financials",
                input_model=MarketFinancialsInput,
                output_model=MarketFinancialsOutput,
                required_permission="tools:market:read",
                data_classification="PUBLIC_MARKET_DATA",
                access="read",
                idempotent=True,
                timeout_seconds=30,
                max_calls_per_run=1,
                handler=cast(_Handler, financials_tool),
            ),
        ]
    )
