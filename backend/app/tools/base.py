from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    required_permission: str
    data_classification: str
    access: str
    idempotent: bool
    timeout_seconds: int
    max_calls_per_run: int
    handler: Callable[[BaseModel], Awaitable[BaseModel]]
