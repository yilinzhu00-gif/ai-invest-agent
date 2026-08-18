from datetime import date

from backend.app.domain.agent_runs.market_research import (
    market_result_payload,
    market_snapshot_citation,
)
from backend.app.tools.market_snapshot import DailyClose, MarketSnapshotOutput


def _snapshot() -> MarketSnapshotOutput:
    return MarketSnapshotOutput(
        symbol="600519",
        as_of_date=date(2026, 8, 12),
        close=1472.5,
        change_percent=0.86,
        high=1480,
        low=1462,
        volume=120,
        turnover=1200,
        period_change_percent=1.55,
        recent_closes=[
            DailyClose(date=date(2026, 8, 10), close=1450),
            DailyClose(date=date(2026, 8, 12), close=1472.5),
        ],
    )


def test_market_snapshot_is_rendered_as_a_citable_observed_fact() -> None:
    citation = market_snapshot_citation(_snapshot())

    assert citation.id == "market-snapshot-600519-2026-08-12"
    assert citation.source == "AkShare stock_zh_a_hist (Eastmoney)"
    assert "收盘 1472.5" in citation.text
    assert "预测" not in citation.text


def test_result_payload_keeps_the_no_forecast_boundary_for_the_ui() -> None:
    payload = market_result_payload(_snapshot(), "基于已提供证据整理。")

    assert payload["symbol"] == "600519"
    assert payload["snapshot"]["close"] == 1472.5
    assert "不预测未来走势" in payload["boundary"]
