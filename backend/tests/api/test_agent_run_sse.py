from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.v1.agent_runs import get_agent_run_service, get_development_run_executor
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunNotFoundError
from backend.app.main import create_app

DEMO_HEADERS = {
    "X-Development-Principal-ID": "analyst-1",
    "X-Development-Workspace-ID": "workspace-a",
}


class FakeAgentRunService:
    def __init__(self) -> None:
        self.runs: dict[UUID, SimpleNamespace] = {}

    async def create(
        self,
        principal: object,
        question: str,
        correlation_id: str,
        executor_mode: str = "development_only",
    ) -> SimpleNamespace:
        run = SimpleNamespace(
            id=uuid4(),
            status=AgentRunStatus.QUEUED.value,
            executor_mode=executor_mode,
            created_at=datetime.now(UTC),
            principal=principal,
            question=question,
            correlation_id=correlation_id,
        )
        self.runs[run.id] = run
        return run

    async def get(self, run_id: UUID, principal: object) -> SimpleNamespace:
        run = self.runs.get(run_id)
        if run is None or run.principal != principal:
            raise AgentRunNotFoundError
        return run

    async def cancel(self, run_id: UUID, principal: object) -> SimpleNamespace:
        run = await self.get(run_id, principal)
        if run.status not in {AgentRunStatus.COMPLETED.value, AgentRunStatus.FAILED.value}:
            run.status = AgentRunStatus.CANCELLED.value
        return run


class FakeDevelopmentExecutor:
    development_only = True

    def submit(self, _: UUID, __: object) -> None:
        return None


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    service = FakeAgentRunService()
    executor = FakeDevelopmentExecutor()
    app.dependency_overrides[get_agent_run_service] = lambda: service
    app.dependency_overrides[get_development_run_executor] = lambda: executor
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_create_run_returns_202_with_development_executor_contract(client: TestClient) -> None:
    """A synchronous 200 or unlabelled executor would hide an unsafe task boundary."""
    response = client.post(
        "/api/v1/agent/runs",
        json={"question": "总结贵州茅台的估值风险"},
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["executor_mode"] == "development_only"


def test_creator_can_query_the_run_created_for_its_workspace(client: TestClient) -> None:
    """Returning a generated ID without persisted ownership would make refresh recovery impossible."""
    created = client.post(
        "/api/v1/agent/runs",
        json={"question": "总结贵州茅台的估值风险"},
        headers=DEMO_HEADERS,
    )

    response = client.get(f"/api/v1/agent/runs/{created.json()['id']}", headers=DEMO_HEADERS)

    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]
    assert response.json()["status"] == "queued"


def test_cancel_is_idempotent_and_terminal_status_is_not_reversed(client: TestClient) -> None:
    """A second cancel must not create a new terminal state or return an error."""
    created = client.post(
        "/api/v1/agent/runs",
        json={"question": "总结贵州茅台的估值风险"},
        headers=DEMO_HEADERS,
    )
    run_id = created.json()["id"]

    first = client.post(f"/api/v1/agent/runs/{run_id}/cancel", headers=DEMO_HEADERS)
    second = client.post(f"/api/v1/agent/runs/{run_id}/cancel", headers=DEMO_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert second.json()["status"] == "cancelled"
