"""Voice activity detection.

Runs on every inbound audio frame to decide when the caller has started
and stopped speaking. This drives when partial audio is sent to STT and
when an utterance is considered complete enough for agent-core to act on,
which is the single biggest lever on end-to-end latency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VadConfig:
    energy_threshold: float = 0.02
    min_speech_frames: int = 3
    min_silence_frames_to_end: int = 15  # ~300ms at 20ms frames


class VoiceActivityDetector:
    """Simple energy-based VAD with hangover, replaceable with a model-based one."""

    def __init__(self, config: VadConfig | None = None):
        self._config = config or VadConfig()
        self._speech_frame_count = 0
        self._silence_frame_count = 0
        self._in_speech = False

    def process_frame(self, frame: np.ndarray) -> tuple[bool, bool]:
        """Returns (is_speech_active, utterance_ended)."""
        energy = float(np.mean(np.abs(frame)))
        is_speech_frame = energy > self._config.energy_threshold

        if is_speech_frame:
            self._speech_frame_count += 1
            self._silence_frame_count = 0
            if self._speech_frame_count >= self._config.min_speech_frames:
                self._in_speech = True
        else:
            self._silence_frame_count += 1
            self._speech_frame_count = 0

        utterance_ended = False
        if self._in_speech and self._silence_frame_count >= self._config.min_silence_frames_to_end:
            utterance_ended = True
            self._in_speech = False

        return self._in_speech, utterance_ended
