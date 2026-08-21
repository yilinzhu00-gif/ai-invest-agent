"""Deterministic quality and runtime metrics for Agent evaluation records.

The functions in this module only score fields present in an evaluation record.
They never infer quality from a pre-filled dashboard value. Missing evidence is
represented by ``None`` and is surfaced as unverified by the evaluator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def _normalise(value: object) -> str:
    return " ".join(str(value).strip().lower().split())


def _set(value: object) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {_normalise(item) for item in value if _normalise(item)}


def score_accuracy(expected: object, predicted: object) -> float | None:
    """Return fact recall, using exact normalized fact strings.

    A case without both expected and predicted facts has no accuracy evidence.
    """

    if not isinstance(expected, Sequence) or isinstance(expected, (str, bytes)):
        return None
    if not isinstance(predicted, Sequence) or isinstance(predicted, (str, bytes)):
        return None
    expected_set, predicted_set = _set(expected), _set(predicted)
    if not expected_set:
        return None
    return len(expected_set & predicted_set) / len(expected_set)


def score_citation(expected: object, cited: object) -> float | None:
    """Return the fraction of expected citation IDs covered by the answer."""

    if not isinstance(expected, Sequence) or isinstance(expected, (str, bytes)):
        return None
    if not isinstance(cited, Sequence) or isinstance(cited, (str, bytes)):
        return None
    expected_set, cited_set = _set(expected), _set(cited)
    if not expected_set:
        return None
    return len(expected_set & cited_set) / len(expected_set)


def score_tool_success(calls: object) -> float | None:
    """Return successful tool calls divided by attempted calls.

    Calls can be ``[{"success": true}, ...]`` or a sequence of booleans.
    """

    if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes)):
        return None
    successes: list[bool] = []
    for call in calls:
        if isinstance(call, Mapping) and isinstance(call.get("success"), bool):
            successes.append(call["success"])
        elif isinstance(call, bool):
            successes.append(call)
    if not successes:
        return None
    return sum(successes) / len(successes)


def score_cost_usd(record: Mapping[str, Any]) -> float | None:
    if isinstance(record.get("cost_usd"), (int, float)):
        return max(0.0, float(record["cost_usd"]))
    if isinstance(record.get("cost_microusd"), (int, float)):
        return max(0.0, float(record["cost_microusd"]) / 1_000_000)
    return None


def score_latency_seconds(record: Mapping[str, Any]) -> float | None:
    value = record.get("latency_seconds")
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    value = record.get("latency_ms")
    if isinstance(value, (int, float)):
        return max(0.0, float(value) / 1000)
    return None


@dataclass(frozen=True)
class CaseMetrics:
    case_id: str
    accuracy: float | None
    citation_score: float | None
    cost_usd: float | None
    latency_seconds: float | None
    tool_success_rate: float | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeRunMetrics:
    """Metrics derived from persisted Agent Run telemetry."""

    run_id: str
    success: bool
    latency_seconds: float | None
    cost_usd: float | None
    citation_score: float | None
    tool_success_rate: float | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def score_runtime_run(
    *,
    run_id: str,
    status: str,
    created_at: datetime | None,
    updated_at: datetime | None,
    cost_microusd: float | None,
    events: Sequence[Mapping[str, Any]] = (),
) -> RuntimeRunMetrics:
    """Calculate observable runtime metrics without treating success as accuracy."""
    latency = None
    if status not in {"queued", "running"} and created_at is not None and updated_at is not None:
        latency = max(0.0, (updated_at - created_at).total_seconds())
    cost = max(0.0, float(cost_microusd) / 1_000_000) if isinstance(cost_microusd, (int, float)) else None

    tool_starts = 0
    tool_ends = 0
    citation_score: float | None = None
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        trace_type = payload.get("type")
        if trace_type == "TOOL_CALL_START":
            tool_starts += 1
        elif trace_type == "TOOL_CALL_END":
            tool_ends += 1
        if event.get("event_type") != "research.evidence_result":
            continue
        claims = payload.get("claims")
        if isinstance(claims, Sequence) and not isinstance(claims, (str, bytes)) and claims:
            valid = [
                isinstance(claim, Mapping)
                and isinstance(claim.get("citations"), Sequence)
                and not isinstance(claim.get("citations"), (str, bytes))
                and bool(claim.get("citations"))
                for claim in claims
            ]
            citation_score = sum(valid) / len(valid)
    tool_success = tool_ends / tool_starts if tool_starts else None
    return RuntimeRunMetrics(
        run_id=run_id,
        success=status == "completed",
        latency_seconds=latency,
        cost_usd=cost,
        citation_score=citation_score,
        tool_success_rate=tool_success,
    )


def aggregate_runtime_metrics(runs: Sequence[RuntimeRunMetrics]) -> dict[str, object]:
    latencies = [run.latency_seconds for run in runs if run.latency_seconds is not None]
    costs = [run.cost_usd for run in runs if run.cost_usd is not None]
    citation = [run.citation_score for run in runs if run.citation_score is not None]
    tool_success = [run.tool_success_rate for run in runs if run.tool_success_rate is not None]
    return {
        "total_research": len(runs),
        "success_rate": sum(run.success for run in runs) / len(runs) if runs else None,
        "average_latency_seconds": _mean(latencies),
        "average_cost_usd": _mean(costs),
        "accuracy": None,
        "citation_score": _mean(citation),
        "tool_success_rate": _mean(tool_success),
        "coverage": {
            "latency": len(latencies),
            "cost": len(costs),
            "citation_score": len(citation),
            "tool_success_rate": len(tool_success),
            "accuracy": 0,
        },
    }


def score_case(record: Mapping[str, Any]) -> CaseMetrics:
    return CaseMetrics(
        case_id=str(record.get("id", "unknown")),
        accuracy=score_accuracy(record.get("expected_facts"), record.get("predicted_facts")),
        citation_score=score_citation(
            record.get("expected_citation_ids"), record.get("cited_citation_ids")
        ),
        cost_usd=score_cost_usd(record),
        latency_seconds=score_latency_seconds(record),
        tool_success_rate=score_tool_success(record.get("tool_calls")),
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_case_metrics(cases: Sequence[CaseMetrics]) -> dict[str, object]:
    """Aggregate case metrics while preserving missing-evidence boundaries."""

    accuracy = [case.accuracy for case in cases if case.accuracy is not None]
    citation = [case.citation_score for case in cases if case.citation_score is not None]
    cost = [case.cost_usd for case in cases if case.cost_usd is not None]
    latency = [case.latency_seconds for case in cases if case.latency_seconds is not None]
    tool_success = [case.tool_success_rate for case in cases if case.tool_success_rate is not None]
    return {
        "accuracy": _mean(accuracy),
        "citation_score": _mean(citation),
        "cost_usd": sum(cost) if cost else None,
        "latency_seconds": _mean(latency),
        "tool_success_rate": _mean(tool_success),
        "coverage": {
            "accuracy": len(accuracy),
            "citation_score": len(citation),
            "cost_usd": len(cost),
            "latency_seconds": len(latency),
            "tool_success_rate": len(tool_success),
        },
    }
