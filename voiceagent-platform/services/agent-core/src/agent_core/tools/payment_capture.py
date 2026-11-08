"""Payment capture tool.

This tool never receives the raw card data, and card data is never placed
into the LLM's context. When a caller needs to make a payment, agent-core
hands off to the isolated PCI-scoped payment service (see
compliance/pci/) which plays its own DTMF/audio capture prompts directly
on the call leg and returns only a tokenized result (success/failure and
a payment reference) back into the conversation.

This module is the tool-calling contract between agent-core and that
isolated service, not the payment capture implementation itself.

Idempotency: a network timeout talking to the PCI service does not mean
the charge didn't happen — it means agent-core doesn't know whether it
happened. Retrying blindly risks a double charge; not retrying at all
risks leaving a call stuck on a transient blip. The fix used here is the
standard one: generate one idempotency key per logical `invoke()` call
and send the same key on every retry attempt of that call, so the
PCI-scoped service can recognize a retried request as "the one I already
processed" and return the original result instead of charging again. See
docs/adr/0008 for the reasoning and what's explicitly out of scope (a
process crash between charging and recording the result would need the
key persisted alongside call state — not implemented here).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import ClassVar

import structlog

logger = structlog.get_logger(__name__)


class PciServiceTransientError(Exception):
    """Raised by a pci_service_client implementation for a retryable
    failure (timeout, connection reset) — as opposed to a definitive
    decline, which should come back as a failed PaymentCaptureResult, not
    an exception, since retrying a decline is never correct."""


@dataclass
class PaymentCaptureResult:
    success: bool
    payment_reference: str | None
    failure_reason: str | None = None


class PaymentCaptureTool:
    name = "capture_payment"
    description = (
        "Hands the call off to the isolated PCI-scoped payment service to "
        "collect a payment. Returns only a tokenized result, never raw card data."
    )
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "amount_cents": {
                "type": "integer",
                "description": "Amount to charge, in the minor currency unit (e.g. paise for INR).",
            },
            "currency": {
                "type": "string",
                "description": "ISO 4217 currency code, e.g. INR.",
            },
        },
        "required": ["amount_cents", "currency"],
    }

    def __init__(self, pci_service_client, *, max_attempts: int = 3, retry_backoff_seconds: float = 0.5):
        self._pci_service = pci_service_client
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

    async def invoke(self, *, channel_id: str, amount_cents: int, currency: str) -> PaymentCaptureResult:
        idempotency_key = f"{channel_id}:{uuid.uuid4()}"
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._pci_service.capture(
                    channel_id=channel_id,
                    amount_cents=amount_cents,
                    currency=currency,
                    idempotency_key=idempotency_key,
                )
            except PciServiceTransientError as exc:
                last_error = exc
                logger.warning(
                    "payment_capture_retrying",
                    channel_id=channel_id,
                    attempt=attempt,
                    idempotency_key=idempotency_key,
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._retry_backoff_seconds * attempt)

        return PaymentCaptureResult(
            success=False,
            payment_reference=None,
            failure_reason=f"payment service unavailable after {self._max_attempts} attempts: {last_error}",
        )
