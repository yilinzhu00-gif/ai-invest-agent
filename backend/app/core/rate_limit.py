from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class InMemoryTokenBucket:
    """Deterministic local adapter; production uses the same key contract in Redis."""

    def __init__(self, capacity: int, window_seconds: int) -> None:
        self.capacity = capacity
        self.window_seconds = window_seconds
        self._entries: dict[str, tuple[int, float]] = {}

    def allow(self, key: str) -> RateLimitDecision:
        count, started = self._entries.get(key, (0, monotonic()))
        elapsed = monotonic() - started
        if elapsed >= self.window_seconds:
            count, started, elapsed = 0, monotonic(), 0
        if count >= self.capacity:
            return RateLimitDecision(False, max(1, int(self.window_seconds - elapsed)))
        self._entries[key] = (count + 1, started)
        return RateLimitDecision(True, 0)
