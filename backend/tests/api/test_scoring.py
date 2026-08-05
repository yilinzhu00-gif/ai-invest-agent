from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
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


def test_evaluate_normalizes_integer_metric_details_to_numbers(client: TestClient) -> None:
    """Returning an unnormalized input value would drift from the frontend number contract."""
    response = client.post(
        "/api/v1/scoring/evaluate", json=_payload(FULL_METRICS | {"pe_ttm": 18})
    )

    assert response.status_code == 200
    value = response.json()["result"]["dimensions"][0]["metrics"][0]["value"]
    assert value == 18.0
    assert isinstance(value, float)


def test_evaluate_with_single_metric_hides_score_details(client: TestClient) -> None:
    """Returning a grade for insufficient data must break this endpoint."""
    response = client.post("/api/v1/scoring/evaluate", json=_payload({"pe_ttm": 18.5}))

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "insufficient_data"
    assert body["result"] is None
    assert "grade" not in body
    assert "label" not in body


def test_explicit_null_metric_is_retained_as_a_quality_signal(client: TestClient) -> None:
    """Rejecting explicit null would remove the documented missing-data representation."""
    response = client.post("/api/v1/scoring/evaluate", json=_payload({"pe_ttm": None}))

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
    assert "pe_ttm" in response.json()["missing_metrics"]


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


@pytest.mark.parametrize("illegal_value", ["18.5", True, {}, []])
def test_metric_values_reject_non_numeric_json_types(
    client: TestClient, illegal_value: object
) -> None:
    """Coercing non-numeric JSON into metrics would break the public request contract."""
    response = client.post(
        "/api/v1/scoring/evaluate",
        json=_payload({"pe_ttm": illegal_value}),
        headers={"X-Correlation-ID": "metric-type-123"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "validation_error"},
        "correlation_id": "metric-type-123",
    }


def test_declared_oversized_body_returns_correlated_413() -> None:
    """Trusting a declared body over the limit would allow avoidable memory pressure."""
    app = create_app(Settings(max_request_body_bytes=128))
    with TestClient(app, raise_server_exceptions=False) as limited_client:
        response = limited_client.post(
            "/api/v1/scoring/evaluate",
            content=b"{" + b" " * 256 + b"}",
            headers={
                "Content-Type": "application/json",
                "X-Correlation-ID": "declared-large-123",
            },
        )

    assert response.status_code == 413
    assert response.headers["X-Correlation-ID"] == "declared-large-123"
    assert response.json() == {
        "error": {"code": "request_body_too_large"},
        "correlation_id": "declared-large-123",
    }


def test_streamed_oversized_body_returns_correlated_413() -> None:
    """Omitting Content-Length must not bypass the request-body limit."""
    app = create_app(Settings(max_request_body_bytes=128))
    with TestClient(app, raise_server_exceptions=False) as limited_client:
        response = limited_client.post(
            "/api/v1/scoring/evaluate",
            content=(chunk for chunk in [b"{" + b" " * 80, b" " * 80 + b"}"]),
            headers={
                "Content-Type": "application/json",
                "X-Correlation-ID": "streamed-large-123",
            },
        )

    assert response.status_code == 413
    assert response.headers["X-Correlation-ID"] == "streamed-large-123"
    assert response.json() == {
        "error": {"code": "request_body_too_large"},
        "correlation_id": "streamed-large-123",
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
