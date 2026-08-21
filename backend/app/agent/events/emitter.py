"""Small dependency-injection boundary for Agent event emission."""

from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from .event import AgentEvent, AgentEventType


class EventSink(Protocol):
    async def __call__(self, event: AgentEvent) -> None: ...


class AgentEventEmitter:
    """Emit typed events to any async sink (DB, queue, test collector, or log)."""

    def __init__(self, sink: EventSink | Callable[[AgentEvent], Awaitable[None]]) -> None:
        self._sink = sink

    async def emit(
        self,
        event_type: AgentEventType | AgentEvent,
        message: str | None = None,
        *,
        run_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentEvent:
        event = event_type if isinstance(event_type, AgentEvent) else AgentEvent(
            event_type=event_type,
            message=message or "",
            run_id=run_id,
            metadata=dict(metadata or {}),
        )
        await self._sink(event)
        return event


class NoopEventEmitter:
    """Explicit opt-out for pure unit tests that do not need observation."""

    async def emit(
        self,
        event_type: AgentEventType | AgentEvent,
        message: str | None = None,
        *,
        run_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentEvent:
        if isinstance(event_type, AgentEvent):
            return event_type
        return AgentEvent(event_type, message or "", run_id, dict(metadata or {}))
