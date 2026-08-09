from backend.app.platform.capacity import (
    CapacityEvidence,
    PlatformEvidenceStatus,
    evaluate_platform_scale,
)


def test_less_than_eight_weeks_is_insufficient_evidence() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=7,
            ha_or_rto_missed=True,
            platform_owner="platform-team",
            budget_approved=True,
            rollback_drilled=True,
        )
    )

    assert decision.status is PlatformEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert decision.reasons == ["minimum_observation_window_not_met"]


def test_missing_owner_budget_and_rollback_is_no_go() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(observed_weeks=8, worker_scale_still_violates_slo=True)
    )

    assert decision.status is PlatformEvidenceStatus.NO_GO
    assert set(decision.reasons) == {
        "platform_owner_missing",
        "budget_not_approved",
        "rollback_not_drilled",
    }


def test_no_technical_trigger_is_no_go() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=8,
            platform_owner="platform-team",
            budget_approved=True,
            rollback_drilled=True,
        )
    )

    assert decision.status is PlatformEvidenceStatus.NO_GO
    assert decision.technical_triggers == []
    assert decision.reasons == ["technical_trigger_missing"]


def test_fully_evidenced_platform_candidate_is_ready_for_adr_not_deployment() -> None:
    decision = evaluate_platform_scale(
        CapacityEvidence(
            observed_weeks=12,
            release_boundary_incidents=2,
            database_optimized_still_insufficient=True,
            platform_owner="platform-team",
            budget_approved=True,
            rollback_drilled=True,
        )
    )

    assert decision.status is PlatformEvidenceStatus.EVIDENCE_READY
    assert decision.technical_triggers == [
        "release_boundary_incidents",
        "database_optimized_still_insufficient",
    ]
    assert decision.reasons == []
