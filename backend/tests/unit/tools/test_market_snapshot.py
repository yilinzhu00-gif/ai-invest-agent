from datetime import date

import pandas as pd
import pytest

from backend.app.tools import market_snapshot


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-08-10", "2026-08-11", "2026-08-12"],
            "收盘": [1450.0, 1460.0, 1472.5],
            "涨跌幅": [0.5, 0.69, 0.86],
            "最高": [1460.0, 1470.0, 1480.0],
            "最低": [1440.0, 1450.0, 1462.0],
            "成交量": [100, 110, 120],
            "成交额": [1000, 1100, 1200],
        }
    )


def test_snapshot_maps_recent_akshare_history_without_making_a_forecast() -> None:
    snapshot = market_snapshot._snapshot_from_history("600519", _history())

    assert snapshot.symbol == "600519"
    assert snapshot.as_of_date == date(2026, 8, 12)
    assert snapshot.close == 1472.5
    assert snapshot.period_change_percent == 1.55
    assert [item.close for item in snapshot.recent_closes] == [1450.0, 1460.0, 1472.5]
    assert snapshot.source == "AkShare stock_zh_a_hist (Eastmoney)"


@pytest.mark.asyncio
async def test_snapshot_wraps_provider_failure_in_a_safe_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_: str) -> pd.DataFrame:
        raise RuntimeError("provider details must not reach the user")

    monkeypatch.setattr(market_snapshot, "_load_history", unavailable)

    with pytest.raises(market_snapshot.MarketSnapshotUnavailableError, match="market_data_unavailable"):
        await market_snapshot.fetch_market_snapshot("600519")


@pytest.mark.asyncio
async def test_snapshot_retries_a_transient_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def flaky(_: str) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("temporary upstream disconnect")
        return _history()

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr(market_snapshot, "_load_history", flaky)
    monkeypatch.setattr(market_snapshot.asyncio, "sleep", no_wait)

    snapshot = await market_snapshot.fetch_market_snapshot("600519")

    assert snapshot.close == 1472.5
    assert calls == 2
