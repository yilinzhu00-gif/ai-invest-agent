def should_retry(*, status_code: int | None, error_code: str | None) -> bool:
    return error_code in {"connection_reset", "provider_temporarily_unavailable"} or status_code == 429 or (
        status_code is not None and 500 <= status_code <= 599
    )
