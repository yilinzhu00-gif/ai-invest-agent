"""Bounded public A-share daily-price snapshot used by a research run.

The provider is deliberately a read-only snapshot: it supplies recent observed
prices, not a forecast or an investment recommendation.  The network call is
kept behind one async function so tests can replace it without touching AkShare.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Any

from pydantic import BaseModel, Field, field_validator

_MAX_PROVIDER_ATTEMPTS = 3


class MarketSnapshotInput(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")


class DailyClose(BaseModel):
    date: date
    close: float

    @field_validator("close")
    @classmethod
    def require_finite_close(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("close must be finite")
        return value


class MarketSnapshotOutput(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")
    as_of_date: date
    close: float
    change_percent: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    turnover: float | None = None
    period_change_percent: float | None = None
    recent_closes: list[DailyClose] = Field(min_length=1, max_length=6)
    source: str = "AkShare stock_zh_a_hist (Eastmoney)"

    @field_validator("close", "change_percent", "high", "low", "volume", "turnover", "period_change_percent")
    @classmethod
    def require_finite_optional_number(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("market snapshot numbers must be finite")
        return value


class MarketSnapshotUnavailableError(RuntimeError):
    """The public source returned no usable recent daily data."""


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _load_history(symbol: str) -> Any:
    """Load a small, unadjusted recent window from the installed AkShare client."""
    import akshare as ak  # type: ignore[import-untyped]

    today = datetime.now(UTC).date()
    return ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=(today - timedelta(days=21)).strftime("%Y%m%d"),
        end_date=today.strftime("%Y%m%d"),
        adjust="",
        timeout=10,
    )


def _snapshot_from_history(symbol: str, history: Any) -> MarketSnapshotOutput:
    if history is None or history.empty:
        raise MarketSnapshotUnavailableError("market_data_unavailable")
    required = {"日期", "收盘"}
    if not required.issubset(history.columns):
        raise MarketSnapshotUnavailableError("market_data_schema_changed")

    rows = history.tail(6)
    recent_closes: list[DailyClose] = []
    for _, row in rows.iterrows():
        close = _finite_number(row["收盘"])
        if close is None:
            continue
        as_of = row["日期"]
        parsed_date = as_of.date() if hasattr(as_of, "date") else date.fromisoformat(str(as_of))
        recent_closes.append(DailyClose(date=parsed_date, close=close))
    if not recent_closes:
        raise MarketSnapshotUnavailableError("market_data_unavailable")

    latest = rows.iloc[-1]
    close = _finite_number(latest["收盘"])
    if close is None:
        raise MarketSnapshotUnavailableError("market_data_unavailable")
    first_close = recent_closes[0].close
    period_change = None if first_close == 0 else round((close / first_close - 1) * 100, 2)
    latest_date = recent_closes[-1].date
    return MarketSnapshotOutput(
        symbol=symbol,
        as_of_date=latest_date,
        close=close,
        change_percent=_finite_number(latest.get("涨跌幅")),
        high=_finite_number(latest.get("最高")),
        low=_finite_number(latest.get("最低")),
        volume=_finite_number(latest.get("成交量")),
        turnover=_finite_number(latest.get("成交额")),
        period_change_percent=period_change,
        recent_closes=recent_closes,
    )


async def fetch_market_snapshot(symbol: str) -> MarketSnapshotOutput:
    """Return an observed snapshot after bounded retries, or a typed unavailable error."""
    last_error: Exception | None = None
    for attempt in range(_MAX_PROVIDER_ATTEMPTS):
        try:
            history = await asyncio.to_thread(_load_history, symbol)
            return _snapshot_from_history(symbol, history)
        except MarketSnapshotUnavailableError:
            raise
        except Exception as error:  # noqa: BLE001 - provider errors must not leak into research output.
            last_error = error
            if attempt + 1 < _MAX_PROVIDER_ATTEMPTS:
                await asyncio.sleep(0.25 * (attempt + 1))
    raise MarketSnapshotUnavailableError("market_data_unavailable") from last_error
