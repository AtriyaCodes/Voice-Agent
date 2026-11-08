"""Wires AEC, VAD, STT, endpointing/turn management, and TTS into the
per-call streaming loop.

This is the module that telephony-gateway and agent-core actually talk to
over gRPC; AEC/VAD/STT/TTS/turn_manager are implementation details behind
it. The ordering inside handle_inbound_audio is deliberate and matters:
echo cancellation has to run before VAD ever sees a frame, or barge-in
detection triggers on the agent hearing itself (see aec.py's docstring).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np
import structlog

from voice_pipeline.aec import EchoCanceller, NoOpEchoCanceller
from voice_pipeline.stt import SttProvider
from voice_pipeline.tts import TtsProvider
from voice_pipeline.turn_manager import TurnManager
from voice_pipeline.vad import VoiceActivityDetector

logger = structlog.get_logger(__name__)


class VoicePipeline:
    def __init__(
        self,
        stt: SttProvider,
        tts: TtsProvider,
        vad: VoiceActivityDetector | None = None,
        turn_manager: TurnManager | None = None,
        echo_canceller: EchoCanceller | None = None,
    ):
        self._stt = stt
        self._tts = tts
        self._vad = vad or VoiceActivityDetector()
        self._turn_manager = turn_manager or TurnManager()
        self._aec = echo_canceller or NoOpEchoCanceller()

    async def handle_inbound_audio(
        self, channel_id: str, frames: AsyncIterator[bytes], language_hint: str | None
    ) -> AsyncIterator[str]:
        """Yields finalized utterance text as soon as endpointing (not just
        STT/VAD silence) agrees the caller is actually done talking."""

        async def echo_cancelled_frames() -> AsyncIterator[bytes]:
            async for frame in frames:
                pcm = np.frombuffer(frame, dtype=np.int16)
                cleaned = self._aec.process(pcm)
                self._maybe_signal_barge_in(cleaned)
                yield cleaned.tobytes()

        async for transcript in self._stt.stream_transcribe(echo_cancelled_frames(), language_hint):
            if not transcript.is_final:
                continue

            # STT's own end-of-utterance signal (typically VAD-silence
            # driven inside the STT engine) is treated as *tentative* —
            # endpointing gets the final say so a mid-thought pause
            # doesn't get finalized as a full turn. See endpointing.py.
            if self._turn_manager.on_utterance_tentatively_ended(transcript.text):
                logger.info("utterance_finalized", channel_id=channel_id)
                self._turn_manager.confirm_real_interruption()
                yield transcript.text

    def _maybe_signal_barge_in(self, cleaned_frame: np.ndarray) -> None:
        is_speech, _ = self._vad.process_frame(cleaned_frame)
        if is_speech:
            self._turn_manager.on_caller_started_speaking_while_agent_speaking()

    async def synthesize_response(
        self, channel_id: str, text_chunks: AsyncIterator[str], voice_id: str, language: str
    ) -> AsyncIterator[bytes]:
        self._turn_manager.on_agent_started_speaking()
        cancellation_token = self._turn_manager.cancellation_token

        async for audio_chunk in self._tts.stream_synthesize(text_chunks, voice_id, language):
            if cancellation_token.is_set():
                logger.info("tts_cancelled_on_barge_in", channel_id=channel_id)
                return
            self._aec.on_far_end_frame(np.frombuffer(audio_chunk, dtype=np.int16))
            yield audio_chunk
