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
    Citation,
    ResearchClaim,
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

    assert outcome.verdict is ReviewVerdict.APPROVE
    assert [f"{role}.{status}" for role, status, _ in observer.events] == [
        "analyst.started",
        "analyst.completed",
        "validator.started",
        "validator.completed",
        "reviewer.started",
        "reviewer.completed",
    ]
    assert observer.events[3][2] == {"passed": True, "error_count": 0}


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

    assert outcome.verdict is ReviewVerdict.REJECT


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


class FakeGateway:
    def __init__(self) -> None:
        self.requests: list[object] = []
        self.responses = [
            '{"summary":"风险摘要","claims":[{"text":"收入增速由 18% 放缓至 6%，原材料成本上升。","citation_ids":["annual-report-p12"],"numeric_values":[]}],"requested_tool_permissions":[]}',
            '{"verdict":"approve","claim_citation_ids":["annual-report-p12"],"revision_notes":[]}',
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
