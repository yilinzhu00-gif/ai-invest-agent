from backend.app.workers.celery_app import create_celery_app

app = create_celery_app()


@app.task(name="backend.app.workers.tasks.agent.run", bind=True, acks_late=True)
def run_agent(self: object, run_id: str) -> str:
    """Queue boundary: durable state remains in PostgreSQL and task result is ignored."""
    return run_id
