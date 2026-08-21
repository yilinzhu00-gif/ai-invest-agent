"""Minimal workspace-scoped memory port used by agents and tests."""

from typing import Protocol


class MemoryStore(Protocol):
    async def get(self, *, workspace_id: str, key: str) -> str | None: ...

    async def put(self, *, workspace_id: str, key: str, value: str) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    async def get(self, *, workspace_id: str, key: str) -> str | None:
        return self._values.get((workspace_id, key))

    async def put(self, *, workspace_id: str, key: str, value: str) -> None:
        self._values[(workspace_id, key)] = value

