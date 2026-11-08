import numpy as np

from telephony_gateway.codec import (
    G711Codec,
    TelephonyCodec,
    alaw_to_pcm16,
    mulaw_to_pcm16,
    pcm16_to_alaw,
    pcm16_to_mulaw,
    resample_linear,
)


def _tone(frequency_hz: float, duration_s: float, sample_rate_hz: int, amplitude: int = 8000) -> np.ndarray:
    t = np.arange(int(duration_s * sample_rate_hz)) / sample_rate_hz
    return (amplitude * np.sin(2 * np.pi * frequency_hz * t)).astype(np.int16)


def test_mulaw_round_trip_is_within_companding_tolerance():
    pcm = _tone(440, 0.02, 8000)
    encoded = pcm16_to_mulaw(pcm)
    assert encoded.dtype == np.uint8

    decoded = mulaw_to_pcm16(encoded)
    # G.711 is lossy (8-bit log companding of a 16-bit signal); this is not
    # meant to be lossless, just accurate enough for speech intelligibility.
    max_error = np.max(np.abs(decoded.astype(np.int32) - pcm.astype(np.int32)))
    assert max_error < 500


def test_alaw_round_trip_is_within_companding_tolerance():
    pcm = _tone(440, 0.02, 8000)
    encoded = pcm16_to_alaw(pcm)
    decoded = alaw_to_pcm16(encoded)
    max_error = np.max(np.abs(decoded.astype(np.int32) - pcm.astype(np.int32)))
    assert max_error < 500


def test_mulaw_round_trip_near_silence():
    pcm = np.zeros(160, dtype=np.int16)
    encoded = pcm16_to_mulaw(pcm)
    decoded = mulaw_to_pcm16(encoded)
    assert np.max(np.abs(decoded)) < 50


def test_resample_linear_preserves_duration_ratio():
    pcm_8k = _tone(300, 0.02, 8000)
    pcm_16k = resample_linear(pcm_8k, 8000, 16000)
    assert pcm_16k.size == pcm_8k.size * 2

    back_to_8k = resample_linear(pcm_16k, 16000, 8000)
    assert abs(back_to_8k.size - pcm_8k.size) <= 1


def test_telephony_codec_round_trip_pipeline_to_telephony_to_pipeline():
    codec = TelephonyCodec(G711Codec.MULAW)
    pcm_16k = _tone(300, 0.02, 16000)

    telephony_bytes = codec.encode_to_telephony(pcm_16k.tobytes())
    # 20ms @ 8kHz mono 8-bit G.711 = 160 bytes.
    assert len(telephony_bytes) == 160

    back_pcm_16k_bytes = codec.decode_from_telephony(telephony_bytes)
    back_pcm_16k = np.frombuffer(back_pcm_16k_bytes, dtype=np.int16)
    assert back_pcm_16k.size == pcm_16k.size

    correlation = np.corrcoef(pcm_16k.astype(np.float64), back_pcm_16k.astype(np.float64))[0, 1]
    assert correlation > 0.95
