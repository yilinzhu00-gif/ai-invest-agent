"""MCP adapter for the existing public stock-price tool."""

from __future__ import annotations

from typing import Any, Literal

from backend.app.tools.stock_tool import (
    StockDataUnavailableError,
    StockPriceInput,
    stock_tool,
)

StockRange = Literal["1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max"]
StockInterval = Literal["1m", "5m", "15m", "30m", "60m", "1d", "1wk", "1mo"]


async def stock_query(
    symbol: str,
    range: StockRange = "1mo",
    interval: StockInterval = "1d",
) -> dict[str, Any]:
    """Query a public stock quote and bounded price history.

    ``symbol`` accepts Yahoo-style tickers (for example ``AAPL`` or
    ``600519``). The result is a JSON object containing the provider, timestamp,
    quote fields and any fields the provider could not supply.
    """

    try:
        result = await stock_tool(StockPriceInput(symbol=symbol, range=range, interval=interval))
    except StockDataUnavailableError as error:
        # Do not leak upstream exception text or URLs through the MCP boundary.
        raise RuntimeError("stock_data_unavailable") from error
    return result.model_dump(mode="json")
