from typing import Protocol

from backend.app.agents.schemas import Citation, ResearchDraft, ReviewDecision


class EvidenceReviewer(Protocol):
    """The reviewer can decide, but cannot change raw evidence or permissions."""

    allow_delegation: bool

    async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision: ...
