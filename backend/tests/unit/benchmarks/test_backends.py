import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
from backend.app.evidence.provenance import EvidenceKind, EvidenceProvenance

_DATASET_SHA256 = "d" * 64


def _provenance(kind: EvidenceKind = EvidenceKind.REAL_ATTESTED) -> EvidenceProvenance:
    return EvidenceProvenance(
        kind=kind,
        source_reference="artifact://backend-benchmark/v1",
        artifact_sha256="b" * 64,
        collected_at=datetime(2026, 8, 9, tzinfo=UTC),
        attested_by="reviewer-1" if kind is EvidenceKind.REAL_ATTESTED else None,
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
    provenance: EvidenceProvenance | None = None,
) -> list[BenchmarkObservation]:
    return [
        BenchmarkObservation(
            dataset_version="embedding-holdout/v1",
            dataset_sha256=_DATASET_SHA256,
            case_id=f"{case_prefix}-{index:03d}",
            case_sha256=hashlib.sha256(
                f"{case_prefix}-{index:03d}".encode()
            ).hexdigest(),
            backend=descriptor,
            provenance=provenance or _provenance(),
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
            dataset_sha256=_DATASET_SHA256,
            case_id="a",
            case_sha256=hashlib.sha256(b"a").hexdigest(),
            backend=descriptor,
            provenance=_provenance(),
            success=True,
            quality_score=1.0,
            latency_ms=10,
            cost_microusd=1,
        ),
        BenchmarkObservation(
            dataset_version="v1",
            dataset_sha256=_DATASET_SHA256,
            case_id="b",
            case_sha256=hashlib.sha256(b"b").hexdigest(),
            backend=descriptor,
            provenance=_provenance(),
            success=True,
            quality_score=0.8,
            latency_ms=20,
            cost_microusd=2,
        ),
        BenchmarkObservation(
            dataset_version="v1",
            dataset_sha256=_DATASET_SHA256,
            case_id="c",
            case_sha256=hashlib.sha256(b"c").hexdigest(),
            backend=descriptor,
            provenance=_provenance(),
            success=True,
            quality_score=0.6,
            latency_ms=30,
            cost_microusd=3,
        ),
        BenchmarkObservation(
            dataset_version="v1",
            dataset_sha256=_DATASET_SHA256,
            case_id="d",
            case_sha256=hashlib.sha256(b"d").hexdigest(),
            backend=descriptor,
            provenance=_provenance(),
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


def test_synthetic_benchmark_is_never_evidence_ready() -> None:
    synthetic = _provenance(EvidenceKind.SYNTHETIC)
    control = _observations(_descriptor("cloud"), provenance=synthetic)
    candidate = _observations(
        _descriptor("local", BackendKind.CPU), provenance=synthetic, quality=1.0
    )

    result = compare_backends(control, candidate, BackendComparisonPolicy())

    assert result.status is BackendEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert result.reasons == ["real_attested_evidence_required"]


def test_quality_floor_uses_unrounded_observations() -> None:
    control = _observations(_descriptor("cloud"), quality=0.95)
    candidate = _observations(_descriptor("local", BackendKind.CPU), quality=0.8999996)

    result = compare_backends(control, candidate, BackendComparisonPolicy())

    assert result.status is BackendEvidenceStatus.NO_GO
    assert "candidate_below_quality_floor" in result.reasons


def test_exactly_allowed_quality_drop_is_not_rejected_by_float_error() -> None:
    control = _observations(_descriptor("cloud"), quality=0.95)
    candidate = _observations(_descriptor("local", BackendKind.CPU), quality=0.94)

    result = compare_backends(
        control,
        candidate,
        BackendComparisonPolicy(maximum_quality_drop=0.01),
    )

    assert result.status is BackendEvidenceStatus.EVIDENCE_READY
    assert result.reasons == []


def test_benchmark_observation_requires_dataset_and_case_digests() -> None:
    payload = _observations(_descriptor("cloud"), cases=1)[0].model_dump()
    payload.pop("dataset_sha256")
    payload.pop("case_sha256")

    with pytest.raises(ValidationError):
        BenchmarkObservation.model_validate(payload)


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


def test_comparison_rejects_same_case_id_with_different_input_digest() -> None:
    control = _observations(_descriptor("cloud"))
    candidate = _observations(_descriptor("local", BackendKind.CPU))
    candidate[-1] = candidate[-1].model_copy(update={"case_sha256": "f" * 64})

    with pytest.raises(ValueError, match="identical case inputs"):
        compare_backends(control, candidate, BackendComparisonPolicy())


def test_comparison_rejects_different_dataset_digest() -> None:
    control = _observations(_descriptor("cloud"))
    candidate = [
        item.model_copy(update={"dataset_sha256": "e" * 64})
        for item in _observations(_descriptor("local", BackendKind.CPU))
    ]

    with pytest.raises(ValueError, match="same dataset digest"):
        compare_backends(control, candidate, BackendComparisonPolicy())


def test_zero_latency_observation_is_rejected_as_undefined_throughput() -> None:
    with pytest.raises(ValidationError):
        BenchmarkObservation(
            dataset_version="v1",
            dataset_sha256=_DATASET_SHA256,
            case_id="case-1",
            case_sha256=hashlib.sha256(b"case-1").hexdigest(),
            backend=_descriptor("cloud"),
            provenance=_provenance(),
            success=True,
            quality_score=1.0,
            latency_ms=0,
            cost_microusd=0,
        )
