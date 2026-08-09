from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.security.classification import DataClassification


class CandidateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TrainingSplit(StrEnum):
    TRAIN = "train"
    HOLDOUT = "holdout"


class TrainingReadinessStatus(StrEnum):
    EVIDENCE_READY = "EVIDENCE_READY"
    NO_GO = "NO_GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class TrainingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1, max_length=128)
    task_type: str = Field(min_length=1, max_length=128)
    source_run_id: UUID
    workspace_id: UUID
    classification: DataClassification
    input_text: str = Field(min_length=1, max_length=20_000)
    expected_output: str = Field(min_length=1, max_length=20_000)
    tool_names: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    labels: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    approver_id: str | None = Field(default=None, max_length=128)
    approved_at: datetime | None = None
    license_id: str = Field(min_length=1, max_length=256)
    license_allows_training: bool
    training_authorized: bool
    split_group: str = Field(min_length=1, max_length=256)
    status: CandidateStatus

    @field_validator("tool_names", "labels")
    @classmethod
    def require_unique_named_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValueError("tuple values must be unique and named")
        return values

    @model_validator(mode="after")
    def require_approval_metadata(self) -> Self:
        if self.status is CandidateStatus.APPROVED and (
            not self.approver_id or self.approved_at is None
        ):
            raise ValueError("approved candidates require approver and timestamp")
        return self


class TrainingExportPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_train: int = Field(default=300, ge=1)
    minimum_holdout: int = Field(default=50, ge=0)
    maximum_holdout: int = Field(default=100, ge=0)

    @model_validator(mode="after")
    def require_ordered_holdout_bounds(self) -> Self:
        if self.maximum_holdout < self.minimum_holdout:
            raise ValueError("maximum holdout must be at least the minimum")
        return self


class TrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_id: str
    task_type: str
    source_run_id: UUID
    classification: DataClassification
    input_text: str
    expected_output: str
    tool_names: tuple[str, ...]
    labels: tuple[str, ...]
    license_id: str
    split_group: str
    split: TrainingSplit


class TrainingExportReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TrainingReadinessStatus
    train_count: int
    holdout_count: int
    rejected: dict[str, list[str]]
    dataset_hash: str | None
    examples: list[TrainingExample]
    reasons: list[str]
