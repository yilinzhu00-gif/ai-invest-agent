from typing import Protocol

from backend.app.agents.schemas import ResearchDraft, ResearchRequest


class ResearchAnalyst(Protocol):
    """The analyst sees request/evidence and only returns a structured draft."""

    allow_delegation: bool

    async def produce_draft(
        self, request: ResearchRequest, revision_notes: list[str]
    ) -> ResearchDraft: ...
