from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentCapability(BaseModel):
    """Offline contract for a candidate specialist; never grants runtime access."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    input_schema: str = Field(min_length=1, max_length=256)
    output_schema: str = Field(min_length=1, max_length=256)
    allowed_tools: tuple[str, ...] = Field(max_length=8)
    max_calls: Literal[1] = 1
    max_cost_microusd: int = Field(gt=0)
    required_eval_suite: str = Field(min_length=1, max_length=256)
    allow_delegation: Literal[False] = False
    read_only: Literal[True] = True

    @field_validator("allowed_tools")
    @classmethod
    def require_unique_tools(cls, tools: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(tools)) != len(tools):
            raise ValueError("allowed tools must be unique")
        if any(not tool.strip() for tool in tools):
            raise ValueError("allowed tools must be named")
        return tools
