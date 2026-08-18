def should_retry(*, status_code: int | None, error_code: str | None) -> bool:
    return error_code in {"connection_reset", "provider_temporarily_unavailable", "run_timeout"} or status_code == 429 or (
        status_code is not None and 500 <= status_code <= 599
    )


def retry_delay_seconds(attempt: int) -> int:
    """Bounded exponential backoff suitable for explicit Celery retry requests."""
    return min(2 ** max(attempt - 1, 0), 60)
