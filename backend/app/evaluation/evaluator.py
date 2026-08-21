"""Versioned JSONL evaluator and report contract used by the dashboard."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from backend.app.evaluation.metrics import aggregate_case_metrics, score_case

EvaluationStatus = Literal["VERIFIED", "PARTIAL", "UNVERIFIED"]


@dataclass(frozen=True)
class EvaluationReport:
    dataset_version: str
    mode: str
    total_cases: int
    status: EvaluationStatus
    metrics: dict[str, object]
    cases: list[dict[str, object]]
    errors: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_cases(dataset: Path) -> tuple[list[dict[str, Any]], list[str]]:
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_no, line in enumerate(dataset.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"line {line_no}: invalid JSON ({error.msg})")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_no}: expected an object")
            continue
        cases.append(value)
    return cases, errors


def evaluate_dataset(
    dataset: Path, *, mode: str = "offline", output: Path | None = None
) -> EvaluationReport:
    cases, errors = _read_cases(dataset)
    scored = [score_case(case) for case in cases]
    metrics = aggregate_case_metrics(scored)
    available = [name for name, value in metrics.items() if name != "coverage" and value is not None]
    status: EvaluationStatus = "VERIFIED" if len(available) == 5 and not errors else (
        "PARTIAL" if available else "UNVERIFIED"
    )
    report = EvaluationReport(
        dataset_version=str(cases[0].get("dataset_version", "unknown")) if cases else "unknown",
        mode=mode,
        total_cases=len(cases),
        status=status,
        metrics=metrics,
        cases=[case.as_dict() for case in scored],
        errors=errors,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def load_report(path: Path) -> EvaluationReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationReport(
        dataset_version=str(data.get("dataset_version", "unknown")),
        mode=str(data.get("mode", "offline")),
        total_cases=int(data.get("total_cases", 0)),
        status=data.get("status", "UNVERIFIED"),
        metrics=dict(data.get("metrics", {})),
        cases=list(data.get("cases", [])),
        errors=list(data.get("errors", [])),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Agent quality and runtime metrics")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", default="offline")
    args = parser.parse_args()
    print(json.dumps(evaluate_dataset(args.dataset, mode=args.mode, output=args.output).as_dict(), ensure_ascii=False))


if __name__ == "__main__":
    main()
