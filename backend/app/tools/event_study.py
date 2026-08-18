"""Recomputable, non-causal market-reaction calculations around an announcement.

The module uses only observed daily data. It aligns the event to the first date
on which the stock and both chosen benchmarks have an observation, and reports
incomplete observations instead of filling them forward.
"""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from statistics import stdev
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CSI_300_SYMBOL = "000300"
DEFAULT_EVENT_WINDOW = 20
_PROVIDER_ATTEMPTS = 3


class MarketReactionUnavailableError(RuntimeError):
    """There is not enough observed data for the requested event window."""


class MarketReactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcement_date: date
    industry_index_symbol: str = Field(pattern=r"^[0-9]{6}$")
    industry_index_name: str = Field(min_length=1, max_length=100)
    event_window: int = Field(default=DEFAULT_EVENT_WINDOW, ge=1, le=60)


class Benchmark(BaseModel):
    name: str
    symbol: str
    source: str


class EventMarketDate(BaseModel):
    event_offset: int
    market_date: date
    stock_close: float
    stock_volume: float | None
    csi_300_close: float
    industry_index_close: float


class WindowReturn(BaseModel):
    start_offset: int
    end_offset: int
    start_date: date
    end_date: date
    stock_start_close: float
    stock_end_close: float
    csi_300_start_close: float
    csi_300_end_close: float
    industry_start_close: float
    industry_end_close: float
    stock_return_percent: float
    csi_300_return_percent: float
    industry_return_percent: float
    excess_vs_csi_300_percentage_points: float
    excess_vs_industry_percentage_points: float


class BeforeAfterChange(BaseModel):
    before_date: date
    event_date: date
    after_date: date
    before_to_event_return_percent: float
    event_to_after_return_percent: float


class VolumeVolatilityChange(BaseModel):
    pre_period: str
    post_period: str
    pre_average_volume: float | None
    post_average_volume: float | None
    volume_change_percent: float | None
    pre_daily_volatility_percent: float | None
    post_daily_volatility_percent: float | None
    volatility_change_percentage_points: float | None


class MarketReactionResponse(BaseModel):
    symbol: str
    announcement_date: date
    event_date: date
    event_window: list[int]
    benchmark_indices: list[Benchmark]
    formula: str
    before_after_change: BeforeAfterChange
    window_result: WindowReturn
    volume_volatility_change: VolumeVolatilityChange
    market_dates: list[EventMarketDate]
    missing_trading_dates: list[date]
    missing_trading_dates_definition: str
    source: str
    boundary: str


@dataclass(frozen=True)
class DailyMarketRecord:
    market_date: date
    close: float
    volume: float | None = None


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _records_from_history(history: Any, *, include_volume: bool) -> list[DailyMarketRecord]:
    if history is None or history.empty or not {"日期", "收盘"}.issubset(history.columns):
        raise MarketReactionUnavailableError("market_data_schema_changed")
    records: dict[date, DailyMarketRecord] = {}
    for _, row in history.iterrows():
        market_date = _to_date(row["日期"])
        close = _finite_number(row["收盘"])
        if market_date is None or close is None or close <= 0:
            continue
        volume = _finite_number(row.get("成交量")) if include_volume else None
        records[market_date] = DailyMarketRecord(market_date, close, volume)
    if not records:
        raise MarketReactionUnavailableError("market_data_unavailable")
    return sorted(records.values(), key=lambda record: record.market_date)


def _load_stock_history(symbol: str, start_date: date, end_date: date) -> Any:
    import akshare as ak  # type: ignore[import-untyped]

    return ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust="",
        timeout=10,
    )


def _load_index_history(symbol: str, start_date: date, end_date: date) -> Any:
    import akshare as ak  # type: ignore[import-untyped]

    return ak.index_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
    )


def _percent_return(start_close: float, end_close: float) -> float:
    return round((end_close / start_close - 1) * 100, 6)


def _daily_volatility(records: list[DailyMarketRecord]) -> float | None:
    returns = [
        (current.close / previous.close - 1) * 100
        for previous, current in zip(records, records[1:], strict=False)
    ]
    return round(stdev(returns), 6) if len(returns) >= 2 else None


def _average_volume(records: list[DailyMarketRecord]) -> float | None:
    volumes = [record.volume for record in records if record.volume is not None]
    return round(sum(volumes) / len(volumes), 6) if volumes else None


def _volume_change_percent(pre: float | None, post: float | None) -> float | None:
    if pre is None or post is None or pre == 0:
        return None
    return round((post / pre - 1) * 100, 6)


