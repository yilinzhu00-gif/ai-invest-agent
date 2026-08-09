import argparse
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from math import ceil
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class AgentExperimentArm(StrEnum):
    BASELINE = "baseline"
    TOKEN_MATCHED = "token_matched"
    SPECIALIST = "specialist"


class ExperimentDecisionStatus(StrEnum):
    GO = "GO"
    NO_GO = "NO_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ExperimentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=256)
    arm: AgentExperimentArm
    hard_gate_passed: bool
    latency_ms: int = Field(ge=0)
    cost_microusd: int = Field(ge=0)
    failure_type: str | None = Field(default=None, max_length=128)


class ExperimentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_cases: int = Field(default=100, ge=1)
    minimum_improvement_pp: float = Field(default=5.0, ge=0)
    max_p95_latency_ms: int = Field(default=120_000, gt=0)
    max_average_cost_microusd: float = Field(default=100_000, ge=0)


class ArmMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: int
    hard_gate_pass_rate: float
    p95_latency_ms: int
    average_cost_microusd: float
    failure_types: dict[str, int]


class ExperimentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExperimentDecisionStatus
    matched_cases: int
    hard_gate_improvement_pp: float
    metrics: dict[AgentExperimentArm, ArmMetrics]
    reasons: list[str]


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    return ordered[max(ceil(percentile * len(ordered)) - 1, 0)]


def _metrics(observations: Sequence[ExperimentObservation]) -> ArmMetrics:
    passed = sum(observation.hard_gate_passed for observation in observations)
    failures = Counter(
        observation.failure_type
        for observation in observations
        if not observation.hard_gate_passed and observation.failure_type
    )
    return ArmMetrics(
        cases=len(observations),
        hard_gate_pass_rate=round(passed / len(observations), 6),
        p95_latency_ms=_nearest_rank([item.latency_ms for item in observations], 0.95),
        average_cost_microusd=round(
            sum(item.cost_microusd for item in observations) / len(observations), 2
        ),
        failure_types=dict(sorted(failures.items())),
    )


def evaluate_controlled_experiment(
    observations: Sequence[ExperimentObservation], policy: ExperimentPolicy
) -> ExperimentDecision:
    grouped = {
        arm: [observation for observation in observations if observation.arm is arm]
        for arm in AgentExperimentArm
    }
    if any(not arm_observations for arm_observations in grouped.values()):
        raise ValueError("all three experiment arms are required")

    case_sets: dict[AgentExperimentArm, set[str]] = {}
    for arm, arm_observations in grouped.items():
        case_ids = [observation.case_id for observation in arm_observations]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError(f"duplicate case id in {arm.value} arm")
        case_sets[arm] = set(case_ids)
    if len({frozenset(case_ids) for case_ids in case_sets.values()}) != 1:
        raise ValueError("experiment arms must use identical case sets")

    matched_cases = len(next(iter(case_sets.values())))
    metrics = {arm: _metrics(arm_observations) for arm, arm_observations in grouped.items()}
    specialist = metrics[AgentExperimentArm.SPECIALIST]
    token_matched = metrics[AgentExperimentArm.TOKEN_MATCHED]
    improvement_pp = round(
        (specialist.hard_gate_pass_rate - token_matched.hard_gate_pass_rate) * 100, 2
    )

    if matched_cases < policy.minimum_cases:
        return ExperimentDecision(
            status=ExperimentDecisionStatus.INSUFFICIENT_EVIDENCE,
            matched_cases=matched_cases,
            hard_gate_improvement_pp=improvement_pp,
            metrics=metrics,
            reasons=["minimum_cases_not_met"],
        )

    reasons: list[str] = []
    if improvement_pp < policy.minimum_improvement_pp:
        reasons.append("hard_gate_improvement_below_threshold")
    if specialist.p95_latency_ms > policy.max_p95_latency_ms:
        reasons.append("p95_latency_budget_exceeded")
    if specialist.average_cost_microusd > policy.max_average_cost_microusd:
        reasons.append("average_cost_budget_exceeded")
    return ExperimentDecision(
        status=ExperimentDecisionStatus.NO_GO if reasons else ExperimentDecisionStatus.GO,
        matched_cases=matched_cases,
        hard_gate_improvement_pp=improvement_pp,
        metrics=metrics,
        reasons=reasons,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    observations = [
        ExperimentObservation.model_validate_json(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decision = evaluate_controlled_experiment(observations, ExperimentPolicy())
    print(decision.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
