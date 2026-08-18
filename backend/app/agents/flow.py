from typing import Protocol

from backend.app.agents.analyst import ResearchAnalyst
from backend.app.agents.reviewer import EvidenceReviewer
from backend.app.agents.schemas import (
    Citation,
    FlowOutcome,
    FlowState,
    ResearchRequest,
    ReviewDecision,
    ReviewVerdict,
)
from backend.app.agents.validators import EvidenceValidator, ResearchValidator


class FlowObserver(Protocol):
    """Receives a minimal audit trail; draft and evidence text never leave the flow."""

    async def on_stage(self, role: str, status: str, payload: dict[str, object]) -> None: ...


class ControlledResearchFlow:
    """Fixed Analyst -> Validator -> Reviewer flow with one revision at most."""

    def __init__(
        self,
        analyst: ResearchAnalyst,
        reviewer: EvidenceReviewer,
        validator: ResearchValidator | None = None,
        max_revisions: int = 1,
        observer: FlowObserver | None = None,
    ) -> None:
        self.validator = validator or EvidenceValidator()
        if analyst.allow_delegation or reviewer.allow_delegation or self.validator.allow_delegation:
            raise ValueError("delegation must remain disabled for all agents")
        if max_revisions != 1:
            raise ValueError("P2 flow permits exactly one targeted revision")
        self.analyst = analyst
        self.reviewer = reviewer
        self.max_revisions = max_revisions
        self.observer = observer

    async def run(self, request: ResearchRequest) -> FlowOutcome:
        state = FlowState(request=request)
        revision_notes: list[str] = []
        while True:
            await self._notify("analyst", "started", {"revision": state.revision_count})
            state.draft = await self.analyst.produce_draft(request.model_copy(deep=True), revision_notes)
            await self._notify(
                "analyst", "completed", {"claim_count": len(state.draft.claims)}
            )
            await self._notify("validator", "started", {"revision": state.revision_count})
            state.validation = self.validator.validate(state.draft, request.evidence)
            await self._notify(
                "validator",
                "completed",
                {"passed": state.validation.passed, "error_count": len(state.validation.errors)},
            )
            if not state.validation.passed:
                await self._notify("reviewer", "skipped", {"reason": "validator_rejected"})
                return FlowOutcome(
                    draft=state.draft,
                    validation=state.validation,
                    review=None,
                    revision_count=state.revision_count,
                    verdict=ReviewVerdict.REJECT,
                )

            await self._notify("reviewer", "started", {"revision": state.revision_count})
            state.review = await self.reviewer.review(
                state.draft.model_copy(deep=True), list(request.evidence)
            )
            if not self._review_targets_are_known(state.review, request.evidence):
                await self._notify("reviewer", "completed", {"verdict": ReviewVerdict.REJECT.value})
                return self._outcome(state, ReviewVerdict.REJECT)
            await self._notify("reviewer", "completed", {"verdict": state.review.verdict.value})
            if state.review.verdict is not ReviewVerdict.REVISE:
                return self._outcome(state, state.review.verdict)
            if state.revision_count >= self.max_revisions:
                await self._notify("flow", "human_review", {"reason": "revision_limit_reached"})
                return self._outcome(state, ReviewVerdict.HUMAN_REVIEW)
            state.revision_count += 1
            revision_notes = list(state.review.revision_notes)
            await self._notify("flow", "revision_scheduled", {"revision": state.revision_count})

    async def _notify(self, role: str, status: str, payload: dict[str, object]) -> None:
        if self.observer is not None:
            await self.observer.on_stage(role, status, payload)

    @staticmethod
    def _review_targets_are_known(review: ReviewDecision, evidence: list[Citation]) -> bool:
        # `ReviewDecision` schema makes target presence mandatory for approve/revise;
        # this guards the remaining cross-agent boundary: targets must refer to evidence.
        evidence_ids = {citation.id for citation in evidence}
        return set(review.claim_citation_ids).issubset(evidence_ids)

    @staticmethod
    def _outcome(state: FlowState, verdict: ReviewVerdict) -> FlowOutcome:
        assert state.validation is not None
        return FlowOutcome(
            draft=state.draft,
            validation=state.validation,
            review=state.review,
            revision_count=state.revision_count,
            verdict=verdict,
        )
