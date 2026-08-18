from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.agents.concrete import (
    EvidenceBoundAnalyst,
    EvidenceReviewer,
    RunUsageLedger,
    StructuredModelAnalyst,
    StructuredModelReviewer,
)
from backend.app.agents.factory import build_research_flow
from backend.app.agents.flow import ControlledResearchFlow
from backend.app.agents.schemas import (
    CalculationOperator,
    Citation,
    ClaimCitationReview,
    ConclusionConfidence,
    NumericCalculation,
    ResearchClaim,
    ResearchConclusion,
    ResearchDraft,
    ResearchMemory,
    ResearchRequest,
    ReviewDecision,
    ReviewVerdict,
)
from backend.app.agents.validators import EvidenceValidator
from backend.app.core.config import Settings
from backend.app.models.schemas import ModelResponse, ModelUsage


def _request() -> ResearchRequest:
    return ResearchRequest(
        run_id=uuid4(),
        workspace_id=uuid4(),
        question="该公司的主要经营风险是什么？",
        evidence=[
            Citation(
                id="annual-report-p12",
                source="annual-report.pdf",
                locator="p.12",
                text="收入增速由 18% 放缓至 6%，原材料成本上升。",
            )
        ],
    )


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    async def on_stage(self, role: str, status: str, payload: dict[str, object]) -> None:
        self.events.append((role, status, payload))


def test_openai_compatible_mode_requires_an_explicit_key_and_builds_offline() -> None:
    with pytest.raises(ValidationError, match="MODEL_API_KEY"):
        Settings(agent_execution_mode="openai_compatible")

    flow = build_research_flow(
        Settings(agent_execution_mode="openai_compatible", model_api_key="test-key")
    )

    assert flow.analyst.allow_delegation is False
    assert flow.reviewer.allow_delegation is False


@pytest.mark.asyncio
async def test_concrete_agents_run_in_order_and_emit_auditable_stages() -> None:
    observer = RecordingObserver()
    outcome = await ControlledResearchFlow(
        EvidenceBoundAnalyst(), EvidenceReviewer(), EvidenceValidator(), observer=observer
    ).run(_request())

    assert outcome.verdict is ReviewVerdict.HUMAN_REVIEW
    assert [f"{role}.{status}" for role, status, _ in observer.events] == [
        "analyst.started",
        "analyst.completed",
        "numeric_validator.started",
        "numeric_validator.completed",
        "reviewer.started",
        "reviewer.completed",
    ]
    assert observer.events[3][2] == {"passed": True, "error_count": 0}


@pytest.mark.asyncio
async def test_structured_conclusion_limits_retrieved_excerpts_to_its_fixed_section_capacity() -> None:
    request = _request().model_copy(
        update={
            "require_structured_conclusion": True,
            "evidence": [
                Citation(
                    id=f"announcement-p{index}",
                    source="announcement.pdf",
                    locator=f"p.{index}",
                    text=f"第 {index} 条公告原文。",
                )
                for index in range(1, 8)
            ],
        }
    )

    draft = await EvidenceBoundAnalyst().produce_draft(request, [])

    assert draft.conclusion is not None
    assert len(draft.claims) == 6
    assert len(draft.conclusion.confirmed_transaction_facts) == 6
    assert len(draft.conclusion.required_evidence_ids) == 6


@pytest.mark.asyncio
async def test_unknown_reviewer_target_cannot_complete_the_flow() -> None:
    class BadReviewer:
        allow_delegation = False

        async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision:
            del draft, citations
            return ReviewDecision(verdict=ReviewVerdict.APPROVE, claim_citation_ids=["not-provided"])

    outcome = await ControlledResearchFlow(
        EvidenceBoundAnalyst(), BadReviewer(), EvidenceValidator()
    ).run(_request())

    assert outcome.verdict is ReviewVerdict.HUMAN_REVIEW


def test_validator_blocks_numeric_value_not_present_in_its_citation() -> None:
    result = EvidenceValidator().validate(
        ResearchDraft(
            summary="风险摘要",
            claims=[
                ResearchClaim(
                    text="成本压力", citation_ids=["annual-report-p12"], numeric_values=[99]
                )
            ],
        ),
        _request().evidence,
    )

    assert result.passed is False
    assert "numeric value 99" in result.errors[0]


