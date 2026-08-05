import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_live_health_returns_healthy_status_and_version() -> None:
    """Removing the live endpoint or its version data must break this contract."""
    client = TestClient(create_app())

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "0.1.0"}


def test_ready_without_database_url_is_safe_while_live_stays_healthy() -> None:
    """Treating an unconfigured database as ready would route traffic too early."""
    client = TestClient(create_app())

    ready = client.get("/api/v1/health/ready", headers={"X-Correlation-ID": "ready-123"})
    live = client.get("/api/v1/health/live")

    assert ready.status_code == 503
    assert ready.json() == {
        "error": {"code": "database_not_ready"},
        "correlation_id": "ready-123",
    }
    assert live.status_code == 200
    assert live.json() == {"status": "healthy", "version": "0.1.0"}


def test_openapi_and_docs_are_available() -> None:
    """Disabling FastAPI's generated API documentation must break this contract."""
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_production_settings_require_a_database_url() -> None:
    """Allowing a production process without database configuration is unsafe."""
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(app_env="production")
