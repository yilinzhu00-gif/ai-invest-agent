from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlatformEvidenceStatus(StrEnum):
    EVIDENCE_READY = "EVIDENCE_READY"
    NO_GO = "NO_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CapacityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_weeks: int = Field(ge=0)
    ha_or_rto_missed: bool = False
    worker_scale_still_violates_slo: bool = False
    release_boundary_incidents: int = Field(default=0, ge=0)
    database_optimized_still_insufficient: bool = False
    platform_owner: str | None = Field(default=None, max_length=128)
    budget_approved: bool = False
    rollback_drilled: bool = False

    @field_validator("platform_owner")
    @classmethod
    def normalize_owner(cls, owner: str | None) -> str | None:
        if owner is None:
            return None
        normalized = owner.strip()
        if not normalized:
            raise ValueError("platform owner must be named")
        return normalized


class PlatformScaleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PlatformEvidenceStatus
    observed_weeks: int
    technical_triggers: list[str]
    reasons: list[str]


def evaluate_platform_scale(evidence: CapacityEvidence) -> PlatformScaleDecision:
    technical_triggers: list[str] = []
    if evidence.ha_or_rto_missed:
        technical_triggers.append("ha_or_rto_missed")
    if evidence.worker_scale_still_violates_slo:
        technical_triggers.append("worker_scale_still_violates_slo")
    if evidence.release_boundary_incidents:
        technical_triggers.append("release_boundary_incidents")
    if evidence.database_optimized_still_insufficient:
        technical_triggers.append("database_optimized_still_insufficient")

    if evidence.observed_weeks < 8:
        return PlatformScaleDecision(
            status=PlatformEvidenceStatus.INSUFFICIENT_EVIDENCE,
            observed_weeks=evidence.observed_weeks,
            technical_triggers=technical_triggers,
            reasons=["minimum_observation_window_not_met"],
        )

    reasons: list[str] = []
    if not technical_triggers:
        reasons.append("technical_trigger_missing")
    if evidence.platform_owner is None:
        reasons.append("platform_owner_missing")
    if not evidence.budget_approved:
        reasons.append("budget_not_approved")
    if not evidence.rollback_drilled:
        reasons.append("rollback_not_drilled")
    return PlatformScaleDecision(
        status=PlatformEvidenceStatus.NO_GO if reasons else PlatformEvidenceStatus.EVIDENCE_READY,
        observed_weeks=evidence.observed_weeks,
        technical_triggers=technical_triggers,
        reasons=reasons,
    )
