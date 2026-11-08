"""RTP media bridging between the SIP leg and the voice-pipeline gRPC stream.

Audio arriving from the caller is framed and forwarded to voice-pipeline as
it arrives, not buffered into full utterances, since streaming end to end is
what keeps the platform inside its latency budget. Audio coming back from
voice-pipeline (synthesized speech) is written back onto the RTP stream in
the same fashion.

Three things happen at this boundary that are easy to gloss over in a
diagram but break a live call if skipped:

1. Codec conversion (codec.py): the wire format is G.711 at 8kHz, not the
   16kHz linear PCM voice-pipeline speaks.
2. Jitter buffering + loss concealment (jitter_buffer.py): telephony
   networks reorder and drop packets; voice-pipeline should never see that.
3. RTP packetization itself: sequence numbers, timestamps, SSRC, and a
   fixed payload type, per RFC 3550, both directions.
"""

from __future__ import annotations

import asyncio
import random
import socket
import struct

import structlog

from telephony_gateway.codec import G711Codec, TelephonyCodec
from telephony_gateway.dtmf import DtmfDecoder
from telephony_gateway.jitter_buffer import JitterBuffer, RtpPacket

logger = structlog.get_logger(__name__)

FRAME_DURATION_MS = 20
SAMPLE_RATE_HZ = 16_000  # voice-pipeline's internal rate; wire rate is 8kHz.
TELEPHONY_SAMPLES_PER_FRAME = 160  # 20ms @ 8kHz

_RTP_VERSION = 2
_PT_PCMU = 0  # RFC 3551 static payload type for G.711 mu-law.
_PT_PCMA = 8  # RFC 3551 static payload type for G.711 A-law.
_RTP_HEADER = struct.Struct("!BBHII")  # version/flags, pt, seq, timestamp, ssrc


def _new_ssrc() -> int:
    return random.getrandbits(32)


def build_rtp_packet(*, sequence: int, timestamp: int, ssrc: int, payload_type: int, payload: bytes) -> bytes:
    header = _RTP_HEADER.pack(
        (_RTP_VERSION << 6),
        payload_type & 0x7F,
        sequence & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc & 0xFFFFFFFF,
    )
    return header + payload


def parse_rtp_packet(packet: bytes) -> tuple[int, int, int, int, bytes]:
    """Returns (payload_type, sequence, timestamp, ssrc, payload)."""
    if len(packet) < _RTP_HEADER.size:
        raise ValueError("packet shorter than a minimal RTP header")
    version_flags, pt, seq, timestamp, ssrc = _RTP_HEADER.unpack_from(packet)
    if (version_flags >> 6) != _RTP_VERSION:
        raise ValueError(f"unsupported RTP version in header byte {version_flags:#x}")
    return pt & 0x7F, seq, timestamp, ssrc, packet[_RTP_HEADER.size :]


class RtpStream:
    """Bridges a single call's RTP audio to and from the voice pipeline.

    telephony-gateway owns exactly one UDP socket per active call for the
    media leg (the address/port are negotiated by the SIP layer via SDP,
    out of scope for this module); this class turns that socket's bytes
    into 16kHz PCM frames for voice-pipeline and back.
    """

    def __init__(
        self,
        channel_id: str,
        voice_pipeline_client,
        *,
        codec: G711Codec = G711Codec.MULAW,
        remote_addr: tuple[str, int] | None = None,
        sock: socket.socket | None = None,
        dtmf_payload_type: int | None = 101,
        on_dtmf_digit=None,
    ):
        self._channel_id = channel_id
        self._voice_pipeline = voice_pipeline_client
        self._codec = TelephonyCodec(codec)
        self._payload_type = _PT_PCMU if codec == G711Codec.MULAW else _PT_PCMA
        self._remote_addr = remote_addr
        self._sock = sock
        self._jitter_buffer = JitterBuffer()
        # RFC 4733 DTMF events arrive as their own RTP payload type,
        # negotiated separately in SDP (101 is the common convention but
        # deployment-specific) — never mixed into the G.711 audio stream.
        self._dtmf_payload_type = dtmf_payload_type
        self._dtmf_decoder = DtmfDecoder()
        self._on_dtmf_digit = on_dtmf_digit
        self._inbound_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False

        self._inbound_ssrc: int | None = None
        self._outbound_ssrc = _new_ssrc()
        self._outbound_seq = random.getrandbits(16)
        self._outbound_timestamp = random.getrandbits(32)

    async def on_inbound_packet(self, packet: bytes) -> None:
        """Called by the media handler for every RTP packet from the caller."""
        if self._closed:
            return
        try:
            pt, seq, timestamp, ssrc, payload = parse_rtp_packet(packet)
        except ValueError:
            logger.warning("dropping_malformed_rtp_packet", channel_id=self._channel_id)
            return
        if pt == self._dtmf_payload_type:
            event = self._dtmf_decoder.decode_packet(payload)
            if event is not None and self._on_dtmf_digit is not None:
                self._on_dtmf_digit(event.digit)
            return
        if pt not in (_PT_PCMU, _PT_PCMA):
            return  # not a codec or DTMF payload type this stream handles
        self._inbound_ssrc = ssrc
        self._jitter_buffer.push(RtpPacket(sequence=seq, timestamp=timestamp, payload=payload))

        while self._jitter_buffer.ready():
            telephony_payload = self._jitter_buffer.pull()
            if telephony_payload is None:
                continue
            pcm_16k = self._codec.decode_from_telephony(telephony_payload)
            await self._inbound_queue.put(pcm_16k)

    async def run(self) -> None:
        """Drains inbound audio into voice-pipeline and streams responses back."""
        send_task = asyncio.create_task(self._forward_inbound())
        try:
            async for outbound_frame in self._voice_pipeline.stream_responses(self._channel_id):
                await self._write_outbound_frame(outbound_frame)
        finally:
            self._closed = True
            send_task.cancel()

    async def _forward_inbound(self) -> None:
        while not self._closed:
            frame = await self._inbound_queue.get()
            await self._voice_pipeline.send_audio_frame(self._channel_id, frame)

    async def _write_outbound_frame(self, pcm_16k_frame: bytes) -> None:
        """Encodes a synthesized 16kHz PCM frame to G.711 and writes it as
        one or more RTP packets onto the RTP leg."""
        telephony_payload = self._codec.encode_to_telephony(pcm_16k_frame)

        for offset in range(0, len(telephony_payload), TELEPHONY_SAMPLES_PER_FRAME):
            chunk = telephony_payload[offset : offset + TELEPHONY_SAMPLES_PER_FRAME]
            packet = build_rtp_packet(
                sequence=self._outbound_seq,
                timestamp=self._outbound_timestamp,
                ssrc=self._outbound_ssrc,
                payload_type=self._payload_type,
                payload=chunk,
            )
            self._outbound_seq = (self._outbound_seq + 1) & 0xFFFF
            self._outbound_timestamp = (self._outbound_timestamp + len(chunk)) & 0xFFFFFFFF
            await self._send_packet(packet)

    async def _send_packet(self, packet: bytes) -> None:
        if self._sock is None or self._remote_addr is None:
            # No socket wired up (e.g. unit tests, or a deployment that
            # bridges media through Asterisk's external media / RTP proxy
            # instead of a raw socket this process owns directly).
            return
        loop = asyncio.get_running_loop()
        await loop.sock_sendto(self._sock, packet, self._remote_addr)
