"""Redaction for data leaving the general conversation path into
analytics/QA storage.

compliance/pci/README.md draws a hard boundary around cardholder data
specifically. That boundary doesn't cover everything a caller says on a
banking call — account numbers, OTPs, and similar sensitive-but-not-card
data can still end up in `CallEvent.metadata` (shared/schemas/call_event
.schema.json) on their way to the analytics/QA store, which is a wider
audience than the call itself. This module is a second, narrower net:
pattern-based redaction applied to event metadata before it's emitted,
independent of (and in addition to) the PCI isolation boundary.

Deliberately conservative and pattern-based rather than an ML PII
detector — false positives (redacting something that wasn't actually
sensitive) are cheap here since this only touches analytics metadata, not
the live conversation; false negatives are the expensive failure mode, so
the patterns lean toward over-matching plausible digit runs.
"""

from __future__ import annotations

import re
from typing import Any

# 6-digit OTPs are the dominant convention (banks, UPI); this also catches
# most other one-time-code lengths in the 4-8 digit range.
_OTP_PATTERN = re.compile(r"\b\d{4,8}\b")
# Longer digit runs (account numbers, card-adjacent numbers even though
# actual card capture never reaches this path) — grouped with optional
# spaces/dashes since callers and STT both tend to chunk long numbers.
_LONG_NUMBER_PATTERN = re.compile(r"\b(?:\d[ -]?){9,}\b")

_REDACTED_OTP = "[redacted:otp-like]"
_REDACTED_NUMBER = "[redacted:number]"


def redact_text(text: str) -> str:
    redacted = _LONG_NUMBER_PATTERN.sub(_REDACTED_NUMBER, text)
    redacted = _OTP_PATTERN.sub(_REDACTED_OTP, redacted)
    return redacted


def redact_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Applies redact_text to every string value in a CallEvent's
    metadata object, recursively. Non-string values pass through
    unchanged; this is about digits-shaped-like-secrets in free text, not
    schema-typed fields."""
    if metadata is None:
        return None
    return {key: _redact_value(value) for key, value in metadata.items()}


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return redact_metadata(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value
