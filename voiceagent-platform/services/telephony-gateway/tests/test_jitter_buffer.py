import numpy as np

from telephony_gateway.jitter_buffer import JitterBuffer, JitterBufferConfig, RtpPacket


def _frame(value: int) -> bytes:
    return np.full(160, value, dtype=np.int16).tobytes()


def test_plays_out_in_order_once_primed():
    buf = JitterBuffer(JitterBufferConfig(target_depth=2))
    buf.push(RtpPacket(sequence=1, timestamp=160, payload=_frame(1)))
    assert buf.pull() is None  # not primed yet

    buf.push(RtpPacket(sequence=2, timestamp=320, payload=_frame(2)))
    assert buf.pull() == _frame(1)
    assert buf.pull() == _frame(2)


def test_reorders_out_of_order_arrivals():
    buf = JitterBuffer(JitterBufferConfig(target_depth=3))
    buf.push(RtpPacket(sequence=5, timestamp=800, payload=_frame(5)))
    buf.push(RtpPacket(sequence=3, timestamp=480, payload=_frame(3)))
    buf.push(RtpPacket(sequence=4, timestamp=640, payload=_frame(4)))

    assert buf.pull() == _frame(3)
    assert buf.pull() == _frame(4)
    assert buf.pull() == _frame(5)


def test_conceals_a_single_lost_packet_then_recovers():
    buf = JitterBuffer(JitterBufferConfig(target_depth=2))
    buf.push(RtpPacket(sequence=1, timestamp=160, payload=_frame(100)))
    # sequence 2 is lost in transit
    buf.push(RtpPacket(sequence=3, timestamp=480, payload=_frame(200)))

    assert buf.pull() == _frame(100)
    concealed = buf.pull()
    assert concealed is not None
    # decayed repeat of the last good frame, not silence and not garbage
    assert np.all(np.abs(np.frombuffer(concealed, dtype=np.int16)) < 100)
    assert buf.pull() == _frame(200)


def test_gives_up_concealing_after_max_consecutive_losses():
    buf = JitterBuffer(JitterBufferConfig(target_depth=1, max_concealed_in_a_row=2))
    buf.push(RtpPacket(sequence=1, timestamp=160, payload=_frame(100)))
    buf.push(RtpPacket(sequence=5, timestamp=800, payload=_frame(200)))

    assert buf.pull() == _frame(100)
    assert buf.pull() is not None  # concealed 2
    assert buf.pull() is not None  # concealed 3
    assert buf.pull() is None  # concealment budget exhausted -> true silence
