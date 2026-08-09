import argparse
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from math import ceil
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.evidence.provenance import SHA256_PATTERN, EvidenceKind, EvidenceProvenance


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
    case_sha256: str = Field(pattern=SHA256_PATTERN)
    arm: AgentExperimentArm
    experiment_id: UUID
    provenance: EvidenceProvenance
    model_id: str = Field(min_length=1, max_length=128)
    token_budget: int = Field(gt=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    hard_gate_passed: bool
    latency_ms: int = Field(ge=0)
    cost_microusd: int = Field(ge=0)
    failure_type: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_usage_within_budget(self) -> "ExperimentObservation":
        if self.input_tokens + self.output_tokens > self.token_budget:
            raise ValueError("observed token usage exceeds registered budget")
        return self


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
    evidence_kind: EvidenceKind
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
    experiment_ids = {observation.experiment_id for observation in observations}
    if len(experiment_ids) != 1:
        raise ValueError("observations must belong to one registered experiment")
    evidence_kinds = {observation.provenance.kind for observation in observations}
    if len(evidence_kinds) != 1:
        raise ValueError("experiment arms must use one evidence kind")
    evidence_kind = next(iter(evidence_kinds))

    case_sets: dict[AgentExperimentArm, set[str]] = {}
    for arm, arm_observations in grouped.items():
        case_ids = [observation.case_id for observation in arm_observations]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError(f"duplicate case id in {arm.value} arm")
        case_sets[arm] = set(case_ids)
    if len({frozenset(case_ids) for case_ids in case_sets.values()}) != 1:
        raise ValueError("experiment arms must use identical case sets")
    case_digests = {
        arm: {item.case_id: item.case_sha256 for item in arm_observations}
        for arm, arm_observations in grouped.items()
    }
    if len({tuple(sorted(digests.items())) for digests in case_digests.values()}) != 1:
        raise ValueError("experiment arms must use identical case inputs")

    token_matched_by_case = {
        item.case_id: item for item in grouped[AgentExperimentArm.TOKEN_MATCHED]
    }
    specialist_by_case = {item.case_id: item for item in grouped[AgentExperimentArm.SPECIALIST]}
    if any(
        (token_matched_by_case[case_id].model_id, token_matched_by_case[case_id].token_budget)
        != (specialist_by_case[case_id].model_id, specialist_by_case[case_id].token_budget)
        for case_id in case_sets[AgentExperimentArm.TOKEN_MATCHED]
    ):
        raise ValueError("token-matched and specialist arms require the same model and token budget")

    matched_cases = len(next(iter(case_sets.values())))
    metrics = {arm: _metrics(arm_observations) for arm, arm_observations in grouped.items()}
    specialist = metrics[AgentExperimentArm.SPECIALIST]
    specialist_passed = sum(
        item.hard_gate_passed for item in grouped[AgentExperimentArm.SPECIALIST]
    )
    token_matched_passed = sum(
        item.hard_gate_passed for item in grouped[AgentExperimentArm.TOKEN_MATCHED]
    )
    exact_improvement_pp = (specialist_passed - token_matched_passed) * 100 / matched_cases
    exact_specialist_average_cost = (
        sum(item.cost_microusd for item in grouped[AgentExperimentArm.SPECIALIST])
        / matched_cases
    )
    improvement_pp = round(exact_improvement_pp, 2)

    if evidence_kind is not EvidenceKind.REAL_ATTESTED:
        return ExperimentDecision(
            status=ExperimentDecisionStatus.INSUFFICIENT_EVIDENCE,
            matched_cases=matched_cases,
            hard_gate_improvement_pp=improvement_pp,
            metrics=metrics,
            evidence_kind=evidence_kind,
            reasons=["real_attested_evidence_required"],
        )

    if matched_cases < policy.minimum_cases:
        return ExperimentDecision(
            status=ExperimentDecisionStatus.INSUFFICIENT_EVIDENCE,
            matched_cases=matched_cases,
            hard_gate_improvement_pp=improvement_pp,
            metrics=metrics,
            evidence_kind=evidence_kind,
            reasons=["minimum_cases_not_met"],
        )

    reasons: list[str] = []
    if exact_improvement_pp < policy.minimum_improvement_pp:
        reasons.append("hard_gate_improvement_below_threshold")
    if specialist.p95_latency_ms > policy.max_p95_latency_ms:
        reasons.append("p95_latency_budget_exceeded")
    if exact_specialist_average_cost > policy.max_average_cost_microusd:
        reasons.append("average_cost_budget_exceeded")
    return ExperimentDecision(
        status=ExperimentDecisionStatus.NO_GO if reasons else ExperimentDecisionStatus.GO,
        matched_cases=matched_cases,
        hard_gate_improvement_pp=improvement_pp,
        metrics=metrics,
        evidence_kind=evidence_kind,
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
