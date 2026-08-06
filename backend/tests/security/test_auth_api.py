from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_production_rejects_development_principal_headers() -> None:
    client = TestClient(create_app(Settings(app_env="production", database_url="postgresql://unused")))
    response = client.post(
        "/api/v1/agent/runs",
        json={"question": "test"},
        headers={"X-Development-Principal-ID": "user", "X-Development-Workspace-ID": "workspace"},
    )
    assert response.status_code == 401
