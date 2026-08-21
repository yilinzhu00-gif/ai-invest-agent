from datetime import UTC, datetime, timedelta

from backend.app.evaluation.metrics import aggregate_runtime_metrics, score_runtime_run


def test_runtime_metrics_capture_success_latency_cost_and_tool_success() -> None:
    started = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    scored = score_runtime_run(
        run_id="run-1",
        status="completed",
        created_at=started,
        updated_at=started + timedelta(seconds=30),
        cost_microusd=120_000,
        events=[
            {"event_type": "agent.trace", "payload": {"type": "TOOL_CALL_START"}},
            {"event_type": "agent.trace", "payload": {"type": "TOOL_CALL_END"}},
            {"event_type": "research.evidence_result", "payload": {"claims": [{"citations": [{"evidence_id": "c1"}]}]}},
        ],
    )

    assert scored.success is True
    assert scored.latency_seconds == 30
    assert scored.cost_usd == 0.12
    assert scored.citation_score == 1
    assert scored.tool_success_rate == 1
    aggregate = aggregate_runtime_metrics([scored])
    assert aggregate["total_research"] == 1
    assert aggregate["success_rate"] == 1
    assert aggregate["average_cost_usd"] == 0.12


def test_runtime_metrics_do_not_infer_accuracy_from_completion() -> None:
    aggregate = aggregate_runtime_metrics([])

    assert aggregate["accuracy"] is None
    assert aggregate["success_rate"] is None
