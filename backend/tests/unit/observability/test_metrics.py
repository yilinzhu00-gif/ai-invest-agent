from backend.app.observability.metrics import safe_metric_labels


def test_metrics_reject_high_cardinality_identity_labels() -> None:
    assert safe_metric_labels({"route": "/api/v1/health", "status": "200"}) == {"route": "/api/v1/health", "status": "200"}
    try:
        safe_metric_labels({"run_id": "secret", "status": "200"})
    except ValueError as error:
        assert str(error) == "high_cardinality_label"
    else:
        raise AssertionError("run_id must never be a metric label")
