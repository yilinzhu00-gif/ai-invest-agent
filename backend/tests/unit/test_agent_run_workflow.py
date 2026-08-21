import pytest
from pydantic import ValidationError

from backend.app.domain.agent_runs.schemas import CreateAgentRunRequest


def test_market_debate_workflow_requires_symbol_and_excludes_documents() -> None:
    with pytest.raises(ValidationError):
        CreateAgentRunRequest(question="比较贵州茅台", workflow="market_debate")
    with pytest.raises(ValidationError):
        CreateAgentRunRequest(
            question="比较贵州茅台",
            workflow="market_debate",
            symbol="600519",
            document_id="00000000-0000-0000-0000-000000000031",
        )


def test_research_workflow_keeps_existing_defaults() -> None:
    request = CreateAgentRunRequest(question="总结估值风险")
    assert request.workflow.value == "research"
