import struct

from telephony_gateway.dtmf import DtmfDecoder


def _packet(event_code: int, end_bit: bool, duration: int = 160, volume: int = 10) -> bytes:
    flags = (0x80 if end_bit else 0x00) | (volume & 0x3F)
    return struct.pack("!BBH", event_code, flags, duration)


def test_reports_a_digit_once_on_first_end_marked_packet():
    decoder = DtmfDecoder()
    # A real sender emits several non-end packets while the key is held,
    # then repeats the end-marked packet a few times for loss redundancy.
    assert decoder.decode_packet(_packet(5, end_bit=False, duration=160)) is None
    assert decoder.decode_packet(_packet(5, end_bit=False, duration=320)) is None

    first = decoder.decode_packet(_packet(5, end_bit=True, duration=480))
    assert first is not None
    assert first.digit == "5"

    # Redundant end-marked repeats of the same keypress must not re-report.
    assert decoder.decode_packet(_packet(5, end_bit=True, duration=480)) is None
    assert decoder.decode_packet(_packet(5, end_bit=True, duration=480)) is None


def test_decodes_star_and_pound_and_a_through_d():
    decoder = DtmfDecoder()
    for code, expected in [(10, "*"), (11, "#"), (12, "A"), (13, "B"), (14, "C"), (15, "D")]:
        event = decoder.decode_packet(_packet(code, end_bit=True))
        assert event.digit == expected
        decoder = DtmfDecoder()  # reset dedup state between keys


def test_full_otp_sequence_decodes_in_order():
    decoder = DtmfDecoder()
    digits = []
    for digit_code in (1, 2, 3, 4):
        decoder.decode_packet(_packet(digit_code, end_bit=False))
        event = decoder.decode_packet(_packet(digit_code, end_bit=True))
        digits.append(event.digit)

    assert "".join(digits) == "1234"


def test_ignores_short_or_malformed_payloads():
    decoder = DtmfDecoder()
    assert decoder.decode_packet(b"\x00") is None
