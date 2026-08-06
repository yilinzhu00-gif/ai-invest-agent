"""Rollback adapter for the pre-gateway local LLM module."""

from backend.app.models.schemas import ModelRequest, ModelResponse, ModelUsage


class LegacyModelAdapter:
    """Keep legacy chat available while new Agent paths migrate to ModelGateway."""

    async def complete(self, request: ModelRequest, timeout_seconds: float) -> ModelResponse:
        del timeout_seconds
        from legacy.llm import chat

        system_messages = [message.content for message in request.messages if message.role == "system"]
        user_messages = [message.content for message in request.messages if message.role == "user"]
        text = chat(
            "\n".join(user_messages),
            system="\n".join(system_messages) or "你是一名严谨的金融投研助手。",
            temperature=request.temperature,
        )
        return ModelResponse(
            text=text,
            usage=ModelUsage(provider="legacy", model=request.model),
        )
