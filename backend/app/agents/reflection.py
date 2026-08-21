"""Reflection/review contracts for evidence-gated output."""

from pydantic import BaseModel, ConfigDict, Field


class ReflectionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accuracy: int = Field(ge=0, le=10)
    logic: int = Field(ge=0, le=10)
    missing: tuple[str, ...] = ()


class ReflectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    issues: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    accuracy: int = Field(default=0, ge=0, le=10)
    logic: int = Field(default=0, ge=0, le=10)
    missing: tuple[str, ...] = ()
    score: ReflectionScore | None = None
