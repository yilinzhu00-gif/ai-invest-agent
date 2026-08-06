from backend.app.tools.base import ToolDefinition
from backend.app.tools.policy import ToolPrincipal, authorize


class UnknownToolError(Exception):
    """A tool name is not in the fixed application whitelist."""


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition]) -> None:
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
        output = await definition.handler(validated_input)
        return definition.output_model.model_validate(output)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._definitions)
