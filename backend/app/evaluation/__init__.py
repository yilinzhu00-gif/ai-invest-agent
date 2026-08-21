"""Evaluation metrics and report generation."""

from backend.app.evaluation.evaluator import EvaluationReport, evaluate_dataset, load_report
from backend.app.evaluation.metrics import (
    CaseMetrics,
    RuntimeRunMetrics,
    aggregate_case_metrics,
    aggregate_runtime_metrics,
    score_case,
    score_runtime_run,
)

__all__ = [
    "CaseMetrics",
    "EvaluationReport",
    "RuntimeRunMetrics",
    "aggregate_case_metrics",
    "aggregate_runtime_metrics",
    "evaluate_dataset",
    "load_report",
    "score_case",
    "score_runtime_run",
]
