"""Celery task entrypoints: arguments are opaque durable IDs, never user input."""

import asyncio

from backend.app.core.config import Settings
from backend.app.workers.agent_runs import (
    RetryableWorkerError,
    execute_claimed_agent_run,
    fail_agent_run,
    schedule_agent_run_retry,
)
from backend.app.workers.celery_app import app
from backend.app.workers.retry import retry_delay_seconds


@app.task(name="backend.app.workers.tasks.agent.run", bind=True, acks_late=True)
def run_agent(self: object, run_id: str, workspace_id: str, principal_id: str) -> str:
    """Execute the durable lifecycle; duplicate deliveries lose the atomic database claim."""
    settings = Settings()
    try:
        return asyncio.run(
            execute_claimed_agent_run(
                run_id=run_id,
                workspace_id=workspace_id,
                principal_id=principal_id,
                settings=settings,
            )
        )
    except RetryableWorkerError as error:
        scheduled = asyncio.run(
            schedule_agent_run_retry(
                run_id=run_id,
                workspace_id=workspace_id,
                principal_id=principal_id,
                error_code=error.error_code,
                settings=settings,
            )
        )
        if not scheduled:
            return "not_retried"
        retries = int(getattr(getattr(self, "request", None), "retries", 0))
        raise self.retry(exc=error, countdown=retry_delay_seconds(retries + 1), max_retries=3)  # type: ignore[attr-defined]
    except Exception:
        asyncio.run(
            fail_agent_run(
                run_id=run_id,
                workspace_id=workspace_id,
                principal_id=principal_id,
                error_code="worker_unhandled",
                settings=settings,
            )
        )
        raise
