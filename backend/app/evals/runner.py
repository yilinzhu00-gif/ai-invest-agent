"""Deterministic, append-only offline evaluation report generator."""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from backend.app.evals.scorers import HARD_GATES, score_gates


@dataclass(frozen=True)
class EvaluationReport:
    dataset_version: str
    mode: str
    total_cases: int
    scores: dict[str, float]
    hard_gate_passed: bool


def run_evaluations(
    dataset: Path, *, mode: Literal["offline", "live"], output: Path | None
) -> EvaluationReport:
    if mode == "live":
        raise ValueError("live evaluation requires an explicitly configured provider runner")
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line]
    all_scores = [score_gates(case.get("gates", {}))[0] for case in cases]
    scores = {
        gate: sum(case_scores[gate] for case_scores in all_scores) / len(all_scores)
        for gate in HARD_GATES
    }
    report = EvaluationReport(
        dataset_version=cases[0].get("dataset_version", "v1") if cases else "v1",
        mode=mode,
        total_cases=len(cases),
        scores=scores,
        hard_gate_passed=all(all(score == 1 for score in case_scores.values()) for case_scores in all_scores),
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "live"], required=True)
    parser.add_argument("--dataset", type=Path, default=Path("evals/agent/research_cases.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_evaluations(args.dataset, mode=args.mode, output=args.output)
    print(json.dumps(asdict(report), ensure_ascii=False))
    if not report.hard_gate_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
