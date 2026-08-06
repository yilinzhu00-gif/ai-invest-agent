"""Stable, provider-neutral request and accounting contracts."""

from pydantic import BaseModel, ConfigDict, Field


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[ModelMessage]
    temperature: float = Field(default=0.3, ge=0, le=2)


class ModelUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_microusd: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)


class ModelResponse(BaseModel):
    text: str
    usage: ModelUsage
