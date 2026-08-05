from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.domain.scoring.service import get_scoring_service
from backend.app.main import create_app

FULL_METRICS = {
    "pe_ttm": 18.5,
    "pb": 2.3,
    "roe": 16.2,
    "net_margin": 12.5,
    "gross_margin": 38.0,
    "rev_growth": 22.0,
    "profit_growth": 28.0,
    "debt_ratio": 45.0,
    "current_ratio": 1.8,
    "ret_60d": 8.0,
    "price_vs_ma20": 3.5,
}


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def _payload(metrics: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": "600519", "as_of_date": "2026-08-05", "metrics": metrics}


def test_evaluate_returns_complete_existing_score_for_full_metrics(client: TestClient) -> None:
    """Bypassing the root scorer or losing its output must break this endpoint."""
    response = client.post("/api/v1/scoring/evaluate", json=_payload(FULL_METRICS))

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["coverage"] == 1.0
    assert body["missing_core_dimensions"] == []
    assert body["missing_metrics"] == []
    assert body["result"]["grade"] == "B"
    assert body["result"]["label"] == "看好"


def test_evaluate_with_single_metric_hides_score_details(client: TestClient) -> None:
    """Returning a grade for insufficient data must break this endpoint."""
    response = client.post("/api/v1/scoring/evaluate", json=_payload({"pe_ttm": 18.5}))

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "insufficient_data"
    assert body["result"] is None
    assert "grade" not in body
    assert "label" not in body


def test_disallowed_cors_preflight_returns_a_correlated_error_envelope(client: TestClient) -> None:
    """Returning Starlette's plain-text preflight rejection must break this contract."""
    response = client.options(
        "/api/v1/scoring/evaluate",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "X-Correlation-ID": "cors-request-123",
        },
    )

    assert response.status_code == 400
    assert response.headers["X-Correlation-ID"] == "cors-request-123"
    assert response.json() == {
        "error": {"code": "cors_preflight_rejected"},
        "correlation_id": "cors-request-123",
    }


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"symbol": "600519", "as_of_date": "not-a-date", "metrics": {}}, 422),
        ({"symbol": "ABC123", "as_of_date": "2026-08-05", "metrics": {}}, 422),
        ({"symbol": "６００５１９", "as_of_date": "2026-08-05", "metrics": {}}, 422),
        ({"symbol": "٦٠٠٥١٩", "as_of_date": "2026-08-05", "metrics": {}}, 422),
        ({"symbol": "600519", "as_of_date": 20260805, "metrics": {}}, 422),
        ({"symbol": "600519", "as_of_date": "2026-08-05T00:00:00", "metrics": {}}, 422),
        (
            {
                "symbol": "600519",
                "as_of_date": "2026-08-05",
                "metrics": {},
                "unexpected": True,
            },
            422,
        ),
        (
            {
                "symbol": "600519",
                "as_of_date": "2026-08-05",
                "metrics": {f"metric_{index}": index for index in range(101)},
            },
            422,
        ),
    ],
)
def test_invalid_requests_return_a_stable_error_envelope(
    client: TestClient, payload: dict[str, Any], expected_status: int
) -> None:
    """Leaking framework validation details or omitting request IDs must break this API."""
    response = client.post(
        "/api/v1/scoring/evaluate", json=payload, headers={"X-Correlation-ID": "request-123"}
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {"code": "validation_error"},
        "correlation_id": "request-123",
    }


def test_domain_failure_returns_safe_internal_error(client: TestClient) -> None:
    """Exposing a service exception message or traceback must break this API."""

    class BrokenScoringService:
        def evaluate(self, metrics: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("sensitive metric payload must not leak")

    app = create_app()
    app.dependency_overrides[get_scoring_service] = BrokenScoringService
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        response = failing_client.post(
            "/api/v1/scoring/evaluate",
            json=_payload(FULL_METRICS),
            headers={"X-Correlation-ID": "server-error-123"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_server_error"},
        "correlation_id": "server-error-123",
    }
    assert "sensitive" not in response.text
    assert "Traceback" not in response.text
