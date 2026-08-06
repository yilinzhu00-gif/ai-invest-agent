from dataclasses import dataclass

from backend.app.tools.base import ToolDefinition


class ToolPolicyError(Exception):
    """Tool access fails closed without exposing internal details."""


@dataclass(frozen=True)
class ToolPrincipal:
    workspace_id: str
    permissions: frozenset[str]


def authorize(definition: ToolDefinition, principal: ToolPrincipal, calls_so_far: int) -> None:
    if definition.access != "read" or definition.required_permission not in principal.permissions:
        raise ToolPolicyError("tool_not_authorized")
    if calls_so_far >= definition.max_calls_per_run:
        raise ToolPolicyError("tool_call_limit_exceeded")
