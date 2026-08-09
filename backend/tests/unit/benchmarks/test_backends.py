import pytest

from backend.app.benchmarks.backends import (
    BackendComparisonPolicy,
    BackendDescriptor,
    BackendEvidenceStatus,
    BackendKind,
    BackendModule,
    BenchmarkObservation,
    compare_backends,
    summarize_observations,
)


def _descriptor(name: str, kind: BackendKind = BackendKind.CLOUD) -> BackendDescriptor:
    return BackendDescriptor(
        name=name,
        model_version="v1",
        module=BackendModule.EMBEDDING,
        kind=kind,
    )


def _observations(
    descriptor: BackendDescriptor,
    *,
    cases: int = 100,
    quality: float = 0.95,
    case_prefix: str = "case",
) -> list[BenchmarkObservation]:
    return [
        BenchmarkObservation(
            dataset_version="embedding-holdout/v1",
            case_id=f"{case_prefix}-{index:03d}",
            backend=descriptor,
            success=True,
            quality_score=quality,
            latency_ms=20,
            cost_microusd=10,
        )
        for index in range(cases)
    ]


def test_summary_rejects_observations_from_multiple_backends() -> None:
    observations = [
        *_observations(_descriptor("cloud-a"), cases=1),
        *_observations(_descriptor("cloud-b"), cases=1, case_prefix="other"),
    ]

    with pytest.raises(ValueError, match="one backend"):
        summarize_observations(observations, minimum_cases=1)


def test_summary_reports_literal_quality_latency_cost_and_failures() -> None:
    descriptor = _descriptor("cloud-a")
    observations = [
        BenchmarkObservation(
            dataset_version="v1",
            case_id="a",
            backend=descriptor,
            success=True,
            quality_score=1.0,
            latency_ms=10,
            cost_microusd=1,
        ),
        BenchmarkObservation(
            dataset_version="v1",
            case_id="b",
            backend=descriptor,
            success=True,
            quality_score=0.8,
            latency_ms=20,
            cost_microusd=2,
        ),
        BenchmarkObservation(
            dataset_version="v1",
            case_id="c",
            backend=descriptor,
            success=True,
            quality_score=0.6,
            latency_ms=30,
            cost_microusd=3,
        ),
        BenchmarkObservation(
            dataset_version="v1",
            case_id="d",
            backend=descriptor,
            success=False,
            quality_score=0.0,
            latency_ms=40,
            cost_microusd=4,
            failure_code="timeout",
        ),
    ]

    summary = summarize_observations(observations, minimum_cases=4)

    assert summary.evidence_sufficient is True
    assert summary.success_rate == 0.75
    assert summary.average_quality == 0.6
    assert summary.p50_latency_ms == 20
    assert summary.p95_latency_ms == 40
    assert summary.average_cost_microusd == 2.5
    assert summary.serial_throughput_per_second == 40.0
    assert summary.failure_codes == {"timeout": 1}


def test_comparison_is_insufficient_below_registered_case_count() -> None:
    control = _observations(_descriptor("cloud"), cases=99)
    candidate = _observations(_descriptor("local", BackendKind.CPU), cases=99)

    result = compare_backends(control, candidate, BackendComparisonPolicy())

    assert result.status is BackendEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert result.reasons == ["minimum_cases_not_met"]


def test_comparison_rejects_quality_regression() -> None:
    control = _observations(_descriptor("cloud"), quality=0.95)
    candidate = _observations(_descriptor("local", BackendKind.CPU), quality=0.89)

    result = compare_backends(control, candidate, BackendComparisonPolicy())

    assert result.status is BackendEvidenceStatus.NO_GO
    assert set(result.reasons) == {"candidate_below_quality_floor", "quality_drop_exceeded"}


def test_comparable_candidate_is_evidence_ready_but_not_automatically_go() -> None:
    control = _observations(_descriptor("cloud"), quality=0.95)
    candidate = _observations(_descriptor("local", BackendKind.CPU), quality=0.94)

    result = compare_backends(
        control,
        candidate,
        BackendComparisonPolicy(maximum_quality_drop=0.02),
    )

    assert result.status is BackendEvidenceStatus.EVIDENCE_READY
    assert result.quality_delta == -0.01
    assert result.reasons == []


def test_comparison_rejects_different_case_sets() -> None:
    control = _observations(_descriptor("cloud"))
    candidate = _observations(_descriptor("local", BackendKind.CPU), case_prefix="other")

    with pytest.raises(ValueError, match="identical case sets"):
        compare_backends(control, candidate, BackendComparisonPolicy())
