from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.agents.report_agent import ReportAgent
from backend.app.agents.schemas import Citation, ResearchClaim, ResearchDraft
from backend.app.api.v1.agent_runs import get_agent_run_service, get_development_run_executor
from backend.app.domain.agent_runs.schemas import ResearchTaskSchema
from backend.app.main import create_app

HEADERS = {
    "X-Development-Principal-ID": "researcher-1",
    "X-Development-Workspace-ID": "workspace-a",
}


class FakeTaskService:
    async def create(self, principal, question, symbol, document_id, correlation_id, **kwargs):
        return SimpleNamespace(
            id=uuid4(),
            status="queued",
            executor_mode=kwargs.get("executor_mode", "development_only"),
            workflow="research",
            symbol=symbol,
            document_id=document_id,
            created_at=datetime.now(UTC),
            target=kwargs["target"],
            research_type=kwargs["research_type"],
            depth=kwargs["depth"],
            time_range=kwargs["time_range"],
            output_format=kwargs["output_format"],
        )


class FakeExecutor:
    def __init__(self) -> None:
        self.submitted = []

    def submit(self, run_id, principal) -> None:
        self.submitted.append((run_id, principal))


class FakeReportService:
    async def list_events(self, run_id, principal, after_sequence):
        citation = Citation(id="c1", source="report.pdf", locator="page=1", text="Revenue was 100.")
        report = ReportAgent().generate(
            target="NVDA",
            draft=ResearchDraft(summary="Summary", claims=[ResearchClaim(text="Revenue was 100.", citation_ids=["c1"])]),
            evidence=[citation],
        )
        return [SimpleNamespace(event_type="research.report", payload=report.model_dump(mode="json"))]


def test_create_research_task_persists_typed_configuration() -> None:
    app = create_app()
    service = FakeTaskService()
    executor = FakeExecutor()
    app.dependency_overrides[get_agent_run_service] = lambda: service
    app.dependency_overrides[get_development_run_executor] = lambda: executor

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research/tasks",
            headers=HEADERS,
            json={
                "target": "NVDA",
                "research_type": "financial",
                "depth": "deep_research",
                "time_range": "custom",
                "custom_start": "2024-01-01",
                "custom_end": "2026-01-01",
                "output_format": "pdf",
            },
        )

    assert response.status_code == 202
    assert response.json()["target"] == "NVDA"
    assert response.json()["research_type"] == "financial"
    assert response.json()["time_range"] == "custom:2024-01-01..2026-01-01"
    assert response.json()["output_format"] == "pdf"
    assert len(executor.submitted) == 1


def test_custom_time_range_requires_both_dates() -> None:
    with pytest.raises(ValueError, match="custom time_range"):
        ResearchTaskSchema(target="AAPL", research_type="risk", time_range="custom")


def test_report_endpoint_exports_the_same_structured_report_as_markdown() -> None:
    app = create_app()
    app.dependency_overrides[get_agent_run_service] = lambda: FakeReportService()

    with TestClient(app) as client:
        response = client.get(f"/api/v1/agent/runs/{uuid4()}/report/export/markdown", headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Executive Summary" in response.text
