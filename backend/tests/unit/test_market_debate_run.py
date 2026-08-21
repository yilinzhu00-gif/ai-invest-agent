from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.domain.agent_runs.market_debate import execute_market_debate_run
from backend.app.domain.agent_runs.service import DevelopmentPrincipal
from backend.app.domain.market_dossier import MarketDossier
from backend.app.models.schemas import ModelResponse, ModelUsage


def _dossier() -> MarketDossier:
    from backend.tests.unit.test_market_debate import _dossier as build_dossier

    return build_dossier()


class FakeGateway:
    def __init__(self) -> None:
        self.responses = [
            '{"role":"bull","core_thesis":"支持","claims":[{"text":"价格观测","evidence_refs":["quote.price"]}]}',
            '{"role":"bear","core_thesis":"风险","claims":[{"text":"报告期需核实","evidence_refs":["financials.report_period"]}]}',
            '{"consensus":["共享底稿"],"disagreements":["解释不同"],"verification_checklist":["补充数据"],"data_gaps":[]}',
        ]

    async def complete(self, request: object, timeout_seconds: float) -> ModelResponse:
        del request, timeout_seconds
        return ModelResponse(
            text=self.responses.pop(0),
            usage=ModelUsage(provider="fake", model="fake", input_tokens=1, output_tokens=1),
        )


class FakeService:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.messages: list[str] = []

    async def append_event(
        self, run_id: object, principal: object, event_type: str, payload: dict[str, object]
    ) -> None:
        del run_id, principal
        self.events.append((event_type, payload))

    async def record_assistant_message(self, run_id: object, principal: object, content: str) -> None:
        del run_id, principal
        self.messages.append(content)

    async def transition(
        self,
        run_id: object,
        principal: object,
        status: object,
        event_type: str,
        payload: dict[str, object],
    ) -> SimpleNamespace:
        del run_id, principal, status, event_type, payload
        return SimpleNamespace(status="completed")


@pytest.mark.asyncio
async def test_market_debate_run_persists_replayable_role_events(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.domain.agent_runs.market_debate as module

    gateway = FakeGateway()
    monkeypatch.setattr(module, "build_completion_gateway", lambda settings: gateway)
    monkeypatch.setattr(module, "build_market_tool_registry", lambda: object())

    async def fake_dossier(**_: object) -> MarketDossier:
        return _dossier()

    monkeypatch.setattr(module, "build_market_dossier", fake_dossier)
    service = FakeService()
    settings = Settings(
        agent_execution_mode="openai_compatible", model_api_key=SecretStr("test-key")
    )
    run = SimpleNamespace(symbol="600519")
    principal = DevelopmentPrincipal(principal_id="user-1", workspace_id="workspace-1")

    result = await execute_market_debate_run(
        run_id=uuid4(),
        principal=principal,
        run=run,
        service=service,  # type: ignore[arg-type]
        settings=settings,
    )

    assert result == "completed"
    assert [event_type for event_type, _ in service.events] == [
        "debate.dossier",
        "debate.bull",
        "debate.bear",
        "debate.moderator",
        "debate.result",
    ]
    assert service.events[1][1]["role"] == "bull"
    assert service.events[2][1]["role"] == "bear"
    assert service.messages
