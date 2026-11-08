"""Jitter buffer and packet-loss concealment for inbound RTP audio.

Telephony networks (carrier SIP trunks especially) reorder and drop UDP
packets; feeding STT a raw, unbuffered, gap-having frame stream measurably
hurts transcription quality and can desync turn-taking timing entirely.
This module holds a small, bounded window of recently-arrived RTP packets,
plays them out in sequence order once a target depth is reached (trading a
little latency for reordering tolerance), and fills genuinely missing
frames with a cheap packet-loss-concealment strategy so downstream VAD/STT
sees a continuous frame stream instead of silence-shaped holes.

This is deliberately the "cheap" PLC: repeat-and-decay the last good frame
rather than a real waveform-similarity/generative PLC model. A codec with
built-in PLC (e.g. Opus) or a dedicated PLC model is the right answer for
a wideband voice product; G.711 telephony audio has no such feature, and
for the frame durations involved (20ms) and consecutive-loss cap here,
repeat-and-decay is what most SIP media stacks already do and is good
enough to keep VAD/STT from choking on a hard gap.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SEQUENCE_MODULUS = 1 << 16  # RTP sequence numbers are 16-bit and wrap around.
_HALF_MODULUS = SEQUENCE_MODULUS // 2


def _seq_distance(a: int, b: int) -> int:
    """Signed distance a - b on the 16-bit RTP sequence number ring."""
    diff = (a - b) % SEQUENCE_MODULUS
    return diff - SEQUENCE_MODULUS if diff > _HALF_MODULUS else diff


@dataclass
class RtpPacket:
    sequence: int
    timestamp: int
    payload: bytes


@dataclass
class JitterBufferConfig:
    target_depth: int = 3
    """Packets buffered before playout starts — the reordering tolerance."""
    max_depth: int = 15
    """Packets held before the oldest is dropped as unrecoverably late."""
    max_concealed_in_a_row: int = 5
    """~100ms at 20ms frames before concealment gives up and goes silent,
    rather than looping a stale frame indefinitely."""


class JitterBuffer:
    """Reorders inbound RTP packets and conceals lost ones on playout."""

    def __init__(self, config: JitterBufferConfig | None = None):
        self._config = config or JitterBufferConfig()
        self._packets: dict[int, RtpPacket] = {}
        self._next_seq: int | None = None
        self._primed = False
        self._last_good_payload: bytes | None = None
        self._concealed_run = 0

    def push(self, packet: RtpPacket) -> None:
        if self._next_seq is not None and _seq_distance(packet.sequence, self._next_seq) < 0:
            return  # already played out or too late to matter
        self._packets[packet.sequence] = packet
        if len(self._packets) > self._config.max_depth:
            oldest_seq = min(self._packets, key=lambda s: _seq_distance(s, packet.sequence))
            del self._packets[oldest_seq]

    def ready(self) -> bool:
        if self._primed:
            return len(self._packets) > 0
        return len(self._packets) >= self._config.target_depth

    def pull(self) -> bytes | None:
        """Returns the next frame's payload in sequence order.

        Returns concealment audio for a genuinely missing packet, or None
        once concealment has run out of budget (caller should treat that
        as "insert true silence" rather than keep manufacturing audio).
        """
        if not self.ready():
            return None
        self._primed = True

        if self._next_seq is None:
            self._next_seq = min(self._packets)

        packet = self._packets.pop(self._next_seq, None)
        self._next_seq = (self._next_seq + 1) % SEQUENCE_MODULUS

        if packet is not None:
            self._concealed_run = 0
            self._last_good_payload = packet.payload
            return packet.payload

        return self._conceal()

    def _conceal(self) -> bytes | None:
        if self._last_good_payload is None:
            return None
        if self._concealed_run >= self._config.max_concealed_in_a_row:
            return None
        self._concealed_run += 1

        # Decay each concealed repeat so a run of losses fades toward
        # silence instead of looping a fixed buzz.
        decay = 0.6**self._concealed_run
        samples = np.frombuffer(self._last_good_payload, dtype=np.int16).astype(np.float64)
        concealed = np.clip(samples * decay, -32768, 32767).astype(np.int16)
        return concealed.tobytes()
