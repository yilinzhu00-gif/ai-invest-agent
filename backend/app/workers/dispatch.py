"""HTTP-to-Celery dispatch adapter for durable Agent Run IDs."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.workers.tasks import run_agent


class AgentTaskSender(Protocol):
    def apply_async(self, args: Sequence[str], queue: str) -> object: ...


class CeleryRunExecutor:
    """Dispatches only durable identities; worker reloads the run from PostgreSQL."""

    development_only = False

    def __init__(self, sender: AgentTaskSender = run_agent) -> None:
        self.sender = sender

    def submit(self, run_id: UUID, principal: RunPrincipal) -> None:
        self.sender.apply_async(
            args=(str(run_id), principal.workspace_id, principal.principal_id), queue="agent"
        )
