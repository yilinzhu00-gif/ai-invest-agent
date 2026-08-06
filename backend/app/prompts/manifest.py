"""Load immutable prompt metadata and assemble a bounded context."""

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptManifest:
    prompt_id: str
    version: str
    sha256: str
    required_variables: tuple[str, ...]
    output_schema: str
    evaluation_version: str


def load_prompt_manifest(prompt_id: str, version: str) -> PromptManifest:
    path = Path(__file__).parent / prompt_id / version / "system.md"
    contents = path.read_bytes()
    return PromptManifest(
        prompt_id=prompt_id,
        version=version,
        sha256=hashlib.sha256(contents).hexdigest(),
        required_variables=("current_request",),
        output_schema="json",
        evaluation_version="offline-v1",
    )


def build_context(
    *,
    safety_rules: str,
    current_request: str,
    run_state: str,
    evidence: list[str],
    conversation_summary: str,
    max_characters: int,
) -> str:
    """Keep mandatory safety/current content before optional run context."""
    mandatory = f"{safety_rules}\n{current_request}"
    if len(mandatory) > max_characters:
        raise ValueError("context_budget_exceeded")
    parts = [mandatory]
    for value in [run_state, *evidence, conversation_summary]:
        candidate = "\n".join([*parts, value])
        if len(candidate) <= max_characters:
            parts.append(value)
    return "\n".join(parts)
