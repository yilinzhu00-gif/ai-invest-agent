import argparse
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from math import ceil
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BackendModule(StrEnum):
    OCR = "ocr"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    GENERATION = "generation"


class BackendKind(StrEnum):
    CPU = "cpu"
    CLOUD = "cloud"
    GPU = "gpu"


class BackendEvidenceStatus(StrEnum):
    EVIDENCE_READY = "EVIDENCE_READY"
    NO_GO = "NO_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class BackendDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    module: BackendModule
    kind: BackendKind


class BenchmarkObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str = Field(min_length=1, max_length=128)
    case_id: str = Field(min_length=1, max_length=256)
    backend: BackendDescriptor
    success: bool
    quality_score: float = Field(ge=0, le=1)
    latency_ms: int = Field(ge=0)
    cost_microusd: int = Field(ge=0)
    failure_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_failure_code_for_failed_observation(self) -> "BenchmarkObservation":
        if not self.success and not self.failure_code:
            raise ValueError("failed observations require a failure code")
        if self.success and self.failure_code:
            raise ValueError("successful observations cannot have a failure code")
        return self


class BenchmarkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: BackendDescriptor
    dataset_version: str
    cases: int
    evidence_sufficient: bool
    success_rate: float
    average_quality: float
    p50_latency_ms: int
    p95_latency_ms: int
    average_cost_microusd: float
    serial_throughput_per_second: float
    failure_codes: dict[str, int]


class BackendComparisonPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_cases: int = Field(default=100, ge=1)
    minimum_candidate_quality: float = Field(default=0.9, ge=0, le=1)
    maximum_quality_drop: float = Field(default=0.01, ge=0, le=1)


class BackendComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BackendEvidenceStatus
    control: BenchmarkSummary
    candidate: BenchmarkSummary
    quality_delta: float
    reasons: list[str]


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    return ordered[max(ceil(percentile * len(ordered)) - 1, 0)]


def summarize_observations(
    observations: Sequence[BenchmarkObservation], *, minimum_cases: int
) -> BenchmarkSummary:
    if not observations:
        raise ValueError("at least one benchmark observation is required")
    descriptors = {observation.backend for observation in observations}
    if len(descriptors) != 1:
        raise ValueError("summary requires observations from one backend")
    dataset_versions = {observation.dataset_version for observation in observations}
    if len(dataset_versions) != 1:
        raise ValueError("summary requires one dataset version")
    case_ids = [observation.case_id for observation in observations]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark case ids must be unique")

    total_latency_ms = sum(observation.latency_ms for observation in observations)
    throughput = len(observations) * 1000 / total_latency_ms if total_latency_ms else 0.0
    failures = Counter(
        observation.failure_code for observation in observations if observation.failure_code
    )
    return BenchmarkSummary(
        backend=next(iter(descriptors)),
        dataset_version=next(iter(dataset_versions)),
        cases=len(observations),
        evidence_sufficient=len(observations) >= minimum_cases,
        success_rate=round(sum(item.success for item in observations) / len(observations), 6),
        average_quality=round(
            sum(item.quality_score for item in observations) / len(observations), 6
        ),
        p50_latency_ms=_nearest_rank([item.latency_ms for item in observations], 0.5),
        p95_latency_ms=_nearest_rank([item.latency_ms for item in observations], 0.95),
        average_cost_microusd=round(
            sum(item.cost_microusd for item in observations) / len(observations), 2
        ),
        serial_throughput_per_second=round(throughput, 2),
        failure_codes=dict(sorted(failures.items())),
    )


def compare_backends(
    control: Sequence[BenchmarkObservation],
    candidate: Sequence[BenchmarkObservation],
    policy: BackendComparisonPolicy,
) -> BackendComparison:
    control_summary = summarize_observations(control, minimum_cases=policy.minimum_cases)
    candidate_summary = summarize_observations(candidate, minimum_cases=policy.minimum_cases)
    if control_summary.dataset_version != candidate_summary.dataset_version:
        raise ValueError("backends must use the same dataset version")
    if control_summary.backend.module is not candidate_summary.backend.module:
        raise ValueError("backends must implement the same module")
    if {item.case_id for item in control} != {item.case_id for item in candidate}:
        raise ValueError("backends must use identical case sets")

    quality_delta = round(
        candidate_summary.average_quality - control_summary.average_quality, 6
    )
    if not control_summary.evidence_sufficient or not candidate_summary.evidence_sufficient:
        return BackendComparison(
            status=BackendEvidenceStatus.INSUFFICIENT_EVIDENCE,
            control=control_summary,
            candidate=candidate_summary,
            quality_delta=quality_delta,
            reasons=["minimum_cases_not_met"],
        )

    reasons: list[str] = []
    if candidate_summary.average_quality < policy.minimum_candidate_quality:
        reasons.append("candidate_below_quality_floor")
    if -quality_delta > policy.maximum_quality_drop:
        reasons.append("quality_drop_exceeded")
    return BackendComparison(
        status=BackendEvidenceStatus.NO_GO if reasons else BackendEvidenceStatus.EVIDENCE_READY,
        control=control_summary,
        candidate=candidate_summary,
        quality_delta=quality_delta,
        reasons=reasons,
    )


def _read_observations(path: Path) -> list[BenchmarkObservation]:
    return [
        BenchmarkObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    comparison = compare_backends(
        _read_observations(args.control),
        _read_observations(args.candidate),
        BackendComparisonPolicy(),
    )
    print(comparison.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
