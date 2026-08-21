from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_evaluation_summary_is_read_only_and_marks_existing_fixture_unverified() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/evaluation/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UNVERIFIED"
    assert payload["metrics"]["accuracy"] is None
