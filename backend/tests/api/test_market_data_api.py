from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.tools import market_data


class FakeProvider:
    async def quote(self, codes: list[str]) -> market_data.MarketQuoteOutput:
        return market_data.MarketQuoteOutput(
            quotes=[market_data.MarketQuote(symbol=codes[0], price=10.0, name="测试公司")],
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )

    async def valuation(self, symbol: str) -> market_data.MarketValuationOutput:
        return market_data.MarketValuationOutput(
            symbol=symbol,
            price=10.0,
            forecast_year=2026,
            next_forecast_year=2027,
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )

    async def financials(self, symbol: str) -> market_data.MarketFinancialsOutput:
        return market_data.MarketFinancialsOutput(
            symbol=symbol,
            report_period="2026-06-30",
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )


DEMO_HEADERS = {
    "X-Development-Principal-ID": "user-1",
    "X-Development-Workspace-ID": "workspace-1",
}


def test_market_data_endpoints_use_the_registry_and_return_typed_data(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(market_data, "_provider", FakeProvider())
    with TestClient(create_app()) as client:
        quote = client.post("/api/v1/market/quote", json={"codes": ["600519"]}, headers=DEMO_HEADERS)
        valuation = client.post(
            "/api/v1/market/valuation", json={"symbol": "600519"}, headers=DEMO_HEADERS
        )
        financials = client.post(
            "/api/v1/market/financials", json={"symbol": "600519"}, headers=DEMO_HEADERS
        )

    assert quote.status_code == 200
    assert quote.json()["quotes"][0]["symbol"] == "600519"
    assert valuation.status_code == 200
    assert valuation.json()["forecast_year"] == 2026
    assert financials.status_code == 200
    assert financials.json()["report_period"] == "2026-06-30"


def test_market_data_validation_is_returned_as_the_standard_error_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/market/quote",
            json={"codes": ["ABC123"]},
            headers=DEMO_HEADERS | {"X-Correlation-ID": "market-validate-1"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "validation_error"},
        "correlation_id": "market-validate-1",
    }


def test_market_dossier_endpoint_returns_fixed_sections(monkeypatch: Any) -> None:
    monkeypatch.setattr(market_data, "_provider", FakeProvider())

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/market/dossier", json={"symbol": "600519"}, headers=DEMO_HEADERS
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert [section["key"] for section in body["sections"]] == [
        "quote",
        "valuation",
        "financials",
    ]


def test_market_debate_requires_an_explicit_model_runtime(monkeypatch: Any) -> None:
    monkeypatch.setattr(market_data, "_provider", FakeProvider())

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/market/debate", json={"symbol": "600519"}, headers=DEMO_HEADERS
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "http_error"
