import pytest

from backend.app.models.gateway import ModelBudgetExceeded, enforce_budget, retryable_provider_error
from backend.app.models.schemas import ModelUsage


def test_retry_policy_allows_only_transient_provider_failures() -> None:
    """Retrying auth/validation failures would waste budget and hide configuration defects."""
    assert retryable_provider_error(status_code=429, error_code=None) is True
    assert retryable_provider_error(status_code=503, error_code=None) is True
    assert retryable_provider_error(status_code=401, error_code=None) is False
    assert retryable_provider_error(status_code=400, error_code="invalid_request") is False


@pytest.mark.asyncio
async def test_gateway_stops_after_two_transient_retries() -> None:
    """A third retry after the allowed two must surface the provider failure."""
    from backend.app.models.gateway import run_with_retry

    attempts = 0

    async def unavailable() -> str:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("provider_unavailable")

    with pytest.raises(RuntimeError, match="provider_unavailable"):
        await run_with_retry(unavailable, should_retry=lambda _: True)
    assert attempts == 3


def test_budget_rejects_excess_tokens_or_cost_before_a_run_can_continue() -> None:
    """Ignoring either accounting threshold would permit an unbounded model Run."""
    usage = ModelUsage(provider="mock", model="mock-chat", input_tokens=8, output_tokens=5, cost_microusd=11)

    with pytest.raises(ModelBudgetExceeded, match="token_budget_exceeded"):
        enforce_budget(usage, max_tokens=12, max_cost_microusd=20)
    with pytest.raises(ModelBudgetExceeded, match="cost_budget_exceeded"):
        enforce_budget(usage, max_tokens=20, max_cost_microusd=10)
