"""Acoustic echo cancellation.

This is the piece that makes barge-in detection trustworthy. Without it,
the agent's own synthesized speech leaks back into the inbound signal
(through the telephony hybrid, or a caller on speakerphone) and VAD has no
way to tell "the caller interrupted" from "the agent is hearing itself" —
it either false-triggers barge-in constantly, or STT starts transcribing
the agent's own words back at it. VAD and turn-taking should only ever
see the caller's actual voice, which means echo has to be removed
*before* audio reaches vad.py, not worked around after the fact.

`NlmsEchoCanceller` is a real, working adaptive filter (normalized LMS)
using the agent's own outbound TTS audio as the echo reference — the
standard architecture for this problem — sized for the telephony sample
rate and typical hybrid/room echo tail lengths. It is not a production
WebRTC-grade AEC (no double-talk detection, no nonlinear residual echo
suppression) — a real deployment should swap in something like the
`webrtc-audio-processing` bindings for that. What matters architecturally
is that the cancellation step exists as a hard stage between the RTP
input and VAD, with the same pluggable-provider shape as STT/TTS, so a
better implementation drops in without moving where echo cancellation
happens in the pipeline.
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

import numpy as np


class EchoCanceller(Protocol):
    """Cancels the agent's own voice out of the inbound (near-end) signal."""

    def on_far_end_frame(self, far_end_frame: np.ndarray) -> None:
        """Called with each frame of audio voice-pipeline is currently
        sending to the caller (the echo reference), in playout order."""
        ...

    def process(self, near_end_frame: np.ndarray) -> np.ndarray:
        """Returns near_end_frame with the estimated echo removed."""
        ...


class NoOpEchoCanceller:
    """Passes audio through unchanged. Only valid where the deployment is
    known to have no echo path (e.g. a pure digital/headset endpoint) —
    never the default for a telephony deployment."""

    def on_far_end_frame(self, far_end_frame: np.ndarray) -> None:
        pass

    def process(self, near_end_frame: np.ndarray) -> np.ndarray:
        return near_end_frame


class NlmsEchoCanceller:
    """Normalized least-mean-squares adaptive echo canceller.

    Models the echo path (hybrid/speaker-to-mic coupling) as an FIR
    filter and adapts its taps every frame to minimize the energy of
    (near_end - estimated_echo), using the far-end reference audio as the
    only input to the estimate. `filter_length_samples` should cover the
    longest echo tail the deployment expects; ~200ms is a reasonable
    default for a telephony hybrid.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int = 16_000,
        filter_length_ms: int = 200,
        step_size: float = 0.5,
        regularization: float = 1e-6,
    ):
        self._filter_length = max(1, int(sample_rate_hz * filter_length_ms / 1000))
        self._step_size = step_size
        self._regularization = regularization
        self._weights = np.zeros(self._filter_length, dtype=np.float64)
        # History of far-end samples, most-recent-last, long enough to
        # supply a full filter window for any near-end frame length.
        self._far_end_history: deque[float] = deque(
            [0.0] * self._filter_length, maxlen=self._filter_length * 4
        )

    def on_far_end_frame(self, far_end_frame: np.ndarray) -> None:
        self._far_end_history.extend(far_end_frame.astype(np.float64).tolist())

    def process(self, near_end_frame: np.ndarray) -> np.ndarray:
        near = near_end_frame.astype(np.float64)
        history = np.array(self._far_end_history, dtype=np.float64)
        output = np.empty_like(near)

        for i in range(near.size):
            window = self._reference_window(history, i, near.size)
            estimated_echo = float(np.dot(self._weights, window))
            error = near[i] - estimated_echo
            output[i] = error

            energy = float(np.dot(window, window)) + self._regularization
            self._weights += (self._step_size * error / energy) * window

        return np.clip(output, -32768, 32767).astype(np.int16)

    def _reference_window(self, history: np.ndarray, sample_index: int, frame_size: int) -> np.ndarray:
        """The filter_length most recent far-end samples as of this
        near-end sample, aligned so index 0 of history is the oldest."""
        # sample_index counts up through the current frame; the far-end
        # history buffer already ends at "now" for the start of this
        # frame, so each subsequent sample looks one position further
        # back from the end to stay aligned as the frame is consumed.
        end = history.size - (frame_size - 1 - sample_index)
        start = end - self._filter_length
        if start < 0:
            window = np.zeros(self._filter_length, dtype=np.float64)
            window[-min(end, self._filter_length) :] = history[max(0, end - self._filter_length) : end]
            return window
        return history[start:end]
