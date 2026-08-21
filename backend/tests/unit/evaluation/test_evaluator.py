import json

from backend.app.evaluation.evaluator import evaluate_dataset


def test_evaluate_dataset_writes_report_and_marks_partial_evidence(tmp_path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case-1",
                "dataset_version": "phase5-v1",
                "expected_facts": ["a"],
                "predicted_facts": ["a"],
                "expected_citation_ids": ["c1"],
                "cited_citation_ids": ["c1"],
                "cost_usd": 0.15,
                "latency_seconds": 30,
                "tool_calls": [{"success": True}],
            }
        )
        + "\n"
    )
    output = tmp_path / "report.json"

    report = evaluate_dataset(dataset, output=output)

    assert report.status == "VERIFIED"
    assert report.metrics["accuracy"] == 1
    assert json.loads(output.read_text())["metrics"]["cost_usd"] == 0.15
