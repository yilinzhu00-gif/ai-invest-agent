from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.v1.agent_runs import get_agent_run_service, get_development_run_executor
from backend.app.domain.agent_runs.research_brief import (
    ResearchBriefContent,
    ResearchBriefVersion,
    content_sha256,
)
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunNotFoundError, DevelopmentPrincipal
from backend.app.main import create_app

DEMO_HEADERS = {
    "X-Development-Principal-ID": "analyst-1",
    "X-Development-Workspace-ID": "workspace-a",
}


class FakeAgentRunService:
    def __init__(self) -> None:
        self.runs: dict[UUID, SimpleNamespace] = {}
        self.briefs: dict[UUID, list[ResearchBriefVersion]] = {}
        self.brief_decisions: list[tuple[UUID, int, str]] = []
        self.events: dict[UUID, list[SimpleNamespace]] = {}

    async def create(
        self,
        principal: object,
        question: str,
        symbol: str | None,
        document_id: UUID | None,
        correlation_id: str,
        executor_mode: str = "development_only",
        workflow: str = "research",
    ) -> SimpleNamespace:
        run = SimpleNamespace(
            id=uuid4(),
            status=AgentRunStatus.QUEUED.value,
            executor_mode=executor_mode,
            created_at=datetime.now(UTC),
            principal=principal,
            question=question,
            symbol=symbol,
            document_id=document_id,
            correlation_id=correlation_id,
            workflow=workflow,
        )
        self.runs[run.id] = run
        return run

    async def get(self, run_id: UUID, principal: object) -> SimpleNamespace:
        run = self.runs.get(run_id)
        if run is None or run.principal != principal:
            raise AgentRunNotFoundError
        return run

    async def list_events(
        self, run_id: UUID, principal: object, after_sequence: int
    ) -> list[SimpleNamespace]:
        await self.get(run_id, principal)
        return [
            event
            for event in self.events.get(run_id, [])
            if event.sequence > after_sequence
        ]

    async def cancel(self, run_id: UUID, principal: object) -> SimpleNamespace:
        run = await self.get(run_id, principal)
        if run.status not in {AgentRunStatus.COMPLETED.value, AgentRunStatus.FAILED.value}:
            run.status = AgentRunStatus.CANCELLED.value
        return run

    async def save_brief_version(
        self, run_id: UUID, principal: object, content: ResearchBriefContent
    ) -> ResearchBriefVersion:
        await self.get(run_id, principal)
        version = len(self.briefs.setdefault(run_id, [])) + 1
        saved = ResearchBriefVersion(
            version=version,
            content=content,
            content_sha256=content_sha256(content),
        )
        self.briefs[run_id].append(saved)
        return saved

    async def list_brief_versions(
        self, run_id: UUID, principal: object
    ) -> list[ResearchBriefVersion]:
        await self.get(run_id, principal)
        return self.briefs.get(run_id, [])

    async def decide_brief_version(
        self, run_id: UUID, principal: object, version: int, decision: str
    ) -> None:
        versions = await self.list_brief_versions(run_id, principal)
        if not any(item.version == version for item in versions):
            raise ValueError("brief_version_not_found")
        self.brief_decisions.append((run_id, version, decision))


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
        json={"question": "总结贵州茅台的估值风险", "symbol": "600519"},
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["executor_mode"] == "development_only"
    assert body["symbol"] == "600519"


def test_create_market_debate_run_exposes_explicit_workflow(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/runs",
        json={
            "workflow": "market_debate",
            "symbol": "600519",
            "question": "整理支持与风险",
        },
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 202
    assert response.json()["workflow"] == "market_debate"


def test_market_debate_events_are_replayable_from_last_event_id() -> None:
    app = create_app()
    service = FakeAgentRunService()
    app.dependency_overrides[get_agent_run_service] = lambda: service
    app.dependency_overrides[get_development_run_executor] = lambda: FakeDevelopmentExecutor()
    run_id = uuid4()
    principal = DevelopmentPrincipal(principal_id="analyst-1", workspace_id="workspace-a")
    service.runs[run_id] = SimpleNamespace(
        id=run_id,
        status=AgentRunStatus.COMPLETED.value,
        executor_mode="development_only",
        workflow="market_debate",
        created_at=datetime.now(UTC),
        principal=principal,
        question="整理支持与风险",
        symbol="600519",
        document_id=None,
        correlation_id="corr-1",
    )
    service.events[run_id] = [
        SimpleNamespace(sequence=1, event_type="debate.bull", payload={"role": "bull"}),
        SimpleNamespace(sequence=2, event_type="debate.bear", payload={"role": "bear"}),
        SimpleNamespace(sequence=3, event_type="debate.moderator", payload={"consensus": []}),
    ]
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/agent/runs/{run_id}/events",
            headers=DEMO_HEADERS | {"Last-Event-ID": "1"},
        )

    assert response.status_code == 200
    assert "id: 2" in response.text
    assert "event: debate.bear" in response.text
    assert "event: debate.bull" not in response.text
    assert "event: debate.moderator" in response.text


def test_create_run_persists_the_selected_document_id_in_its_public_contract(client: TestClient) -> None:
    document_id = "00000000-0000-0000-0000-000000000031"
    response = client.post(
        "/api/v1/agent/runs",
        json={"question": "交易对价是多少", "symbol": "600519", "document_id": document_id},
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 202
    assert response.json()["document_id"] == document_id


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


def test_researcher_can_save_decide_and_export_one_identical_brief_version(client: TestClient) -> None:
    created = client.post(
        "/api/v1/agent/runs",
        json={"question": "交易对价是多少"},
        headers=DEMO_HEADERS,
    )
    run_id = created.json()["id"]
    citation = {
        "evidence_id": "document:31:block:7",
        "filename": "收购报告书.pdf",
        "document_version": 2,
        "page_number": 8,
        "block_id": "7",
    }
    content = {
        "title": "交易研究简报",
        "summary": "交易对价为 10 亿元。",
        "data_date": "2026-08-18",
        "sections": [
            {"title": "已证实的交易事实", "claims": [{"text": "交易对价为 10 亿元。", "citations": [citation]}]},
            {"title": "公告后的市场反应", "claims": []},
            {"title": "可能的影响机制", "claims": []},
            {"title": "正面因素", "claims": []},
            {"title": "风险和不确定性", "claims": []},
        ],
        "missing_information": ["公告后市场反应数据。"],
        "confidence": "low",
        "confidence_rationale": "只有一处直接公告引用。",
        "risk_disclaimer": "不构成投资建议。",
    }

    saved = client.post(
        f"/api/v1/agent/runs/{run_id}/brief/versions",
        json={"content": content},
        headers=DEMO_HEADERS,
    )
    assert saved.status_code == 201
    assert saved.json()["version"] == 1

    decision = client.post(
        f"/api/v1/agent/runs/{run_id}/brief/versions/1/decision",
        json={"decision": "accept"},
        headers=DEMO_HEADERS,
    )
    assert decision.status_code == 204
    exported = client.get(
        f"/api/v1/agent/runs/{run_id}/brief/versions/1/export/markdown",
        headers=DEMO_HEADERS,
    )
    assert exported.status_code == 200
    assert exported.headers["x-research-brief-version"] == "1"
    assert saved.json()["content_sha256"] in exported.text
    assert "交易对价为 10 亿元。" in exported.text
    assert "收购报告书.pdf · v2 · 第 8 页 · 块 7" in exported.text
