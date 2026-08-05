"""PostgreSQL-only readiness coverage.

Set TEST_DATABASE_URL to a disposable PostgreSQL database before running this module.
"""

import os

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for real PostgreSQL integration tests",
)


if TEST_DATABASE_URL:
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    from backend.app.core.config import Settings
    from backend.app.main import create_app


@pytest.fixture
def migrated_settings() -> "Settings":
    """Apply the real migration before exercising the HTTP readiness boundary."""
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL or "")
    command.upgrade(config, "head")
    return Settings(app_env="test", database_url=TEST_DATABASE_URL)


def test_ready_is_healthy_after_real_postgres_migration(migrated_settings: "Settings") -> None:
    """A missing migration/version row must never be reported as ready."""
    client = TestClient(create_app(migrated_settings))

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "version": "0.1.0"}


def test_ready_hides_connection_failures_without_breaking_live() -> None:
    """Database connection failures must stay a safe readiness-only failure."""
    unavailable = Settings(
        app_env="test",
        database_url="postgresql://integration:integration@127.0.0.1:1/unreachable",
        db_connect_timeout=0.1,
    )
    client = TestClient(create_app(unavailable), raise_server_exceptions=False)

    ready = client.get("/api/v1/health/ready", headers={"X-Correlation-ID": "ready-failed-123"})
    live = client.get("/api/v1/health/live")

    assert ready.status_code == 503
    assert ready.json() == {
        "error": {"code": "database_not_ready"},
        "correlation_id": "ready-failed-123",
    }
    assert "127.0.0.1" not in ready.text
    assert "Traceback" not in ready.text
    assert live.status_code == 200
    assert live.json() == {"status": "healthy", "version": "0.1.0"}
