"""Runtime adapters; importing CrewAI is delayed and side-effect constrained."""

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import appdirs  # type: ignore[import-untyped]

from backend.app.agents.flow import ControlledResearchFlow
from backend.app.agents.schemas import AgentRuntime, FlowOutcome, ResearchRequest


def _load_crewai_flow() -> tuple[type[Any], Callable[..., Any]]:
    """Import CrewAI without letting it create an unbounded user-home data directory."""
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    storage_dir = Path(tempfile.gettempdir()) / "investment-agent-crewai"
    storage_dir.mkdir(parents=True, exist_ok=True)
    credential_dir = storage_dir / "credentials"
    credential_dir.mkdir(parents=True, exist_ok=True)
    # CrewAI 1.x also creates a credential key while importing its event listener.
    # Keep that key process-local: this service neither uses CrewAI cloud auth nor
    # accepts an implicit write to a developer's home directory.
    from crewai_core import paths as crewai_paths
    from crewai_core.token_manager import TokenManager

    TokenManager._get_secure_storage_path = staticmethod(lambda: credential_dir)  # type: ignore[method-assign]
    crewai_paths.db_storage_path = lambda: str(storage_dir)
    original_user_data_dir = appdirs.user_data_dir
    appdirs.user_data_dir = lambda *_args, **_kwargs: str(storage_dir)
    try:
        from crewai.flow.flow import Flow, start

        return Flow, start
    finally:
        appdirs.user_data_dir = original_user_data_dir


async def run_with_runtime(
    runtime: AgentRuntime, controlled_flow: ControlledResearchFlow, request: ResearchRequest
) -> FlowOutcome:
    if runtime is AgentRuntime.LANGGRAPH:
        return await controlled_flow.run(request)
    return await _run_crewai_flow(controlled_flow, request)


async def _run_crewai_flow(
    controlled_flow: ControlledResearchFlow, request: ResearchRequest
) -> FlowOutcome:
    Flow, start = _load_crewai_flow()

    class CrewAIResearchFlow(Flow):  # type: ignore[misc,valid-type]
        _skip_auto_memory = True

        @start()
        async def execute(self) -> FlowOutcome:
            return await controlled_flow.run(request)

    flow = CrewAIResearchFlow(suppress_flow_events=True, tracing=False)
    result = await flow.kickoff_async()
    if not isinstance(result, FlowOutcome):
        raise TypeError("CrewAI flow did not return a FlowOutcome")
    return result
