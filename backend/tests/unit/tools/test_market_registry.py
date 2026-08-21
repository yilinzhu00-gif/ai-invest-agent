import pytest

from backend.app.tools.market_data import (
    MarketQuoteOutput,
    MarketValuationOutput,
)
from backend.app.tools.market_registry import build_market_tool_registry
from backend.app.tools.policy import ToolPolicyError, ToolPrincipal


def test_market_registry_exposes_only_the_first_three_read_tools() -> None:
    registry = build_market_tool_registry()

    assert registry.names == frozenset({"market.quote", "market.valuation", "market.financials"})
    assert registry.definition("market.quote").data_classification == "PUBLIC_MARKET_DATA"
    assert registry.definition("market.quote").access == "read"


@pytest.mark.asyncio
async def test_market_registry_fails_closed_without_market_permission() -> None:
    registry = build_market_tool_registry()

    with pytest.raises(ToolPolicyError, match="tool_not_authorized"):
        await registry.invoke(
            "market.quote",
            {"codes": ["600519"]},
            ToolPrincipal("workspace-1", frozenset()),
            calls_so_far=0,
        )


def test_market_output_models_reject_unexpected_provider_fields() -> None:
    with pytest.raises(ValueError):
        MarketQuoteOutput.model_validate(
            {
                "quotes": [{"symbol": "600519", "price": 10.0, "unexpected": 1}],
                "as_of": "2026-08-21T00:00:00Z",
            }
        )
    with pytest.raises(ValueError):
        MarketValuationOutput.model_validate(
            {
                "symbol": "600519",
                "price": 10.0,
                "forecast_year": 2026,
                "next_forecast_year": 2027,
                "as_of": "2026-08-21T00:00:00Z",
                "unexpected": 1,
            }
        )