def test_numeric_validator_recomputes_analyst_calculations() -> None:
    claim = ResearchClaim(
        text="收盘价由 100 变为 110，区间涨幅为 10%。",
        citation_ids=["annual-report-p12"],
        calculations=[
            NumericCalculation(
                operator=CalculationOperator.PERCENT_CHANGE,
                operands=[100, 110],
                result=10,
            )
        ],
    )
    evidence = [
        Citation(
            id="annual-report-p12",
            source="market-data.csv",
            locator="row=1",
            text="收盘价由 100 变为 110。",
        )
    ]

    assert EvidenceValidator().validate(ResearchDraft(summary="数值复核", claims=[claim]), evidence).passed
    incorrect = claim.model_copy(
        update={"calculations": [claim.calculations[0].model_copy(update={"result": 8})]}
    )
    assert not EvidenceValidator().validate(
        ResearchDraft(summary="数值复核", claims=[incorrect]), evidence
    ).passed


@pytest.mark.asyncio
async def test_removing_key_announcement_evidence_invalidates_the_original_conclusion() -> None:
    claim = ResearchClaim(text="本次交易对价为 10 亿元。", citation_ids=["announcement-core"])
    conclusion = ResearchConclusion(
        confirmed_transaction_facts=[claim],
        post_announcement_market_reaction=[],
        possible_impact_mechanisms=[],
        positive_factors=[],
        risks_and_uncertainties=[],
        missing_information=["公告后行情窗口尚未绑定。"],
        confidence=ConclusionConfidence.LOW,
        confidence_rationale="关键交易对价仅由一处公告原文支持。",
        required_evidence_ids=["announcement-core"],
    )
    draft = ResearchDraft(summary="交易对价结论", claims=[claim], conclusion=conclusion)

    class FixedAnalyst:
        allow_delegation = False

        async def produce_draft(self, request: ResearchRequest, revision_notes: list[str]) -> ResearchDraft:
            del request, revision_notes
            return draft

    class PerClaimReviewer:
        allow_delegation = False

        async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision:
            del draft, citations
            return ReviewDecision(
                verdict=ReviewVerdict.APPROVE,
                claim_citation_ids=["announcement-core"],
                claim_reviews=[
                    ClaimCitationReview(
                        claim_index=0,
                        citation_id="announcement-core",
                        supported=True,
                    )
                ],
            )

    complete_request = ResearchRequest(
        run_id=uuid4(),
        workspace_id=uuid4(),
        question="本次交易对价是多少？",
        evidence=[
            Citation(
                id="announcement-core",
                source="收购公告.pdf",
                locator="p.8",
                text="本次交易对价为 10 亿元。",
            )
        ],
        require_structured_conclusion=True,
    )
    flow = ControlledResearchFlow(FixedAnalyst(), PerClaimReviewer(), EvidenceValidator())
    assert (await flow.run(complete_request)).verdict is ReviewVerdict.APPROVE

    missing_key_evidence = complete_request.model_copy(update={"evidence": []})
    outcome = await flow.run(missing_key_evidence)
    assert outcome.verdict is ReviewVerdict.REJECT
    assert "conclusion requires missing evidence: announcement-core" in outcome.validation.errors


class FakeGateway:
    def __init__(self) -> None:
        self.requests: list[object] = []
        self.responses = [
            '{"summary":"风险摘要","claims":[{"text":"收入增速由 18% 放缓至 6%，原材料成本上升。","citation_ids":["annual-report-p12"],"numeric_values":[]}],"requested_tool_permissions":[]}',
            '{"verdict":"approve","claim_citation_ids":["annual-report-p12"],"claim_reviews":[{"claim_index":0,"citation_id":"annual-report-p12","supported":true}],"revision_notes":[]}',
        ]

    async def complete(self, request: object, timeout_seconds: float) -> ModelResponse:
        del timeout_seconds
        self.requests.append(request)
        return ModelResponse(
            text=self.responses.pop(0),
            usage=ModelUsage(provider="fake", model="fake-model", input_tokens=10, output_tokens=5),
        )


@pytest.mark.asyncio
async def test_structured_model_roles_use_distinct_prompts_and_shared_budget() -> None:
    gateway = FakeGateway()
    ledger = RunUsageLedger(max_tokens=100, max_cost_microusd=100)
    request = _request().model_copy(
        update={"memory": [ResearchMemory(id=uuid4(), content="偏好关注现金流和估值风险。")]} 
    )
    outcome = await ControlledResearchFlow(
        StructuredModelAnalyst(gateway, "analyst-model", 5, ledger),
        StructuredModelReviewer(gateway, "review-model", 5, ledger),
        EvidenceValidator(),
    ).run(request)

    assert outcome.verdict is ReviewVerdict.APPROVE
    assert len(gateway.requests) == 2
    assert gateway.requests[0].model == "analyst-model"
    assert gateway.requests[1].model == "review-model"
    assert ledger._input_tokens == 20
    assert '"memory": [{"id":' in gateway.requests[0].messages[1].content
