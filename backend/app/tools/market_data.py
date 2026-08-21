"""Typed, read-only market data tools for the first public-data slice.

The provider is deliberately kept behind a small protocol.  The HTTP/API layer
and tests only depend on the typed contracts; a provider outage becomes a safe
``market_data_unavailable`` error instead of leaking upstream details.
"""

from __future__ import annotations

import asyncio
import math
import urllib.request
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketDataUnavailableError(RuntimeError):
    """The public provider returned no usable observation."""


def _code(value: str) -> str:
    normalized = str(value).strip()
    if len(normalized) != 6 or not normalized.isascii() or not normalized.isdigit():
        raise ValueError("symbol must be a 6-digit A-share code")
    return normalized


def _number(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class MarketQuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codes: list[str] = Field(min_length=1, max_length=20)

    @field_validator("codes")
    @classmethod
    def validate_codes(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(_code(value) for value in values))


class MarketQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[0-9]{6}$")
    name: str | None = None
    price: float
    last_close: float | None = None
    change_percent: float | None = None
    change_amount: float | None = None
    high: float | None = None
    low: float | None = None
    turnover_percent: float | None = None
    pe_ttm: float | None = None
    pe_static: float | None = None
    pb: float | None = None
    market_cap_yi: float | None = None
    float_market_cap_yi: float | None = None
    limit_up: float | None = None
    limit_down: float | None = None


class MarketQuoteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quotes: list[MarketQuote] = Field(min_length=1, max_length=20)
    source: str = "Tencent quote"
    as_of: datetime
    missing_symbols: list[str] = Field(default_factory=list)


class MarketValuationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return _code(value)


class MarketValuationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[0-9]{6}$")
    name: str | None = None
    price: float
    market_cap_yi: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    forecast_year: int
    next_forecast_year: int
    eps_forecast: float | None = None
    eps_next_forecast: float | None = None
    forward_pe: float | None = None
    eps_cagr_percent: float | None = None
    peg: float | None = None
    analyst_count: int | None = None
    source: str = "Tencent quote + AkShare stock_profit_forecast_ths"
    as_of: datetime
    missing_fields: list[str] = Field(default_factory=list)


class MarketFinancialsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return _code(value)


class MarketFinancialsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[0-9]{6}$")
    report_period: str
    revenue: float | None = None
    revenue_yoy_percent: float | None = None
    net_profit: float | None = None
    net_profit_yoy_percent: float | None = None
    eps: float | None = None
    bvps: float | None = None
    roe_percent: float | None = None
    gross_margin_percent: float | None = None
    net_margin_percent: float | None = None
    operating_cash_flow_per_share: float | None = None
    source: str = "AkShare stock_financial_abstract_ths"
    as_of: datetime
    missing_fields: list[str] = Field(default_factory=list)


class MarketDataProvider(Protocol):
    async def quote(self, codes: list[str]) -> MarketQuoteOutput: ...

    async def valuation(self, symbol: str) -> MarketValuationOutput: ...

    async def financials(self, symbol: str) -> MarketFinancialsOutput: ...


def _prefix(symbol: str) -> str:
    if symbol.startswith("6"):
        return "sh"
    if symbol.startswith(("4", "8")):
        return "bj"
    return "sz"


def _fetch_tencent_quote(codes: list[str]) -> dict[str, dict[str, Any]]:
    symbols = [f"{_prefix(code)}{code}" for code in codes]
    request = urllib.request.Request(
        "https://qt.gtimg.cn/q=" + ",".join(symbols),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("gbk", errors="replace")
    except Exception as error:
        raise MarketDataUnavailableError("market_data_unavailable") from error

    return _parse_tencent_quote(body)


def _parse_tencent_quote(body: str) -> dict[str, dict[str, Any]]:
    """Parse Tencent's tilde-delimited quote response without network access."""
    parsed: dict[str, dict[str, Any]] = {}
    for line in body.strip().split(";"):
        if "=" not in line or '"' not in line:
            continue
        key = line.split("=", 1)[0].split("_")[-1]
        values = line.split('"', 2)[1].split("~")
        if len(values) < 53 or len(key) < 8:
            continue
        symbol = key[2:]
        parsed[symbol] = {
            "name": values[1] or None,
            "price": _number(values[3]),
            "last_close": _number(values[4]),
            "change_amount": _number(values[31]),
            "change_percent": _number(values[32]),
            "high": _number(values[33]),
            "low": _number(values[34]),
            "turnover_percent": _number(values[38]),
            "pe_ttm": _number(values[39]),
            "market_cap_yi": _number(values[44]),
            "float_market_cap_yi": _number(values[45]),
            "pb": _number(values[46]),
            "limit_up": _number(values[47]),
            "limit_down": _number(values[48]),
            "pe_static": _number(values[52]),
        }
    return parsed


def _load_profit_forecast(symbol: str) -> list[dict[str, Any]]:
    try:
        import akshare as ak  # type: ignore[import-untyped]

        frame = ak.stock_profit_forecast_ths(symbol=symbol, indicator="预测年报每股收益")
    except Exception as error:
        raise MarketDataUnavailableError("market_data_unavailable") from error
    if frame is None or frame.empty:
        return []
    return frame.to_dict("records")


def _load_financials(symbol: str) -> dict[str, Any]:
    try:
        import akshare as ak  # type: ignore[import-untyped]

        frame = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
    except Exception as error:
        raise MarketDataUnavailableError("market_data_unavailable") from error
    if frame is None or frame.empty:
        raise MarketDataUnavailableError("market_data_unavailable")
    return frame.iloc[-1].to_dict()


def _forecast_value(row: dict[str, Any]) -> float | None:
    return _number(row.get("均值"))


class PublicMarketDataProvider:
    async def quote(self, codes: list[str]) -> MarketQuoteOutput:
        raw = await asyncio.to_thread(_fetch_tencent_quote, codes)
        quotes: list[MarketQuote] = []
        missing: list[str] = []
        for symbol in codes:
            item = raw.get(symbol)
            if not item or item.get("price") is None:
                missing.append(symbol)
                continue
            quotes.append(MarketQuote(symbol=symbol, **item))
        if not quotes:
            raise MarketDataUnavailableError("market_data_unavailable")
        return MarketQuoteOutput(
            quotes=quotes,
            as_of=datetime.now(UTC),
            missing_symbols=missing,
        )

    async def valuation(self, symbol: str) -> MarketValuationOutput:
        quote = (await self.quote([symbol])).quotes[0]
        now = datetime.now(UTC)
        year = now.year
        try:
            rows = await asyncio.to_thread(_load_profit_forecast, symbol)
        except MarketDataUnavailableError:
            # Quote data remains useful when the optional forecast endpoint is
            # unavailable; the missing fields are explicit in the output.
            rows = []
        values: dict[int, float] = {}
        analyst_count: int | None = None
        for row in rows:
            raw_year = str(row.get("年度") or "")
            try:
                forecast_year = int(next(part for part in raw_year.split() if part.isdigit() and len(part) == 4))
            except (StopIteration, ValueError):
                continue
            value = _forecast_value(row)
            if value is not None:
                values[forecast_year] = value
            if analyst_count is None:
                analyst_count = int(_number(row.get("预测机构数")) or 0)
        eps = values.get(year)
        next_eps = values.get(year + 1)
        forward_pe = quote.price / eps if eps and eps > 0 else None
        cagr = (next_eps / eps - 1) * 100 if eps and next_eps and eps > 0 else None
        peg = forward_pe / cagr if forward_pe is not None and cagr and cagr > 0 else None
        missing = [
            field for field, value in (("eps_forecast", eps), ("eps_next_forecast", next_eps)) if value is None
        ]
        return MarketValuationOutput(
            symbol=symbol,
            name=quote.name,
            price=quote.price,
            market_cap_yi=quote.market_cap_yi,
            pe_ttm=quote.pe_ttm,
            pb=quote.pb,
            forecast_year=year,
            next_forecast_year=year + 1,
            eps_forecast=eps,
            eps_next_forecast=next_eps,
            forward_pe=round(forward_pe, 4) if forward_pe is not None else None,
            eps_cagr_percent=round(cagr, 4) if cagr is not None else None,
            peg=round(peg, 4) if peg is not None else None,
            analyst_count=analyst_count,
            as_of=now,
            missing_fields=missing,
        )

    async def financials(self, symbol: str) -> MarketFinancialsOutput:
        row = await asyncio.to_thread(_load_financials, symbol)

        def value(key: str) -> float | None:
            return _number(row.get(key))

        fields: dict[str, float | None] = {
            "revenue": value("营业总收入"),
            "revenue_yoy_percent": value("营业总收入同比增长率"),
            "net_profit": value("净利润"),
            "net_profit_yoy_percent": value("净利润同比增长率"),
            "eps": value("基本每股收益"),
            "bvps": value("每股净资产"),
            "roe_percent": value("净资产收益率"),
            "gross_margin_percent": value("销售毛利率"),
            "net_margin_percent": value("销售净利率"),
            "operating_cash_flow_per_share": value("每股经营现金流"),
        }
        missing = [name for name, item in fields.items() if item is None]
        period = str(row.get("报告期") or "").strip()
        if not period:
            raise MarketDataUnavailableError("market_data_schema_changed")
        return MarketFinancialsOutput(
            symbol=symbol,
            report_period=period,
            as_of=datetime.now(UTC),
            missing_fields=missing,
            revenue=fields["revenue"],
            revenue_yoy_percent=fields["revenue_yoy_percent"],
            net_profit=fields["net_profit"],
            net_profit_yoy_percent=fields["net_profit_yoy_percent"],
            eps=fields["eps"],
            bvps=fields["bvps"],
            roe_percent=fields["roe_percent"],
            gross_margin_percent=fields["gross_margin_percent"],
            net_margin_percent=fields["net_margin_percent"],
            operating_cash_flow_per_share=fields["operating_cash_flow_per_share"],
        )


_provider: MarketDataProvider = PublicMarketDataProvider()


def get_market_data_provider() -> MarketDataProvider:
    return _provider


async def quote_tool(payload: MarketQuoteInput) -> MarketQuoteOutput:
    return await get_market_data_provider().quote(payload.codes)


async def valuation_tool(payload: MarketValuationInput) -> MarketValuationOutput:
    return await get_market_data_provider().valuation(payload.symbol)


async def financials_tool(payload: MarketFinancialsInput) -> MarketFinancialsOutput:
    return await get_market_data_provider().financials(payload.symbol)
