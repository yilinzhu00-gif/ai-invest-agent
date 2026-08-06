import json

import pytest

from backend.app.evals.runner import run_evaluations


def test_offline_runner_writes_versioned_report_and_blocks_failed_hard_gate(tmp_path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps({"id": "ok", "dataset_version": "v1", "gates": {"schema": True, "numeric": True, "citation": True, "acl": True, "no_answer": True, "tool_policy": True}})
        + "\n"
        + json.dumps({"id": "bad", "dataset_version": "v1", "gates": {"schema": True, "numeric": True, "citation": False, "acl": True, "no_answer": True, "tool_policy": True}})
        + "\n"
    )
    output = tmp_path / "offline.json"

    report = run_evaluations(dataset, mode="offline", output=output)

    assert report.total_cases == 2
    assert report.hard_gate_passed is False
    assert json.loads(output.read_text())["dataset_version"] == "v1"


def test_live_mode_requires_explicit_runner() -> None:
    with pytest.raises(ValueError, match="explicitly configured"):
        run_evaluations(__file__, mode="live", output=None)
