from typing import Protocol

from backend.app.agents.analyst import ResearchAnalyst
from backend.app.agents.reviewer import EvidenceReviewer
from backend.app.agents.schemas import (
    Citation,
    FlowOutcome,
    FlowState,
    ResearchDraft,
    ResearchRequest,
    ReviewDecision,
    ReviewVerdict,
)
from backend.app.agents.validators import EvidenceValidator, ResearchValidator, validate_draft


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
            await self._notify("numeric_validator", "started", {"revision": state.revision_count})
            state.validation = self.validator.validate(state.draft, request.evidence)
            if request.require_structured_conclusion:
                # Keep a custom Validator's own checks, then add the announcement
                # conclusion contract without allowing the model to bypass it.
                conclusion_validation = validate_draft(
                    state.draft,
                    request.evidence,
                    require_structured_conclusion=True,
                )
                errors = list(dict.fromkeys(
                    [*state.validation.errors, *conclusion_validation.errors]
                ))
                state.validation = state.validation.model_copy(
                    update={"passed": not errors, "errors": errors}
                )
            await self._notify(
                "numeric_validator",
                "completed",
                {"passed": state.validation.passed, "error_count": len(state.validation.errors)},
            )
            if not state.validation.passed:
                await self._notify("reviewer", "skipped", {"reason": "numeric_validator_rejected"})
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
            if not self._review_is_complete(state.review, state.draft, request.evidence):
                await self._notify("reviewer", "completed", {"verdict": ReviewVerdict.HUMAN_REVIEW.value})
                return self._outcome(state, ReviewVerdict.HUMAN_REVIEW)
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
    def _review_is_complete(
        review: ReviewDecision, draft: ResearchDraft, evidence: list[Citation]
    ) -> bool:
        """Require the Reviewer to audit every claim/citation pair explicitly."""
        evidence_ids = {citation.id for citation in evidence}
        if not set(review.claim_citation_ids).issubset(evidence_ids):
            return False
        claims = draft.claims
        expected_pairs = {
            (claim_index, citation_id)
            for claim_index, claim in enumerate(claims)
            for citation_id in claim.citation_ids
        }
        reviewed_pairs = {(item.claim_index, item.citation_id) for item in review.claim_reviews}
        if reviewed_pairs != expected_pairs or len(reviewed_pairs) != len(review.claim_reviews):
            return False
        for checked in review.claim_reviews:
            if checked.citation_id not in evidence_ids:
                return False
            if review.verdict is ReviewVerdict.APPROVE and not checked.supported:
                return False
        return True

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
