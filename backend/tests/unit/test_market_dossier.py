from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.domain.market_dossier import MarketDossierInput, build_market_dossier
from backend.app.tools import market_data
from backend.app.tools.market_registry import build_market_tool_registry
from backend.app.tools.policy import ToolPrincipal


class PartialProvider:
    async def quote(self, codes: list[str]) -> market_data.MarketQuoteOutput:
        return market_data.MarketQuoteOutput(
            quotes=[market_data.MarketQuote(symbol=codes[0], price=10.0)],
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )

    async def valuation(self, symbol: str) -> market_data.MarketValuationOutput:
        return market_data.MarketValuationOutput(
            symbol=symbol,
            price=10.0,
            forecast_year=2026,
            next_forecast_year=2027,
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
            missing_fields=["eps_forecast", "eps_next_forecast"],
        )

    async def financials(self, symbol: str) -> market_data.MarketFinancialsOutput:
        return market_data.MarketFinancialsOutput(
            symbol=symbol,
            report_period="2026-06-30",
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )


class UnavailableProvider(PartialProvider):
    async def quote(self, codes: list[str]) -> market_data.MarketQuoteOutput:
        raise market_data.MarketDataUnavailableError("market_data_unavailable")

    async def valuation(self, symbol: str) -> market_data.MarketValuationOutput:
        raise market_data.MarketDataUnavailableError("market_data_unavailable")

    async def financials(self, symbol: str) -> market_data.MarketFinancialsOutput:
        raise market_data.MarketDataUnavailableError("market_data_unavailable")


@pytest.mark.asyncio
async def test_dossier_runs_fixed_sections_and_distinguishes_partial_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(market_data, "_provider", PartialProvider())

    dossier = await build_market_dossier(
        registry=build_market_tool_registry(),
        principal=ToolPrincipal("workspace-1", frozenset({"tools:market:read"})),
        symbol="600519",
    )

    assert dossier.status == "partial"
    assert [section.key for section in dossier.sections] == ["quote", "valuation", "financials"]
    assert dossier.sections[0].status == "ready"
    assert dossier.sections[1].status == "partial"
    assert dossier.sections[1].missing_fields == ["eps_forecast", "eps_next_forecast"]
    assert dossier.sections[2].status == "ready"
    assert dossier.missing_sections == []


@pytest.mark.asyncio
async def test_dossier_preserves_provider_unavailability_without_fabricating_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(market_data, "_provider", UnavailableProvider())

    dossier = await build_market_dossier(
        registry=build_market_tool_registry(),
        principal=ToolPrincipal("workspace-1", frozenset({"tools:market:read"})),
        symbol="600519",
    )

    assert dossier.status == "unavailable"
    assert dossier.missing_sections == ["quote", "valuation", "financials"]
    assert all(section.data is None for section in dossier.sections)
    assert all(section.error_code == "market_data_unavailable" for section in dossier.sections)


def test_dossier_input_is_strict() -> None:
    with pytest.raises(ValidationError):
        MarketDossierInput(symbol="ABC123")
    with pytest.raises(ValidationError):
        MarketDossierInput(symbol="600519", unexpected=True)
