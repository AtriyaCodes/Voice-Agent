"""Streaming speech to text.

Defines the provider-agnostic interface voice-pipeline uses for STT, so a
local/on-prem model and a hosted provider can be swapped per tenant
deployment without touching pipeline.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class SttProvider(Protocol):
    """Any STT backend (on-prem model, hosted API) must implement this."""

    async def stream_transcribe(
        self, audio_frames: AsyncIterator[bytes], language_hint: str | None = None
    ) -> AsyncIterator[PartialTranscript]:
        ...


class PartialTranscript:
    def __init__(self, text: str, is_final: bool, confidence: float):
        self.text = text
        self.is_final = is_final
        self.confidence = confidence
