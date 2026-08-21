"""Debate role contracts, independent from model-provider details."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DebatePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["bull", "bear", "moderator"]
    claim: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()

