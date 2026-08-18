import pytest
from pydantic import BaseModel

from backend.app.tools.base import ToolDefinition
from backend.app.tools.policy import ToolPolicyError, ToolPrincipal
from backend.app.tools.registry import (
    DuplicateToolError,
    ToolRegistry,
    ToolTimeoutError,
    UnknownToolError,
)


def test_registry_rejects_unknown_tools_before_any_handler_runs() -> None:
    """An arbitrary tool name must never become an implicit code execution surface."""
    registry = ToolRegistry([])

    with pytest.raises(UnknownToolError):
        registry.definition("shell")


@pytest.mark.asyncio
async def test_registry_checks_policy_before_running_handler() -> None:
    """An unauthorized principal must have zero handler execution success."""

    class Input(BaseModel):
        value: str

    class Output(BaseModel):
        value: str

    called = False

    async def handler(_: BaseModel) -> BaseModel:
        nonlocal called
        called = True
        return Output(value="ok")

    registry = ToolRegistry([
        ToolDefinition("score_stock", Input, Output, "tools:read", "INTERNAL", "read", True, 15, 1, handler)
    ])
    with pytest.raises(ToolPolicyError, match="tool_not_authorized"):
        await registry.invoke("score_stock", {"value": "x"}, ToolPrincipal("a", frozenset()), 0)
    assert called is False


def test_registry_rejects_duplicate_names_instead_of_replacing_policy() -> None:
    class Payload(BaseModel):
        value: str

    async def handler(payload: BaseModel) -> BaseModel:
        return payload

    definition = ToolDefinition("same", Payload, Payload, "tools:read", "INTERNAL", "read", True, 1, 1, handler)
    with pytest.raises(DuplicateToolError):
        ToolRegistry([definition, definition])


@pytest.mark.asyncio
async def test_registry_applies_each_tool_timeout() -> None:
    class Payload(BaseModel):
        value: str

    async def handler(_: BaseModel) -> BaseModel:
        await __import__("asyncio").sleep(0.02)
        return Payload(value="late")

    registry = ToolRegistry([
        ToolDefinition("slow", Payload, Payload, "tools:read", "INTERNAL", "read", True, 0.001, 1, handler)
    ])
    with pytest.raises(ToolTimeoutError, match="tool_timeout"):
        await registry.invoke("slow", {"value": "x"}, ToolPrincipal("a", frozenset({"tools:read"})), 0)