def _reaction_from_records(
    *,
    symbol: str,
    announcement_date: date,
    industry_index_symbol: str,
    industry_index_name: str,
    event_window: int,
    stock_records: list[DailyMarketRecord],
    csi_300_records: list[DailyMarketRecord],
    industry_records: list[DailyMarketRecord],
) -> MarketReactionResponse:
    stock = {record.market_date: record for record in stock_records}
    csi_300 = {record.market_date: record for record in csi_300_records}
    industry = {record.market_date: record for record in industry_records}
    common_dates = sorted(set(stock) & set(csi_300) & set(industry))
    try:
        event_index = next(i for i, market_date in enumerate(common_dates) if market_date >= announcement_date)
    except StopIteration as error:
        raise MarketReactionUnavailableError("event_date_unavailable") from error
    start_index = event_index - event_window
    end_index = event_index + event_window
    if start_index < 0 or end_index >= len(common_dates):
        raise MarketReactionUnavailableError("event_window_unavailable")

    selected_dates = common_dates[start_index : end_index + 1]
    event_date = common_dates[event_index]
    market_dates = [
        EventMarketDate(
            event_offset=index - event_window,
            market_date=market_date,
            stock_close=stock[market_date].close,
            stock_volume=stock[market_date].volume,
            csi_300_close=csi_300[market_date].close,
            industry_index_close=industry[market_date].close,
        )
        for index, market_date in enumerate(selected_dates)
    ]
    start_date, end_date = selected_dates[0], selected_dates[-1]
    selected_date_set = set(selected_dates)
    missing_trading_dates = sorted(
        market_date
        for market_date in set(stock) | set(csi_300) | set(industry)
        if start_date <= market_date <= end_date and market_date not in selected_date_set
    )
    start_stock, end_stock = stock[start_date].close, stock[end_date].close
    start_csi, end_csi = csi_300[start_date].close, csi_300[end_date].close
    start_industry, end_industry = industry[start_date].close, industry[end_date].close
    stock_return = _percent_return(start_stock, end_stock)
    csi_return = _percent_return(start_csi, end_csi)
    industry_return = _percent_return(start_industry, end_industry)

    previous_date = common_dates[event_index - 1]
    next_date = common_dates[event_index + 1]
    pre_records = [stock[market_date] for market_date in common_dates[start_index:event_index]]
    post_records = [stock[market_date] for market_date in common_dates[event_index : end_index + 1]]
    pre_volume = _average_volume(pre_records)
    post_volume = _average_volume(post_records)
    pre_volatility = _daily_volatility(pre_records)
    post_volatility = _daily_volatility(post_records)
    volatility_change = (
        None
        if pre_volatility is None or post_volatility is None
        else round(post_volatility - pre_volatility, 6)
    )
    return MarketReactionResponse(
        symbol=symbol,
        announcement_date=announcement_date,
        event_date=event_date,
        event_window=[-event_window, event_window],
        benchmark_indices=[
            Benchmark(name="沪深300", symbol=CSI_300_SYMBOL, source="AkShare index_zh_a_hist (Eastmoney)"),
            Benchmark(
                name=industry_index_name,
                symbol=industry_index_symbol,
                source="AkShare index_zh_a_hist (Eastmoney)",
            ),
        ],
        formula="区间收益率(%) = 100 × (期末收盘价 ÷ 期初收盘价 − 1)；超额收益(百分点) = 个股区间收益率 − 基准指数区间收益率。",
        before_after_change=BeforeAfterChange(
            before_date=previous_date,
            event_date=event_date,
            after_date=next_date,
            before_to_event_return_percent=_percent_return(stock[previous_date].close, stock[event_date].close),
            event_to_after_return_percent=_percent_return(stock[event_date].close, stock[next_date].close),
        ),
        window_result=WindowReturn(
            start_offset=-event_window,
            end_offset=event_window,
            start_date=start_date,
            end_date=end_date,
            stock_start_close=start_stock,
            stock_end_close=end_stock,
            csi_300_start_close=start_csi,
            csi_300_end_close=end_csi,
            industry_start_close=start_industry,
            industry_end_close=end_industry,
            stock_return_percent=stock_return,
            csi_300_return_percent=csi_return,
            industry_return_percent=industry_return,
            excess_vs_csi_300_percentage_points=round(stock_return - csi_return, 6),
            excess_vs_industry_percentage_points=round(stock_return - industry_return, 6),
        ),
        volume_volatility_change=VolumeVolatilityChange(
            pre_period=f"[-{event_window}, -1]",
            post_period=f"[0, +{event_window}]",
            pre_average_volume=pre_volume,
            post_average_volume=post_volume,
            volume_change_percent=_volume_change_percent(pre_volume, post_volume),
            pre_daily_volatility_percent=pre_volatility,
            post_daily_volatility_percent=post_volatility,
            volatility_change_percentage_points=volatility_change,
        ),
        market_dates=market_dates,
        missing_trading_dates=missing_trading_dates,
        missing_trading_dates_definition="窗口内至少一条行情序列有观测、但个股、沪深300和行业指数未能同时观测的日期；三者均未开市的自然日不计为缺失。",
        source="个股：AkShare stock_zh_a_hist（不复权）；指数：AkShare index_zh_a_hist（Eastmoney）。",
        boundary="该表只描述公告日前后的同期市场数据和公式计算结果，不将价格、成交量或波动变化归因于本次公告或交易。",
    )


async def fetch_market_reaction(
    *, symbol: str, request: MarketReactionRequest
) -> MarketReactionResponse:
    """Fetch enough surrounding days, retrying transient provider failures only."""
    padding_days = request.event_window * 5 + 30
    start_date = request.announcement_date - timedelta(days=padding_days)
    end_date = request.announcement_date + timedelta(days=padding_days)
    last_error: Exception | None = None
    for attempt in range(_PROVIDER_ATTEMPTS):
        try:
            stock_history, csi_history, industry_history = await asyncio.gather(
                asyncio.to_thread(_load_stock_history, symbol, start_date, end_date),
                asyncio.to_thread(_load_index_history, CSI_300_SYMBOL, start_date, end_date),
                asyncio.to_thread(_load_index_history, request.industry_index_symbol, start_date, end_date),
            )
            return _reaction_from_records(
                symbol=symbol,
                announcement_date=request.announcement_date,
                industry_index_symbol=request.industry_index_symbol,
                industry_index_name=request.industry_index_name,
                event_window=request.event_window,
                stock_records=_records_from_history(stock_history, include_volume=True),
                csi_300_records=_records_from_history(csi_history, include_volume=False),
                industry_records=_records_from_history(industry_history, include_volume=False),
            )
        except MarketReactionUnavailableError:
            raise
        except Exception as error:  # noqa: BLE001 - keep provider details out of the response.
            last_error = error
            if attempt + 1 < _PROVIDER_ATTEMPTS:
                await asyncio.sleep(0.25 * (attempt + 1))
    raise MarketReactionUnavailableError("market_data_unavailable") from last_error
