"""RFC 4733 DTMF (telephone-event) decoding.

Banking IVR replacement needs digit capture independent of the isolated
PCI payment leg (compliance/pci/) — menu navigation ("press 2 for
collections"), OTP entry outside a payment flow, account number entry
where speech recognition alone is unreliable for long digit strings. RFC
4733 sends DTMF as its own RTP payload type (out-of-band, negotiated
separately from the G.711 audio payload type), not as in-band audio
tones, which is why this is a separate decoder from codec.py rather than
something VAD/STT ever sees.

An RFC 4733 sender repeats the packet for an event several times for
packet-loss redundancy — the last few repeats have the end bit (E) set.
This decoder reports a digit exactly once per keypress, on the first
end-marked packet, and ignores the redundant end-marked repeats that
follow it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

_EVENT_TO_DIGIT = {
    0: "0", 1: "1", 2: "2", 3: "3", 4: "4",
    5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
    10: "*", 11: "#",
    12: "A", 13: "B", 14: "C", 15: "D",
}

_HEADER = struct.Struct("!BBH")  # event, (E|R|volume), duration


@dataclass
class DtmfEvent:
    digit: str
    duration_samples: int


class DtmfDecoder:
    """Decodes one call leg's stream of RFC 4733 telephone-event payloads."""

    def __init__(self):
        self._end_already_reported = False

    def decode_packet(self, payload: bytes) -> DtmfEvent | None:
        if len(payload) < _HEADER.size:
            return None
        event_code, flags, duration = _HEADER.unpack_from(payload)
        end_bit = bool(flags & 0x80)

        if event_code not in _EVENT_TO_DIGIT:
            return None

        if not end_bit:
            self._end_already_reported = False
            return None

        if self._end_already_reported:
            return None  # redundant end-marked repeat of the same keypress

        self._end_already_reported = True
        return DtmfEvent(digit=_EVENT_TO_DIGIT[event_code], duration_samples=duration)
