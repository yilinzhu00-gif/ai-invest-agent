import pytest

from backend.app.models.openai_compatible import OpenAICompatibleGateway, ProviderFailure
from backend.app.models.schemas import ModelMessage, ModelRequest


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **_: object) -> object:
        self.calls += 1
        if self.calls < 3:
            raise ProviderFailure(status_code=429, code="rate_limit")
        return type(
            "Response",
            (),
            {
                "model": "mock-chat",
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()],
                "usage": None,
            },
        )()


class FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": FakeCompletions()})()


@pytest.mark.asyncio
async def test_openai_compatible_gateway_retries_429_and_normalizes_missing_usage() -> None:
    """Missing usage must not crash accounting, and transient retries stop at the bounded policy."""
    client = FakeClient()
    gateway = OpenAICompatibleGateway(client, provider="mock")

    response = await gateway.complete(
        ModelRequest(model="mock-chat", messages=[ModelMessage(role="user", content="hello")]),
        timeout_seconds=1,
    )

    assert response.text == "ok"
    assert response.usage.input_tokens == 0
    assert response.usage.output_tokens == 0
    assert client.chat.completions.calls == 3
