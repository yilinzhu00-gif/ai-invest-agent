import pytest
from pydantic import BaseModel

from backend.app.tools.base import ToolDefinition
from backend.app.tools.policy import ToolPolicyError, ToolPrincipal
from backend.app.tools.registry import ToolRegistry, UnknownToolError


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
