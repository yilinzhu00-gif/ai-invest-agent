from collections.abc import Sequence
from uuid import uuid4

import pytest

from backend.app.agents.flow import ControlledResearchFlow
from backend.app.agents.runtime import _load_crewai_flow
from backend.app.agents.schemas import (
    AgentRuntime,
    Citation,
    ClaimCitationReview,
    ResearchClaim,
    ResearchDraft,
    ResearchRequest,
    ReviewDecision,
    ReviewVerdict,
)


class RecordingAnalyst:
    allow_delegation = False

    def __init__(self, drafts: Sequence[ResearchDraft]) -> None:
        self.drafts = list(drafts)
        self.calls = 0

    async def produce_draft(self, request: ResearchRequest, revision_notes: list[str]) -> ResearchDraft:
        del request, revision_notes
        result = self.drafts[self.calls]
        self.calls += 1
        return result


class RecordingReviewer:
    allow_delegation = False

    def __init__(self, decisions: Sequence[ReviewDecision]) -> None:
        self.decisions = list(decisions)
        self.calls = 0

    async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision:
        del draft, citations
        result = self.decisions[self.calls]
        self.calls += 1
        return result


def request() -> ResearchRequest:
    return ResearchRequest(
        run_id=uuid4(),
        workspace_id=uuid4(),
        question="宁德时代的估值风险是什么？",
        evidence=[Citation(id="c1", source="annual-report.pdf", locator="p.12", text="营收增长放缓")],
    )


def draft(*, citation_ids: list[str] | None = None) -> ResearchDraft:
    return ResearchDraft(
        summary="增长存在不确定性。",
        claims=[ResearchClaim(text="营收增长放缓", citation_ids=citation_ids or ["c1"])],
    )


@pytest.mark.asyncio
async def test_validator_failure_is_hard_gate_before_reviewer() -> None:
    analyst = RecordingAnalyst([draft(citation_ids=["missing"])])
    reviewer = RecordingReviewer(
        [ReviewDecision(verdict=ReviewVerdict.APPROVE, claim_citation_ids=["c1"])]
    )

    outcome = await ControlledResearchFlow(analyst, reviewer).run(request())

    assert outcome.verdict is ReviewVerdict.REJECT
    assert outcome.validation.passed is False
    assert reviewer.calls == 0


@pytest.mark.asyncio
async def test_reviewer_can_request_only_one_targeted_revision() -> None:
    analyst = RecordingAnalyst([draft(), draft()])
    reviewer = RecordingReviewer(
        [
            ReviewDecision(
                verdict=ReviewVerdict.REVISE,
                claim_citation_ids=["c1"],
                claim_reviews=[ClaimCitationReview(claim_index=0, citation_id="c1", supported=False)],
                revision_notes=["补充风险边界"],
            ),
            ReviewDecision(
                verdict=ReviewVerdict.APPROVE,
                claim_citation_ids=["c1"],
                claim_reviews=[ClaimCitationReview(claim_index=0, citation_id="c1", supported=True)],
            ),
        ]
    )

    outcome = await ControlledResearchFlow(analyst, reviewer).run(request())

    assert outcome.verdict is ReviewVerdict.APPROVE
    assert outcome.revision_count == 1
    assert analyst.calls == 2
    assert reviewer.calls == 2


@pytest.mark.asyncio
async def test_reviewer_must_check_each_citation_not_just_each_claim() -> None:
    request_with_two_citations = request().model_copy(
        update={
            "evidence": [
                Citation(id="c1", source="announcement.pdf", locator="p.1", text="交易对价为 10 亿元"),
                Citation(id="c2", source="announcement.pdf", locator="p.2", text="资金来自自有资金"),
            ]
        }
    )
    analyst = RecordingAnalyst([
        ResearchDraft(
            summary="交易摘要",
            claims=[ResearchClaim(text="交易信息", citation_ids=["c1", "c2"])],
        )
    ])
    reviewer = RecordingReviewer([
        ReviewDecision(
            verdict=ReviewVerdict.APPROVE,
            claim_citation_ids=["c1", "c2"],
            claim_reviews=[ClaimCitationReview(claim_index=0, citation_id="c1", supported=True)],
        )
    ])

    outcome = await ControlledResearchFlow(analyst, reviewer).run(request_with_two_citations)

    assert outcome.verdict is ReviewVerdict.HUMAN_REVIEW


@pytest.mark.parametrize("runtime", [AgentRuntime.LANGGRAPH, AgentRuntime.CREWAI])
def test_runtime_enum_keeps_migration_fallback(runtime: AgentRuntime) -> None:
    assert runtime.value in {"langgraph", "crewai"}


def test_crewai_flow_dependency_is_loadable_without_home_storage() -> None:
    flow, start = _load_crewai_flow()

    assert flow.__name__ == "Flow"
    assert callable(start)


def test_approve_review_requires_a_cited_claim() -> None:
    with pytest.raises(ValueError, match="cite at least one"):
        ReviewDecision(verdict=ReviewVerdict.APPROVE)
