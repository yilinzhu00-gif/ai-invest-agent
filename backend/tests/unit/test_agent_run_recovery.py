from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, DevelopmentPrincipal


class FakeSession:
    async def execute(self, *_: object, **__: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _: object) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeRepository:
    def __init__(self, run: SimpleNamespace, message: SimpleNamespace | None = None) -> None:
        self.session = FakeSession()
        self.run = run
        self.message = message
        self.events: list[tuple[str, dict[str, object]]] = []
        self.memories: list[dict[str, object]] = []

    async def get_run(self, _: object, *, lock: bool = False) -> SimpleNamespace:
        del lock
        return self.run

    async def append_event(
        self, _: object, event_type: str, payload: dict[str, object]
    ) -> SimpleNamespace:
        self.events.append((event_type, payload))
        return SimpleNamespace()

    async def latest_message(self, _: object, __: str) -> SimpleNamespace | None:
        return self.message

    async def create_memory(self, **kwargs: object) -> SimpleNamespace:
        self.memories.append(kwargs)
        return SimpleNamespace(id=uuid4())

    async def list_memories(self, **_: object) -> list[object]:
        return []


def _run(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), workspace_id="workspace-a", principal_id="user-a", status=status, attempt_count=2
    )


@pytest.mark.asyncio
async def test_approval_is_the_only_path_that_persists_a_scoped_memory() -> None:
    run = _run(AgentRunStatus.AWAITING_CONFIRMATION.value)
    repository = FakeRepository(run, SimpleNamespace(content="人工确认后的研究摘要"))
    service = AgentRunService(repository)  # type: ignore[arg-type]

    confirmed = await service.confirm(
        run.id, DevelopmentPrincipal(principal_id="user-a", workspace_id="workspace-a"), approve=True
    )

    assert confirmed.status == AgentRunStatus.COMPLETED.value
    assert repository.memories == [
        {
            "workspace_id": "workspace-a",
            "principal_id": "user-a",
            "source_run_id": run.id,
            "content": "人工确认后的研究摘要",
        }
    ]
    assert [event for event, _ in repository.events] == ["memory.saved", "run.confirmed"]


@pytest.mark.asyncio
async def test_rejection_never_writes_memory_and_recovery_requeues_only_failed_runs() -> None:
    awaiting = _run(AgentRunStatus.AWAITING_CONFIRMATION.value)
    repository = FakeRepository(awaiting, SimpleNamespace(content="不应保存"))
    service = AgentRunService(repository)  # type: ignore[arg-type]

    rejected = await service.confirm(
        awaiting.id, DevelopmentPrincipal(principal_id="user-a", workspace_id="workspace-a"), approve=False
    )
    assert rejected.status == AgentRunStatus.REJECTED.value
    assert repository.memories == []

    failed = _run(AgentRunStatus.FAILED.value)
    recovery_repository = FakeRepository(failed)
    recovered = await AgentRunService(recovery_repository).recover(  # type: ignore[arg-type]
        failed.id, DevelopmentPrincipal(principal_id="user-a", workspace_id="workspace-a")
    )
    assert recovered.status == AgentRunStatus.QUEUED.value
    assert recovery_repository.events == [
        ("run.recovery_queued", {"attempt": 2, "source": "human_confirmation"})
    ]
