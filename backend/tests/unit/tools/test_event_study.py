from datetime import date, timedelta

import pandas as pd

from backend.app.tools.event_study import (
    MarketReactionRequest,
    _reaction_from_records,
    _records_from_history,
)


def _history(*, include_volume: bool, missing_index: int | None = None) -> pd.DataFrame:
    rows = []
    for index in range(50):
        if index == missing_index:
            continue
        row = {"日期": date(2025, 1, 1) + timedelta(days=index), "收盘": 100 + index}
        if include_volume:
            row["成交量"] = 1000 + index * 10
        rows.append(row)
    return pd.DataFrame(rows)


def test_event_window_uses_common_trading_dates_and_exposes_recomputable_returns() -> None:
    stock = _records_from_history(_history(include_volume=True, missing_index=25), include_volume=True)
    csi = _records_from_history(_history(include_volume=False), include_volume=False)
    industry = _records_from_history(_history(include_volume=False), include_volume=False)

    result = _reaction_from_records(
        symbol="600519",
        announcement_date=date(2025, 1, 26),
        industry_index_symbol="801010",
        industry_index_name="申万行业",
        event_window=20,
        stock_records=stock,
        csi_300_records=csi,
        industry_records=industry,
    )

    assert result.event_date == date(2025, 1, 27)
    assert result.event_window == [-20, 20]
    assert len(result.market_dates) == 41
    assert result.missing_trading_dates == [date(2025, 1, 26)]
    window = result.window_result
    assert (window.start_offset, window.end_offset) == (-20, 20)
    assert window.stock_return_percent == round((window.stock_end_close / window.stock_start_close - 1) * 100, 6)
    assert window.excess_vs_csi_300_percentage_points == round(
        window.stock_return_percent - window.csi_300_return_percent, 6
    )
    assert result.boundary.startswith("该表只描述公告日前后的同期市场数据")


def test_market_reaction_request_rejects_unbounded_or_unknown_fields() -> None:
    request = MarketReactionRequest(
        announcement_date="2025-01-26",
        industry_index_symbol="801010",
        industry_index_name="申万行业",
    )

    assert request.event_window == 20
