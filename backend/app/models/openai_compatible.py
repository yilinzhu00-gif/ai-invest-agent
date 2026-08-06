"""Bounded adapter for OpenAI-compatible synchronous SDK clients."""

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

from backend.app.models.gateway import retryable_provider_error, run_with_retry
from backend.app.models.schemas import ModelRequest, ModelResponse, ModelUsage


@dataclass
class ProviderFailure(Exception):
    status_code: int | None = None
    code: str | None = None


class OpenAICompatibleCompletions(Protocol):
    def create(self, **kwargs: object) -> object: ...


class OpenAICompatibleChat(Protocol):
    completions: OpenAICompatibleCompletions


class OpenAICompatibleClient(Protocol):
    chat: OpenAICompatibleChat


class OpenAICompatibleGateway:
    def __init__(self, client: OpenAICompatibleClient, *, provider: str) -> None:
        self.client = client
        self.provider = provider

    async def complete(self, request: ModelRequest, timeout_seconds: float) -> ModelResponse:
        started_at = time.monotonic()

        def should_retry(error: Exception) -> bool:
            return retryable_provider_error(
                status_code=getattr(error, "status_code", None), error_code=getattr(error, "code", None)
            )

        async def operation() -> object:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=request.model,
                    messages=[message.model_dump() for message in request.messages],
                    temperature=request.temperature,
                ),
                timeout=timeout_seconds,
            )

        response = await run_with_retry(operation, should_retry)
        choices = getattr(response, "choices", [])
        content = getattr(getattr(choices[0], "message", None), "content", None) if choices else None
        if not isinstance(content, str):
            raise ProviderFailure(code="invalid_response")
        raw_usage = getattr(response, "usage", None)
        return ModelResponse(
            text=content,
            usage=ModelUsage(
                provider=self.provider,
                model=str(getattr(response, "model", request.model)),
                input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
                latency_ms=int((time.monotonic() - started_at) * 1000),
            ),
        )
