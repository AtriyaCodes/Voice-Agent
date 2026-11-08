import asyncio
import socket

import numpy as np
import pytest

from telephony_gateway.codec import G711Codec, TelephonyCodec
from telephony_gateway.rtp_stream import RtpStream, build_rtp_packet, parse_rtp_packet


def test_build_and_parse_rtp_packet_round_trip():
    packet = build_rtp_packet(sequence=42, timestamp=12345, ssrc=999, payload_type=0, payload=b"\x01\x02\x03")
    pt, seq, ts, ssrc, payload = parse_rtp_packet(packet)
    assert (pt, seq, ts, ssrc, payload) == (0, 42, 12345, 999, b"\x01\x02\x03")


def test_parse_rejects_short_packet():
    with pytest.raises(ValueError):
        parse_rtp_packet(b"\x00\x00")


class FakeVoicePipelineClient:
    async def stream_responses(self, channel_id):
        return
        yield  # pragma: no cover - makes this an async generator

    async def send_audio_frame(self, channel_id, frame):
        pass


@pytest.mark.asyncio
async def test_on_inbound_packet_decodes_g711_to_16khz_pcm_once_jitter_buffer_primes():
    stream = RtpStream("chan-1", FakeVoicePipelineClient(), codec=G711Codec.MULAW)
    codec = TelephonyCodec(G711Codec.MULAW)

    pcm_16k = (2000 * np.sin(2 * np.pi * 300 * np.arange(320) / 16000)).astype(np.int16)
    telephony_bytes = codec.encode_to_telephony(pcm_16k.tobytes())

    for i, seq in enumerate((1, 2, 3)):  # target_depth defaults to 3
        packet = build_rtp_packet(sequence=seq, timestamp=seq * 160, ssrc=1, payload_type=0, payload=telephony_bytes)
        await stream.on_inbound_packet(packet)

    frame = await asyncio.wait_for(stream._inbound_queue.get(), timeout=1)
    assert len(frame) == len(pcm_16k.tobytes())


@pytest.mark.asyncio
async def test_on_inbound_packet_ignores_non_g711_payload_types():
    stream = RtpStream("chan-1", FakeVoicePipelineClient(), codec=G711Codec.MULAW)
    dtmf_packet = build_rtp_packet(sequence=1, timestamp=160, ssrc=1, payload_type=101, payload=b"\x00\x0a\x0a\x00")
    await stream.on_inbound_packet(dtmf_packet)
    assert stream._inbound_queue.empty()


@pytest.mark.asyncio
async def test_write_outbound_frame_sends_real_rtp_packets_over_udp_loopback():
    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx_sock.setblocking(False)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.bind(("127.0.0.1", 0))
    rx_sock.setblocking(False)

    try:
        stream = RtpStream(
            "chan-1",
            FakeVoicePipelineClient(),
            codec=G711Codec.MULAW,
            remote_addr=rx_sock.getsockname(),
            sock=tx_sock,
        )
        pcm_16k = (1000 * np.sin(2 * np.pi * 300 * np.arange(320) / 16000)).astype(np.int16)
        await stream._write_outbound_frame(pcm_16k.tobytes())

        loop = asyncio.get_running_loop()
        received = await asyncio.wait_for(loop.sock_recv(rx_sock, 2048), timeout=1)
        pt, _seq, _ts, _ssrc, payload = parse_rtp_packet(received)
        assert pt == 0  # PCMU
        assert len(payload) == 160  # 20ms @ 8kHz G.711
    finally:
        tx_sock.close()
        rx_sock.close()
