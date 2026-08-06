"""Provider-independent retry helpers and gateway protocol."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from backend.app.models.schemas import ModelUsage


class ModelGateway(Protocol):
    """P2 model boundary; concrete adapters are added behind this protocol."""


class ModelBudgetExceeded(Exception):
    """A Run exceeded its configured token or cost allowance."""


def enforce_budget(usage: ModelUsage, *, max_tokens: int, max_cost_microusd: int) -> None:
    if usage.input_tokens + usage.output_tokens > max_tokens:
        raise ModelBudgetExceeded("token_budget_exceeded")
    if usage.cost_microusd > max_cost_microusd:
        raise ModelBudgetExceeded("cost_budget_exceeded")


def retryable_provider_error(*, status_code: int | None, error_code: str | None) -> bool:
    """Classify only bounded, transient provider failures as retryable."""
    if error_code in {"connection_reset", "connection_reset_by_peer"}:
        return True
    return status_code == 429 or (status_code is not None and 500 <= status_code <= 599)


async def run_with_retry[T](
    operation: Callable[[], Awaitable[T]], should_retry: Callable[[Exception], bool]
) -> T:
    """Run once plus at most two retries without hiding non-transient failures."""
    for attempt in range(3):
        try:
            return await operation()
        except Exception as error:
            if attempt == 2 or not should_retry(error):
                raise
    raise RuntimeError("unreachable")
