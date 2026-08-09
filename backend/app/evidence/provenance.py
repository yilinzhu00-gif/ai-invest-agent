from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class EvidenceKind(StrEnum):
    REAL_ATTESTED = "REAL_ATTESTED"
    SYNTHETIC = "SYNTHETIC"
    UNVERIFIED = "UNVERIFIED"


class EvidenceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EvidenceKind
    source_reference: str = Field(min_length=1, max_length=512)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    collected_at: datetime
    attested_by: str | None = Field(default=None, max_length=128)

    @field_validator("source_reference")
    @classmethod
    def require_named_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence source must be named")
        return normalized

    @field_validator("attested_by")
    @classmethod
    def normalize_attester(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("attester must be named")
        return normalized

    @model_validator(mode="after")
    def require_attester_for_real_evidence(self) -> Self:
        if self.kind is EvidenceKind.REAL_ATTESTED and self.attested_by is None:
            raise ValueError("real evidence requires an attester")
        return self
