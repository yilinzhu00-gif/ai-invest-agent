"""LLM service seam.

Provider construction stays in ``agents.factory``; this module exposes the
small interface used by higher-level services and keeps credentials out of
domain objects.
"""

from typing import Protocol


class LLMService(Protocol):
    async def complete(self, *, model: str, prompt: str) -> str: ...

