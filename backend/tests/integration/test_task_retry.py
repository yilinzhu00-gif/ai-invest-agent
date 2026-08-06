import pytest

from backend.app.workers.celery_app import create_celery_app
from backend.app.workers.idempotency import JobRegistry
from backend.app.workers.retry import should_retry


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
