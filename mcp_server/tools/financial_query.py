"""MCP adapter for the existing public financial-report tool."""

from __future__ import annotations

from typing import Any, Literal

from backend.app.tools.financial_tool import (
    FinancialReportInput,
    financial_tool,
)
from backend.app.tools.stock_tool import StockDataUnavailableError


async def financial_query(
    symbol: str,
    period: Literal["annual", "quarterly"] = "annual",
) -> dict[str, Any]:
    """Query the latest public financial report for a ticker.

    Financial values are returned as reported by the provider. Missing values
    remain ``null`` and are listed in ``missing_fields``; this tool does not
    infer or estimate them.
    """

    try:
        result = await financial_tool(FinancialReportInput(symbol=symbol, period=period))
    except StockDataUnavailableError as error:
        raise RuntimeError("financial_data_unavailable") from error
    return result.model_dump(mode="json")
