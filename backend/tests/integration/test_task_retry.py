import pytest

from backend.app.domain.agent_runs.service import DevelopmentPrincipal
from backend.app.workers.celery_app import create_celery_app
from backend.app.workers.idempotency import JobRegistry
from backend.app.workers.retry import should_retry
from backend.app.workers.tasks import run_agent


def test_duplicate_idempotency_key_claims_only_one_job() -> None:
    registry = JobRegistry()
    assert registry.claim("workspace-a", "key-1") is True
    assert registry.claim("workspace-a", "key-1") is False


def test_celery_routes_workloads_to_isolated_queues_without_result_backend() -> None:
    app = create_celery_app()
    assert app.conf.task_acks_late is True
    assert app.conf.task_ignore_result is True
    assert app.conf.task_routes["backend.app.workers.tasks.ocr.*"]["queue"] == "ocr"


@pytest.mark.parametrize("status,expected", [(429, True), (503, True), (400, False), (403, False)])
def test_only_transient_provider_errors_are_retried(status: int, expected: bool) -> None:
    assert should_retry(status_code=status, error_code=None) is expected


def test_celery_agent_task_forwards_the_durable_identity_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """The broker payload carries IDs only; the task reloads all durable state from PostgreSQL."""
    async def complete(**_kwargs: object) -> str:
        return "completed"

    monkeypatch.setattr(
        "backend.app.workers.tasks.execute_claimed_agent_run",
        complete,
    )

    result = run_agent.apply(args=("run-1", "workspace-a", "user-1"))

    assert result.successful()
    assert result.result == "completed"


def test_celery_dispatcher_sends_only_durable_identity_ids() -> None:
    from uuid import UUID

    from backend.app.workers.dispatch import CeleryRunExecutor

    calls: list[tuple[tuple[str, str, str], str]] = []

    class Sender:
        def apply_async(self, args: tuple[str, str, str], queue: str) -> None:
            calls.append((args, queue))

    CeleryRunExecutor(Sender()).submit(
        UUID("00000000-0000-0000-0000-000000000001"),
        DevelopmentPrincipal(principal_id="user-1", workspace_id="workspace-a"),
    )

    assert calls == [
        (("00000000-0000-0000-0000-000000000001", "workspace-a", "user-1"), "agent")
    ]


def test_celery_task_persists_a_retry_before_requesting_redelivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.workers.agent_runs import RetryableWorkerError

    async def transient_failure(**_kwargs: object) -> str:
        raise RetryableWorkerError("provider_temporarily_unavailable")

    scheduled: list[str] = []

    async def scheduled_retry(**_kwargs: object) -> bool:
        scheduled.append("persisted")
        return True

    monkeypatch.setattr("backend.app.workers.tasks.execute_claimed_agent_run", transient_failure)
    monkeypatch.setattr("backend.app.workers.tasks.schedule_agent_run_retry", scheduled_retry)

    result = run_agent.apply(args=("run-1", "workspace-a", "user-1"))

    assert result.failed()
    assert isinstance(result.result, RetryableWorkerError)
    assert scheduled == ["persisted"] * 4
