from datetime import UTC, datetime

import pytest

from backend.app.agents.concrete import RunUsageLedger
from backend.app.domain.market_debate import (
    MarketDebateOutputError,
    run_market_debate,
)
from backend.app.domain.market_dossier import MarketDossier, MarketDossierSection
from backend.app.models.schemas import ModelResponse, ModelUsage


def _dossier() -> MarketDossier:
    return MarketDossier(
        symbol="600519",
        generated_at=datetime(2026, 8, 21, tzinfo=UTC),
        status="ready",
        sections=[
            MarketDossierSection(
                key="quote",
                title="实时行情",
                tool="market.quote",
                status="ready",
                data={"quotes": [{"symbol": "600519", "price": 10.0}]},
            ),
            MarketDossierSection(
                key="valuation",
                title="估值与一致预期",
                tool="market.valuation",
                status="ready",
                data={"symbol": "600519", "price": 10.0, "forecast_year": 2026},
            ),
            MarketDossierSection(
                key="financials",
                title="最新报告期财务指标",
                tool="market.financials",
                status="ready",
                data={"symbol": "600519", "report_period": "2026-06-30"},
            ),
        ],
    )


class FakeGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests = []

    async def complete(self, request: object, timeout_seconds: float) -> ModelResponse:
        del timeout_seconds
        self.requests.append(request)
        return ModelResponse(
            text=self.responses.pop(0),
            usage=ModelUsage(provider="fake", model="fake", input_tokens=10, output_tokens=5),
        )


def _valid_responses() -> list[str]:
    return [
        '{"role":"bull","core_thesis":"底稿中的价格与预期数据形成支持。","claims":[{"text":"价格观测为 10。","evidence_refs":["quote.quotes[0].price"]}]}',
        '{"role":"bear","core_thesis":"底稿仍存在财务期间和估值缺口。","claims":[{"text":"最新报告期需要继续核实。","evidence_refs":["financials.report_period"]}]}',
        '{"consensus":["双方都依赖同一份底稿"],"disagreements":["对估值数据完整性的解释不同"],"verification_checklist":["补充下一报告期财务数据"],"data_gaps":["缺少更长历史序列"]}',
    ]


@pytest.mark.asyncio
async def test_market_debate_uses_same_dossier_and_shared_budget() -> None:
    gateway = FakeGateway(_valid_responses())
    ledger = RunUsageLedger(max_tokens=100, max_cost_microusd=100)

    result = await run_market_debate(
        dossier=_dossier(), gateway=gateway, model="fake-model", timeout_seconds=5, ledger=ledger
    )

    assert result.symbol == "600519"
    assert result.bull.role == "bull"
    assert result.bear.role == "bear"
    assert len(gateway.requests) == 3
    assert all(request.messages[1].content.find('"symbol": "600519"') >= 0 for request in gateway.requests)
    assert ledger._input_tokens == 30
    assert ledger._output_tokens == 15


@pytest.mark.asyncio
async def test_market_debate_rejects_actionable_model_output() -> None:
    responses = _valid_responses()
    responses[0] = (
        '{"role":"bull","core_thesis":"建议买入。","claims":'
        '[{"text":"价格观测为 10。","evidence_refs":["quote.quotes[0].price"]}]}'
    )
    with pytest.raises(MarketDebateOutputError, match="actionable advice"):
        await run_market_debate(
            dossier=_dossier(),
            gateway=FakeGateway(responses),
            model="fake-model",
            timeout_seconds=5,
            ledger=RunUsageLedger(max_tokens=100, max_cost_microusd=100),
        )


def test_market_debate_input_is_strict() -> None:
    from pydantic import ValidationError

    from backend.app.domain.market_debate import MarketDebateInput

    with pytest.raises(ValidationError):
        MarketDebateInput(symbol="600519", extra="nope")
