from datetime import UTC, datetime

from backend.app.evidence.provenance import EvidenceKind, EvidenceProvenance
from backend.app.platform.capacity import (
    CapacityEvidence,
    PlatformEvidenceStatus,
    evaluate_platform_scale,
)


def _provenance(kind: EvidenceKind = EvidenceKind.REAL_ATTESTED) -> EvidenceProvenance:
    return EvidenceProvenance(
        kind=kind,
        source_reference="artifact://capacity-report/v1",
        artifact_sha256="c" * 64,
        collected_at=datetime(2026, 8, 9, tzinfo=UTC),
        attested_by="reviewer-1" if kind is EvidenceKind.REAL_ATTESTED else None,
    )


def test_less_than_eight_weeks_is_insufficient_evidence() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=7,
            provenance=_provenance(),
            ha_or_rto_missed=True,
            trigger_evidence_refs={"ha_or_rto_missed": "d" * 64},
            platform_owner="platform-team",
            budget_approval_ref="e" * 64,
            rollback_drill_ref="f" * 64,
        )
    )

    assert decision.status is PlatformEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert decision.reasons == ["minimum_observation_window_not_met"]


def test_missing_owner_budget_and_rollback_is_no_go() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=8,
            provenance=_provenance(),
            worker_scale_still_violates_slo=True,
            trigger_evidence_refs={"worker_scale_still_violates_slo": "d" * 64},
        )
    )

    assert decision.status is PlatformEvidenceStatus.NO_GO
    assert set(decision.reasons) == {
        "platform_owner_missing",
        "budget_approval_missing",
        "rollback_drill_missing",
    }


def test_no_technical_trigger_is_no_go() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=8,
            provenance=_provenance(),
            platform_owner="platform-team",
            budget_approval_ref="e" * 64,
            rollback_drill_ref="f" * 64,
        )
    )

    assert decision.status is PlatformEvidenceStatus.NO_GO
    assert decision.technical_triggers == []
    assert decision.reasons == ["technical_trigger_missing"]


def test_unreferenced_technical_trigger_is_no_go() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=8,
            provenance=_provenance(),
            ha_or_rto_missed=True,
            platform_owner="platform-team",
            budget_approval_ref="e" * 64,
            rollback_drill_ref="f" * 64,
        )
    )

    assert decision.status is PlatformEvidenceStatus.NO_GO
    assert decision.reasons == ["technical_trigger_evidence_missing:ha_or_rto_missed"]


def test_fully_evidenced_platform_candidate_is_ready_for_adr_not_deployment() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=12,
            provenance=_provenance(),
            release_boundary_incidents=2,
            database_optimized_still_insufficient=True,
            trigger_evidence_refs={
                "release_boundary_incidents": "d" * 64,
                "database_optimized_still_insufficient": "e" * 64,
            },
            platform_owner="platform-team",
            budget_approval_ref="f" * 64,
            rollback_drill_ref="1" * 64,
        )
    )

    assert decision.status is PlatformEvidenceStatus.EVIDENCE_READY
    assert decision.technical_triggers == [
        "release_boundary_incidents",
        "database_optimized_still_insufficient",
    ]
    assert decision.reasons == []


def test_synthetic_capacity_claim_is_never_evidence_ready() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=12,
            provenance=_provenance(EvidenceKind.SYNTHETIC),
            ha_or_rto_missed=True,
            trigger_evidence_refs={"ha_or_rto_missed": "d" * 64},
            platform_owner="platform-team",
            budget_approval_ref="e" * 64,
            rollback_drill_ref="f" * 64,
        )
    )

    assert decision.status is PlatformEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert decision.reasons == ["real_attested_evidence_required"]
