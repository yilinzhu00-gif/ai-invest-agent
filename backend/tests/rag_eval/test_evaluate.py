from backend.app.domain.knowledge.evaluate import evaluate


def test_offline_evaluation_reports_retrieval_and_no_answer_metrics(tmp_path) -> None:
    dataset = tmp_path / "queries.jsonl"
    dataset.write_text(
        '{"expected_evidence_ids":["a"],"retrieved_evidence_ids":["a"]}\n'
        '{"expected_evidence_ids":[],"retrieved_evidence_ids":[]}\n'
    )

    result = evaluate(dataset)

    assert result == {"cases": 2, "recall_at_k": 1.0, "mrr": 1.0, "citation_accuracy": 1.0, "no_answer_accuracy": 1.0}
