"""Celery configuration with isolated queues and no result-backend business state."""

from celery import Celery  # type: ignore[import-untyped]


def create_celery_app(broker_url: str = "redis://localhost:6379/0") -> Celery:
    app = Celery("investment_agent", broker=broker_url)
    app.conf.update(
        task_default_queue="agent",
        task_routes={
            "backend.app.workers.tasks.agent.*": {"queue": "agent"},
            "backend.app.workers.tasks.ingestion.*": {"queue": "ingestion"},
            "backend.app.workers.tasks.ocr.*": {"queue": "ocr"},
            "backend.app.workers.tasks.embedding.*": {"queue": "embedding"},
        },
        task_acks_late=True,
        task_ignore_result=True,
        task_soft_time_limit=170,
        task_time_limit=180,
        worker_prefetch_multiplier=1,
    )
    return app
