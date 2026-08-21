"""Read-only stock quote and price-history tool.

The provider uses Yahoo Finance's public chart/quoteSummary endpoints and is
kept behind a protocol so tests and deployments can inject another provider.
No API key is required, but upstream availability is never treated as a
guarantee: failures are surfaced as ``stock_data_unavailable``.
"""

from __future__ import annotations

import asyncio
import json
import math
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockDataUnavailableError(RuntimeError):
    """The upstream market-data provider returned no usable observation."""


def _symbol(value: str) -> str:
    normalized = str(value).strip().upper()
    if not normalized or len(normalized) > 16 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^=" for character in normalized
    ):
        raise ValueError("symbol must be a ticker such as AAPL or 600519")
    return normalized


def _number(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _value(node: Any) -> Any:
    if isinstance(node, dict) and "raw" in node:
        return node["raw"]
    return node


def _human_market_cap(value: float | None) -> str | None:
    if value is None:
        return None
    suffix = ""
    divisor = 1.0
    for candidate, amount in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(value) >= amount:
            suffix, divisor = candidate, amount
            break
    return f"{value / divisor:.2f}{suffix}" if suffix else f"{value:.0f}"


class StockPriceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    range: str = Field(default="1mo", pattern=r"^(1d|5d|1mo|3mo|6mo|1y|5y|max)$")
    interval: str = Field(default="1d", pattern=r"^(1m|5m|15m|30m|60m|1d|1wk|1mo)$")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return _symbol(value)


class PriceBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class StockPriceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str | None = None
    price: float
    currency: str | None = None
    market_cap: str | None = None
    pe: float | None = None
    previous_close: float | None = None
    change_percent: float | None = None
    history: list[PriceBar] = Field(default_factory=list)
    source: str = "Yahoo Finance public endpoints"
    as_of: datetime
    missing_fields: list[str] = Field(default_factory=list)


class StockDataProvider(Protocol):
    async def get_stock(self, payload: StockPriceInput) -> StockPriceOutput: ...


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-investment-copilot/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise StockDataUnavailableError("stock_data_unavailable") from error
    if not isinstance(result, dict):
        raise StockDataUnavailableError("stock_data_schema_changed")
    return result


def _chart_url(symbol: str, period: str, interval: str) -> str:
    query = urllib.parse.urlencode({"range": period, "interval": interval, "includePrePost": "false"})
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}"


def _summary_url(symbol: str) -> str:
    modules = "price,summaryDetail,defaultKeyStatistics"
    return (
        "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
        f"{urllib.parse.quote(symbol)}?modules={modules}"
    )


class YahooFinanceProvider:
    async def get_stock(self, payload: StockPriceInput) -> StockPriceOutput:
        responses: list[Any] = await asyncio.gather(
            asyncio.to_thread(_request_json, _chart_url(payload.symbol, payload.range, payload.interval)),
            asyncio.to_thread(_request_json, _summary_url(payload.symbol)),
            return_exceptions=True,
        )
        chart_response, summary_response = responses
        if isinstance(chart_response, Exception):
            raise StockDataUnavailableError("stock_data_unavailable") from chart_response
        chart_result = chart_response.get("chart", {}).get("result") or []
        if not chart_result:
            raise StockDataUnavailableError("stock_data_unavailable")
        chart = chart_result[0]
        meta = chart.get("meta", {})
        timestamps = chart.get("timestamp") or []
        quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
        bars: list[PriceBar] = []
        for index, timestamp in enumerate(timestamps):
            values = {key: _number(items[index]) if index < len(items) else None for key, items in quote.items()}
            bars.append(PriceBar(date=datetime.fromtimestamp(timestamp, UTC), **values))

        summary: dict[str, Any] = {}
        if not isinstance(summary_response, Exception):
            result = summary_response.get("quoteSummary", {}).get("result") or []
            if result:
                for section_name, section in result[0].items():
                    if isinstance(section, dict) and "raw" in section:
                        summary[section_name] = section
                    elif isinstance(section, dict):
                        summary.update(section)
        price = _number(meta.get("regularMarketPrice")) or (bars[-1].close if bars else None)
        if price is None:
            raise StockDataUnavailableError("stock_data_schema_changed")
        previous = _number(meta.get("previousClose")) or _number(summary.get("previousClose"))
        change = ((price / previous) - 1) * 100 if previous else None
        market_cap_raw = _number(_value(summary.get("marketCap")))
        missing = [field for field, value in (("market_cap", market_cap_raw), ("pe", _value(summary.get("trailingPE")))) if value is None]
        return StockPriceOutput(
            symbol=payload.symbol,
            name=meta.get("longName") or meta.get("shortName") or _value(summary.get("longName")),
            price=price,
            currency=meta.get("currency"),
            market_cap=_human_market_cap(market_cap_raw),
            pe=_number(_value(summary.get("trailingPE"))),
            previous_close=previous,
            change_percent=change,
            history=bars,
            as_of=datetime.now(UTC),
            missing_fields=missing,
        )


_provider: StockDataProvider = YahooFinanceProvider()


def get_stock_data_provider() -> StockDataProvider:
    return _provider


async def stock_tool(payload: StockPriceInput) -> StockPriceOutput:
    return await get_stock_data_provider().get_stock(payload)


async def get_stock_price(symbol: str, *, range: str = "1mo", interval: str = "1d") -> dict[str, Any]:
    """Return a JSON-serialisable quote object for a ticker such as ``AAPL``."""
    result = await stock_tool(StockPriceInput(symbol=symbol, range=range, interval=interval))
    return result.model_dump(mode="json")
