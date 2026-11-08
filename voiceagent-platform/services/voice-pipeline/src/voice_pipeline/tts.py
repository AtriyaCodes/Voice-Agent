"""Streaming text to speech.

Response text from agent-core is synthesized incrementally, sentence by
sentence where possible, so the caller starts hearing audio before the
full response has finished generating.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class TtsProvider(Protocol):
    """Any TTS backend must implement incremental synthesis."""

    async def stream_synthesize(
        self, text_chunks: AsyncIterator[str], voice_id: str, language: str
    ) -> AsyncIterator[bytes]:
        ...
