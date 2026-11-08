import numpy as np
import pytest

from voice_pipeline.pipeline import VoicePipeline
from voice_pipeline.stt import PartialTranscript
from voice_pipeline.turn_manager import TurnManager


async def _frames(chunks):
    for c in chunks:
        yield c


class ScriptedSttProvider:
    """Yields a fixed sequence of PartialTranscript events regardless of
    the audio actually passed in, for deterministic endpointing tests."""

    def __init__(self, transcripts):
        self._transcripts = transcripts

    async def stream_transcribe(self, audio_frames, language_hint=None):
        async for _ in audio_frames:
            pass
        for t in self._transcripts:
            yield t


class CountingTtsProvider:
    def __init__(self, n_chunks: int):
        self._n_chunks = n_chunks

    async def stream_synthesize(self, text_chunks, voice_id, language):
        for _ in range(self._n_chunks):
            yield np.zeros(160, dtype=np.int16).tobytes()


@pytest.mark.asyncio
async def test_endpointing_extends_past_a_mid_thought_pause():
    stt = ScriptedSttProvider(
        [
            PartialTranscript("I need to check my", is_final=True, confidence=0.9),
            PartialTranscript("I need to check my balance", is_final=True, confidence=0.9),
        ]
    )
    tts = CountingTtsProvider(0)
    pipeline = VoicePipeline(stt=stt, tts=tts)

    silent_frame = np.zeros(160, dtype=np.int16).tobytes()
    finalized = [
        text async for text in pipeline.handle_inbound_audio("chan-1", _frames([silent_frame]), None)
    ]

    # The first "final" looked mid-thought and should have been extended,
    # not surfaced as a finalized utterance; only the second is.
    assert finalized == ["I need to check my balance"]


@pytest.mark.asyncio
async def test_synthesize_response_stops_yielding_once_barge_in_cancels():
    async def text_chunks():
        yield "hello there, how can I "
        yield "help you today"

    tts = CountingTtsProvider(5)
    turn_manager = TurnManager()
    pipeline = VoicePipeline(stt=ScriptedSttProvider([]), tts=tts, turn_manager=turn_manager)

    chunks_received = []
    gen = pipeline.synthesize_response("chan-1", text_chunks(), voice_id="v1", language="en-IN")
    async for chunk in gen:
        chunks_received.append(chunk)
        if len(chunks_received) == 2:
            # Simulate a barge-in landing mid-synthesis.
            turn_manager.cancellation_token.set()

    assert len(chunks_received) == 2  # stopped short of all 5 available chunks
