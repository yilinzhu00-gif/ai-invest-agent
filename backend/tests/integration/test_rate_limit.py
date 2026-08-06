from backend.app.core.rate_limit import InMemoryTokenBucket


def test_http_limit_returns_retry_after_after_120_requests() -> None:
    limiter = InMemoryTokenBucket(capacity=120, window_seconds=60)
    for _ in range(120):
        assert limiter.allow("user-1").allowed is True
    rejected = limiter.allow("user-1")
    assert rejected.allowed is False
    assert rejected.retry_after_seconds > 0
