from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.tools import market_data


class FakeProvider:
    async def quote(self, codes: list[str]) -> market_data.MarketQuoteOutput:
        return market_data.MarketQuoteOutput(
            quotes=[
                market_data.MarketQuote(
                    symbol=codes[0], name="测试公司", price=10.0, pe_ttm=20.0, pb=2.0
                )
            ],
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )

    async def valuation(self, symbol: str) -> market_data.MarketValuationOutput:
        return market_data.MarketValuationOutput(
            symbol=symbol,
            price=10.0,
            forecast_year=2026,
            next_forecast_year=2027,
            eps_forecast=1.0,
            eps_next_forecast=1.2,
            forward_pe=10.0,
            eps_cagr_percent=20.0,
            peg=0.5,
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )

    async def financials(self, symbol: str) -> market_data.MarketFinancialsOutput:
        return market_data.MarketFinancialsOutput(
            symbol=symbol,
            report_period="2026-06-30",
            revenue=100.0,
            revenue_yoy_percent=10.0,
            net_profit=20.0,
            roe_percent=15.0,
            as_of=datetime(2026, 8, 21, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_typed_tools_delegate_to_provider_and_preserve_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(market_data, "_provider", FakeProvider())

    quote = await market_data.quote_tool(market_data.MarketQuoteInput(codes=["600519", "600519"]))
    valuation = await market_data.valuation_tool(market_data.MarketValuationInput(symbol="600519"))
    financials = await market_data.financials_tool(market_data.MarketFinancialsInput(symbol="600519"))

    assert [item.symbol for item in quote.quotes] == ["600519"]
    assert valuation.forward_pe == 10.0
    assert financials.report_period == "2026-06-30"


@pytest.mark.parametrize("value", ["ABC123", "６００５１９", "60051", "6005190"])
def test_market_inputs_reject_non_ascii_six_digit_codes(value: str) -> None:
    with pytest.raises(ValidationError):
        market_data.MarketValuationInput(symbol=value)


def test_quote_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        market_data.MarketQuoteInput(codes=["600519"], unexpected=True)


def test_tencent_parser_maps_public_quote_fields() -> None:
    body = (
        'v_sh600519="1~贵州茅台~600519~1472.5~1460~1450~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~12.5~0.86~1480~1462~0~0~1000~1.2~20~0~0~0~0~0~0~0~0~0~0~0~0~2.0~0";'
    )

    parsed = market_data._parse_tencent_quote(body)

    assert parsed["600519"]["name"] == "贵州茅台"
    assert parsed["600519"]["price"] == 1472.5
    assert parsed["600519"]["change_percent"] == 0.86


def test_tencent_provider_hides_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object, **__: object) -> object:
        raise ConnectionError("provider details must not escape")

    monkeypatch.setattr(market_data.urllib.request, "urlopen", fail)

    with pytest.raises(market_data.MarketDataUnavailableError, match="market_data_unavailable"):
        market_data._fetch_tencent_quote(["600519"])
