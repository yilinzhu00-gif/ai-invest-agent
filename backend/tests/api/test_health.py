from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_live_health_returns_healthy_status_and_version() -> None:
    """Removing the live endpoint or its version data must break this contract."""
    client = TestClient(create_app())

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "0.1.0"}


def test_openapi_and_docs_are_available() -> None:
    """Disabling FastAPI's generated API documentation must break this contract."""
    client = TestClient(create_app())

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
