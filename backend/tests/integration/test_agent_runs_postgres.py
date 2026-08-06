"""PostgreSQL-only persistence coverage for P2-01 Agent Runs.

Set TEST_DATABASE_URL only to a disposable, empty database.
"""

import asyncio
import os
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for disposable PostgreSQL integration tests",
)


if TEST_DATABASE_URL:
    from alembic import command
    from alembic.config import Config
    from fastapi import Request
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.app.api.v1.agent_runs import get_development_run_executor
    from backend.app.core.config import Settings
    from backend.app.db.session import get_request_session_factory
    from backend.app.domain.agent_runs.executor import DevelopmentRunExecutor
    from backend.app.main import create_app
    from backend.app.security.authentication import OidcJwtValidator, OidcSettings


DEMO_HEADERS = {
    "X-Development-Principal-ID": "analyst-1",
    "X-Development-Workspace-ID": "workspace-a",
}
OTHER_HEADERS = {
    "X-Development-Principal-ID": "analyst-2",
    "X-Development-Workspace-ID": "workspace-b",
}


@pytest.fixture
def client() -> Generator["TestClient", None, None]:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL or "")
    command.upgrade(config, "head")
    settings = Settings(app_env="test", database_url=TEST_DATABASE_URL)
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


def test_persisted_run_replays_ordered_events_and_hides_other_workspace(client: "TestClient") -> None:
    """Losing the DB row, sequence, or workspace guard must break the visible run contract."""
    created = client.post(
        "/api/v1/agent/runs",
        json={"question": "总结贵州茅台的估值风险"},
        headers=DEMO_HEADERS,
    )

    assert created.status_code == 202
    run_id = created.json()["id"]
    for _ in range(20):
        current = client.get(f"/api/v1/agent/runs/{run_id}", headers=DEMO_HEADERS)
        if current.json()["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    events = client.get(f"/api/v1/agent/runs/{run_id}/events", headers=DEMO_HEADERS)
    assert events.status_code == 200
    assert "event: run.started" in events.text
    assert "event: run.completed" in events.text
    assert "event: heartbeat" in events.text
    event_ids = [line.removeprefix("id: ") for line in events.text.splitlines() if line.startswith("id: ")]
    assert event_ids == sorted(event_ids, key=int)
    reconnect = client.get(
        f"/api/v1/agent/runs/{run_id}/events",
        headers=DEMO_HEADERS | {"Last-Event-ID": event_ids[-1]},
    )
    assert "id: " not in reconnect.text
    assert "event: heartbeat" in reconnect.text
    assert client.get(f"/api/v1/agent/runs/{run_id}", headers=OTHER_HEADERS).status_code == 404


def test_persisted_cancel_is_idempotent_and_hidden_from_other_workspace(client: "TestClient") -> None:
    """A queued row must be safely cancellable even when its executor has not claimed it."""

    class NoopExecutor:
        def submit(self, *_: object) -> None:
            return None

    client.app.dependency_overrides[get_development_run_executor] = NoopExecutor
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
    assert first.json()["status"] == second.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/agent/runs/{run_id}/cancel", headers=OTHER_HEADERS).status_code == 404


def test_executor_timeout_persists_a_failed_terminal_run(client: "TestClient") -> None:
    """An elapsed run deadline must become a persisted failed terminal state."""
    settings = Settings(
        app_env="test",
        database_url=TEST_DATABASE_URL,
        agent_run_timeout_seconds=1,
    )

    class SlowExecutor(DevelopmentRunExecutor):
        async def wait_before_first_step(self) -> None:
            await asyncio.sleep(2)

    def slow_executor(request: "Request") -> SlowExecutor:
        return SlowExecutor(get_request_session_factory(request), request.app.state.settings)

    app = create_app(settings)
    app.dependency_overrides[get_development_run_executor] = slow_executor
    with TestClient(app, raise_server_exceptions=False) as test_client:
        created = test_client.post(
            "/api/v1/agent/runs",
            json={"question": "总结贵州茅台的估值风险"},
            headers=DEMO_HEADERS,
        )
        run_id = created.json()["id"]
        for _ in range(30):
            current = test_client.get(f"/api/v1/agent/runs/{run_id}", headers=DEMO_HEADERS)
            if current.json()["status"] == "failed":
                break
            time.sleep(0.1)
        assert current.json()["status"] == "failed"


async def _seed_active_membership() -> None:
    settings = Settings(app_env="test", database_url=TEST_DATABASE_URL)
    engine = create_async_engine(settings.async_database_url)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "DELETE FROM workspace_memberships "
                "WHERE workspace_id = :workspace_id AND user_id = :user_id"
            ),
            {"workspace_id": "workspace-oidc", "user_id": "oidc-user"},
        )
        await connection.execute(
            text(
                "INSERT INTO workspace_memberships "
                "(id, workspace_id, user_id, role, is_human) "
                "VALUES (:id, :workspace_id, :user_id, :role, :is_human)"
            ),
            {
                "id": uuid4(),
                "workspace_id": "workspace-oidc",
                "user_id": "oidc-user",
                "role": "analyst",
                "is_human": True,
            },
        )
    await engine.dispose()


def test_production_bearer_token_uses_active_workspace_membership() -> None:
    """A real FastAPI request succeeds only after JWT validation and local membership lookup."""
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL or "")
    command.upgrade(config, "head")
    asyncio.run(_seed_active_membership())
    signing_key = "test-signing-key-with-at-least-thirty-two-bytes"
    oidc = OidcSettings(
        issuer="https://issuer.example", audience="investment-api", allowed_algorithms=("HS256",)
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "oidc-user",
            "iss": oidc.issuer,
            "aud": oidc.audience,
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=1),
            "jti": "oidc-token-1",
            "scope": "agent:run",
            "typ": "access",
        },
        signing_key,
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    app = create_app(
        Settings(
            app_env="production",
            database_url=TEST_DATABASE_URL,
            oidc_issuer=oidc.issuer,
            oidc_audience=oidc.audience,
            oidc_jwks_url="https://issuer.example/.well-known/jwks.json",
        )
    )
    app.state.oidc_validator = OidcJwtValidator(oidc, key_resolver=lambda _kid: signing_key)

    class NoopExecutor:
        def submit(self, *_: object) -> None:
            return None

    app.dependency_overrides[get_development_run_executor] = NoopExecutor
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/v1/agent/runs",
            json={"question": "验证 OIDC 成员关系"},
            headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": "workspace-oidc"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["id"]
