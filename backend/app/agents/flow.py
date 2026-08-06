from backend.app.agents.analyst import ResearchAnalyst
from backend.app.agents.reviewer import EvidenceReviewer
from backend.app.agents.schemas import (
    FlowOutcome,
    FlowState,
    ResearchRequest,
    ReviewVerdict,
)
from backend.app.agents.validators import validate_draft


class ControlledResearchFlow:
    """Fixed Analyst -> Validator -> Reviewer flow with one revision at most."""

    def __init__(
        self, analyst: ResearchAnalyst, reviewer: EvidenceReviewer, max_revisions: int = 1
    ) -> None:
        if analyst.allow_delegation or reviewer.allow_delegation:
            raise ValueError("delegation must remain disabled for both agents")
        if max_revisions != 1:
            raise ValueError("P2 flow permits exactly one targeted revision")
        self.analyst = analyst
        self.reviewer = reviewer
        self.max_revisions = max_revisions

    async def run(self, request: ResearchRequest) -> FlowOutcome:
        state = FlowState(request=request)
        revision_notes: list[str] = []
        while True:
            state.draft = await self.analyst.produce_draft(request.model_copy(deep=True), revision_notes)
            state.validation = validate_draft(state.draft, request.evidence)
            if not state.validation.passed:
                return FlowOutcome(
                    draft=state.draft,
                    validation=state.validation,
                    review=None,
                    revision_count=state.revision_count,
                    verdict=ReviewVerdict.REJECT,
                )

            state.review = await self.reviewer.review(state.draft.model_copy(deep=True), list(request.evidence))
            if state.review.verdict is not ReviewVerdict.REVISE:
                return self._outcome(state, state.review.verdict)
            if state.revision_count >= self.max_revisions:
                return self._outcome(state, ReviewVerdict.HUMAN_REVIEW)
            state.revision_count += 1
            revision_notes = list(state.review.revision_notes)

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
