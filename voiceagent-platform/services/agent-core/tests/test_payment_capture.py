import pytest

from agent_core.tools.payment_capture import (
    PaymentCaptureResult,
    PaymentCaptureTool,
    PciServiceTransientError,
)


class FlakyThenSucceedsPciClient:
    def __init__(self, fail_times: int):
        self._fail_times = fail_times
        self.calls: list[dict] = []

    async def capture(self, *, channel_id, amount_cents, currency, idempotency_key):
        self.calls.append(
            {
                "channel_id": channel_id,
                "amount_cents": amount_cents,
                "currency": currency,
                "idempotency_key": idempotency_key,
            }
        )
        if len(self.calls) <= self._fail_times:
            raise PciServiceTransientError("timeout")
        return PaymentCaptureResult(success=True, payment_reference="tok_123")


@pytest.mark.asyncio
async def test_retries_reuse_the_same_idempotency_key_and_eventually_succeed():
    client = FlakyThenSucceedsPciClient(fail_times=1)
    tool = PaymentCaptureTool(client, retry_backoff_seconds=0)

    result = await tool.invoke(channel_id="chan-1", amount_cents=50000, currency="INR")

    assert result.success is True
    assert result.payment_reference == "tok_123"
    assert len(client.calls) == 2
    # Same logical operation, same key on both attempts -> the PCI
    # service can dedupe if the first attempt actually went through.
    assert client.calls[0]["idempotency_key"] == client.calls[1]["idempotency_key"]


@pytest.mark.asyncio
async def test_succeeds_on_first_attempt_without_retrying():
    client = FlakyThenSucceedsPciClient(fail_times=0)
    tool = PaymentCaptureTool(client, retry_backoff_seconds=0)

    result = await tool.invoke(channel_id="chan-1", amount_cents=1000, currency="INR")

    assert result.success is True
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts_and_returns_a_failure_result_not_an_exception():
    client = FlakyThenSucceedsPciClient(fail_times=99)
    tool = PaymentCaptureTool(client, max_attempts=3, retry_backoff_seconds=0)

    result = await tool.invoke(channel_id="chan-1", amount_cents=1000, currency="INR")

    assert result.success is False
    assert result.payment_reference is None
    assert "3 attempts" in result.failure_reason
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_two_separate_invoke_calls_get_different_idempotency_keys():
    client = FlakyThenSucceedsPciClient(fail_times=0)
    tool = PaymentCaptureTool(client, retry_backoff_seconds=0)

    await tool.invoke(channel_id="chan-1", amount_cents=1000, currency="INR")
    await tool.invoke(channel_id="chan-1", amount_cents=2000, currency="INR")

    assert client.calls[0]["idempotency_key"] != client.calls[1]["idempotency_key"]
