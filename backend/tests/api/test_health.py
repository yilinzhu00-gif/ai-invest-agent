import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.db.session import create_database_engine
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


def test_ready_with_an_unreachable_database_returns_a_safe_503() -> None:
    """Letting connection setup errors escape would turn readiness into a 500."""
    settings = Settings(
        app_env="test",
        database_url="postgresql://integration:integration@127.0.0.1:1/unreachable",
        db_connect_timeout=0.1,
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)

    response = client.get("/api/v1/health/ready", headers={"X-Correlation-ID": "offline-123"})

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "database_not_ready"},
        "correlation_id": "offline-123",
    }
    assert "Traceback" not in response.text


def test_database_engine_applies_connect_timeout_to_pool_waiting() -> None:
    """Ignoring DB_CONNECT_TIMEOUT for the pool could stall saturated requests for 30 seconds."""
    settings = Settings(
        database_url="postgresql://integration:integration@127.0.0.1:1/unreachable",
        db_connect_timeout=0.25,
    )
    engine = create_database_engine(settings)

    try:
        assert engine.pool.timeout() == 0.25
    finally:
        asyncio.run(engine.dispose())


def test_openapi_and_docs_are_available() -> None:
    """Disabling FastAPI's generated API documentation must break this contract."""
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_production_settings_require_a_database_url() -> None:
    """Allowing a production process without database configuration is unsafe."""
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(app_env="production")
