from backend.app.evaluation.metrics import aggregate_case_metrics, score_case


def test_score_case_computes_quality_and_runtime_metrics() -> None:
    result = score_case(
        {
            "id": "case-1",
            "expected_facts": ["Revenue grew 10%", "Margin stable"],
            "predicted_facts": ["revenue grew 10%"],
            "expected_citation_ids": ["p1", "p2"],
            "cited_citation_ids": ["p2"],
            "cost_microusd": 150_000,
            "latency_ms": 30_000,
            "tool_calls": [{"success": True}, {"success": False}],
        }
    )

    assert result.accuracy == 0.5
    assert result.citation_score == 0.5
    assert result.cost_usd == 0.15
    assert result.latency_seconds == 30
    assert result.tool_success_rate == 0.5


def test_aggregate_preserves_missing_evidence_as_none() -> None:
    result = aggregate_case_metrics([score_case({"id": "without-ground-truth"})])

    assert result["accuracy"] is None
    assert result["citation_score"] is None
    assert result["cost_usd"] is None
    assert result["coverage"] == {
        "accuracy": 0,
        "citation_score": 0,
        "cost_usd": 0,
        "latency_seconds": 0,
        "tool_success_rate": 0,
    }
