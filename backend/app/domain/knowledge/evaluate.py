"""Offline retrieval quality gate; no model, database or network dependency."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path


def evaluate(dataset: Path) -> dict[str, float | int]:
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    reciprocal_ranks: list[float] = []
    recalls: list[float] = []
    citation_hits = 0
    no_answer_hits = 0
    for case in cases:
        expected = set(case.get("expected_evidence_ids", []))
        actual = case.get("retrieved_evidence_ids", [])
        if not expected:
            no_answer_hits += actual == []
            continue
        hits = expected.intersection(actual)
        recalls.append(len(hits) / len(expected))
        citation_hits += bool(hits)
        reciprocal_ranks.append(next((1 / (index + 1) for index, item in enumerate(actual) if item in expected), 0))
    answer_cases = len(recalls)
    return {
        "cases": len(cases),
        "recall_at_k": round(sum(recalls) / answer_cases, 4) if answer_cases else 0,
        "mrr": round(sum(reciprocal_ranks) / answer_cases, 4) if answer_cases else 0,
        "citation_accuracy": round(citation_hits / answer_cases, 4) if answer_cases else 0,
        "no_answer_accuracy": round(no_answer_hits / (len(cases) - answer_cases), 4)
        if len(cases) > answer_cases
        else 0,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.dataset), ensure_ascii=False))


if __name__ == "__main__":
    main()
