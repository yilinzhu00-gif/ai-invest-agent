"""Structured financial-report tool for public-company research."""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.tools.stock_tool import (
    StockDataUnavailableError,
    _number,
    _request_json,
    _symbol,
    _value,
)


class FinancialReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    period: str = Field(default="annual", pattern=r"^(annual|quarterly)$")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return _symbol(value)


class FinancialReportOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str | None = None
    report_period: str | None = None
    revenue: float | None = None
    profit: float | None = None
    gross_profit: float | None = None
    gross_margin: float | None = None
    growth_rate: float | None = None
    eps: float | None = None
    operating_cash_flow: float | None = None
    source: str = "Yahoo Finance public quoteSummary/timeseries endpoints"
    as_of: datetime
    missing_fields: list[str] = Field(default_factory=list)


class FinancialDataProvider(Protocol):
    async def get_report(self, payload: FinancialReportInput) -> FinancialReportOutput: ...


def _timeseries_url(symbol: str, period: str) -> str:
    suffix = "annual" if period == "annual" else "quarterly"
    types = ",".join(
        f"{suffix}{field}"
        for field in ("TotalRevenue", "NetIncome", "GrossProfit", "OperatingCashFlow", "DilutedEPS")
    )
    query = urllib.parse.urlencode({"symbol": symbol, "type": types, "period1": "946684800", "period2": "4102444800"})
    return f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(symbol)}?{query}"


def _latest_timeseries(response: dict[str, Any]) -> tuple[str | None, dict[str, float]]:
    result = response.get("timeseries", {}).get("result") or []
    period: str | None = None
    values: dict[str, float] = {}
    for series in result:
        if not isinstance(series, dict):
            continue
        name = str(series.get("meta", {}).get("type", [""])[0]) if series.get("meta") else ""
        rows = series.get(name) or series.get(str(series.get("meta", {}).get("type", [""])[0])) or []
        if not rows:
            # Yahoo sometimes uses the type as the only non-meta key.
            rows = next((value for key, value in series.items() if key != "meta" and isinstance(value, list)), [])
        if not rows or not isinstance(rows[-1], dict):
            continue
        row = rows[-1]
        period = period or row.get("asOfDate")
        value = _number(_value(row.get("reportedValue")))
        if value is not None:
            values[name.removeprefix("annual").removeprefix("quarterly")] = value
    return period, values


class YahooFinancialProvider:
    async def get_report(self, payload: FinancialReportInput) -> FinancialReportOutput:
        response = await asyncio.to_thread(_request_json, _timeseries_url(payload.symbol, payload.period))
        period, values = _latest_timeseries(response)
        # A quoteSummary fallback supplies the company name and a few ratios;
        # missing fundamentals remain explicit rather than fabricated.
        name: str | None = None
        ratios: dict[str, Any] = {}
        try:
            summary = await asyncio.to_thread(
                _request_json,
                "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                f"{urllib.parse.quote(payload.symbol)}?modules=price,defaultKeyStatistics,financialData",
            )
            result = summary.get("quoteSummary", {}).get("result") or []
            if result:
                price_section = result[0].get("price", {})
                if isinstance(price_section, dict):
                    name = _value(price_section.get("longName"))
                for section_name, section in result[0].items():
                    if isinstance(section, dict) and "raw" in section:
                        ratios[section_name] = section
                    elif isinstance(section, dict):
                        ratios.update(section)
        except StockDataUnavailableError:
            pass
        revenue = values.get("TotalRevenue")
        profit = values.get("NetIncome")
        gross_profit = values.get("GrossProfit")
        gross_margin = gross_profit / revenue * 100 if gross_profit is not None and revenue else None
        growth = _number(_value(ratios.get("revenueGrowth")))
        # Yahoo's growth ratio is decimal; expose the user-facing percentage.
        if growth is not None and abs(growth) <= 2:
            growth *= 100
        fields = {
            "revenue": revenue,
            "profit": profit,
            "gross_margin": gross_margin,
            "growth_rate": growth,
            "eps": values.get("DilutedEPS"),
            "operating_cash_flow": values.get("OperatingCashFlow"),
        }
        return FinancialReportOutput(
            symbol=payload.symbol,
            name=name,
            report_period=period,
            revenue=revenue,
            profit=profit,
            gross_margin=gross_margin,
            growth_rate=growth,
            eps=values.get("DilutedEPS"),
            operating_cash_flow=values.get("OperatingCashFlow"),
            gross_profit=gross_profit,
            as_of=datetime.now(UTC),
            missing_fields=[name for name, value in fields.items() if value is None],
        )


_provider: FinancialDataProvider = YahooFinancialProvider()


def get_financial_data_provider() -> FinancialDataProvider:
    return _provider


async def financial_tool(payload: FinancialReportInput) -> FinancialReportOutput:
    return await get_financial_data_provider().get_report(payload)


async def get_financial_report(symbol: str, *, period: str = "annual") -> dict[str, Any]:
    result = await financial_tool(FinancialReportInput(symbol=symbol, period=period))
    return result.model_dump(mode="json")
