"""Researcher role adapter.

The concrete evidence-bound flow is still in ``agents.flow``.  This protocol
is intentionally narrow so a LangGraph node, an offline test double, or a
future provider can be substituted without changing the API layer.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from backend.app.agents.schemas import FlowOutcome, ResearchRequest


class Researcher(Protocol):
    async def run(self, request: ResearchRequest) -> FlowOutcome: ...


ResearcherFactory = Callable[[ResearchRequest], Awaitable[FlowOutcome]]

