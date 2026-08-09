import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.evidence.provenance import SHA256_PATTERN, EvidenceKind, EvidenceProvenance


class PlatformEvidenceStatus(StrEnum):
    EVIDENCE_READY = "EVIDENCE_READY"
    NO_GO = "NO_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CapacityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_weeks: int = Field(ge=0)
    provenance: EvidenceProvenance
    ha_or_rto_missed: bool = False
    worker_scale_still_violates_slo: bool = False
    release_boundary_incidents: int = Field(default=0, ge=0)
    database_optimized_still_insufficient: bool = False
    trigger_evidence_refs: dict[str, str] = Field(default_factory=dict, max_length=4)
    platform_owner: str | None = Field(default=None, max_length=128)
    budget_approval_ref: str | None = Field(default=None, pattern=SHA256_PATTERN)
    rollback_drill_ref: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @field_validator("platform_owner")
    @classmethod
    def normalize_owner(cls, owner: str | None) -> str | None:
        if owner is None:
            return None
        normalized = owner.strip()
        if not normalized:
            raise ValueError("platform owner must be named")
        return normalized

    @field_validator("trigger_evidence_refs")
    @classmethod
    def require_sha256_trigger_refs(cls, refs: dict[str, str]) -> dict[str, str]:
        allowed = {
            "ha_or_rto_missed",
            "worker_scale_still_violates_slo",
            "release_boundary_incidents",
            "database_optimized_still_insufficient",
        }
        if not set(refs).issubset(allowed):
            raise ValueError("unknown technical trigger evidence")
        if any(not re.fullmatch(SHA256_PATTERN, value) for value in refs.values()):
            raise ValueError("trigger evidence references must be sha256 values")
        return refs


class PlatformScaleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PlatformEvidenceStatus
    observed_weeks: int
    evidence_kind: EvidenceKind
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

    if evidence.provenance.kind is not EvidenceKind.REAL_ATTESTED:
        return PlatformScaleDecision(
            status=PlatformEvidenceStatus.INSUFFICIENT_EVIDENCE,
            observed_weeks=evidence.observed_weeks,
            evidence_kind=evidence.provenance.kind,
            technical_triggers=technical_triggers,
            reasons=["real_attested_evidence_required"],
        )

    if evidence.observed_weeks < 8:
        return PlatformScaleDecision(
            status=PlatformEvidenceStatus.INSUFFICIENT_EVIDENCE,
            observed_weeks=evidence.observed_weeks,
            evidence_kind=evidence.provenance.kind,
            technical_triggers=technical_triggers,
            reasons=["minimum_observation_window_not_met"],
        )

    reasons: list[str] = []
    if not technical_triggers:
        reasons.append("technical_trigger_missing")
    for trigger in technical_triggers:
        if trigger not in evidence.trigger_evidence_refs:
            reasons.append(f"technical_trigger_evidence_missing:{trigger}")
    if evidence.platform_owner is None:
        reasons.append("platform_owner_missing")
    if evidence.budget_approval_ref is None:
        reasons.append("budget_approval_missing")
    if evidence.rollback_drill_ref is None:
        reasons.append("rollback_drill_missing")
    return PlatformScaleDecision(
        status=PlatformEvidenceStatus.NO_GO if reasons else PlatformEvidenceStatus.EVIDENCE_READY,
        observed_weeks=evidence.observed_weeks,
        evidence_kind=evidence.provenance.kind,
        technical_triggers=technical_triggers,
        reasons=reasons,
    )
