import asyncio

from backend.app.tools.base import ToolDefinition
from backend.app.tools.policy import ToolPrincipal, authorize


class UnknownToolError(Exception):
    """A tool name is not in the fixed application whitelist."""


class DuplicateToolError(ValueError):
    """A duplicate registration would otherwise silently replace a policy."""


class ToolTimeoutError(TimeoutError):
    """A bounded read tool exceeded its declared execution budget."""


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition]) -> None:
        names = [definition.name for definition in definitions]
        if len(names) != len(set(names)):
            raise DuplicateToolError("duplicate tool registrations are forbidden")
        self._definitions = {definition.name: definition for definition in definitions}

    def definition(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as error:
            raise UnknownToolError from error

    async def invoke(
        self, name: str, raw_input: dict[str, object], principal: ToolPrincipal, calls_so_far: int
    ) -> object:
        definition = self.definition(name)
        validated_input = definition.input_model.model_validate(raw_input)
        authorize(definition, principal, calls_so_far)
        try:
            async with asyncio.timeout(definition.timeout_seconds):
                output = await definition.handler(validated_input)
        except TimeoutError as error:
            raise ToolTimeoutError("tool_timeout") from error
        return definition.output_model.model_validate(output)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._definitions)
