import numpy as np

from voice_pipeline.aec import NlmsEchoCanceller


def _tone(frequency_hz: float, n_samples: int, sample_rate_hz: int, amplitude: float = 4000) -> np.ndarray:
    t = np.arange(n_samples) / sample_rate_hz
    return (amplitude * np.sin(2 * np.pi * frequency_hz * t)).astype(np.int16)


def test_reduces_pure_echo_energy_after_adapting():
    """near-end is *only* a delayed, attenuated copy of far-end (pure
    echo, no real caller speech) — after the filter adapts across a few
    frames, cancelled output energy should drop well below the raw echo."""
    sample_rate_hz = 8_000
    frame_size = 160  # 20ms
    aec = NlmsEchoCanceller(sample_rate_hz=sample_rate_hz, filter_length_ms=20, step_size=0.5)

    far_end_signal = _tone(300, frame_size * 12, sample_rate_hz, amplitude=6000)
    echo_delay_samples = 40
    echo_gain = 0.6
    near_end_signal = np.zeros_like(far_end_signal, dtype=np.float64)
    near_end_signal[echo_delay_samples:] = far_end_signal[:-echo_delay_samples] * echo_gain
    near_end_signal = near_end_signal.astype(np.int16)

    raw_energy_last_frame = None
    cancelled_energy_last_frame = None
    for i in range(0, len(far_end_signal), frame_size):
        far_frame = far_end_signal[i : i + frame_size]
        near_frame = near_end_signal[i : i + frame_size]
        aec.on_far_end_frame(far_frame)
        cancelled = aec.process(near_frame)
        raw_energy_last_frame = float(np.mean(near_frame.astype(np.float64) ** 2))
        cancelled_energy_last_frame = float(np.mean(cancelled.astype(np.float64) ** 2))

    # By the final frame the adaptive filter should have converged enough
    # to cancel most of the echo's energy.
    assert cancelled_energy_last_frame < raw_energy_last_frame * 0.5


def test_does_not_touch_signal_when_far_end_is_silent():
    """With no far-end reference at all, there is nothing to cancel —
    the near-end signal (independent caller speech) should pass through
    close to unchanged rather than being blindly attenuated."""
    sample_rate_hz = 8_000
    frame_size = 160
    aec = NlmsEchoCanceller(sample_rate_hz=sample_rate_hz, filter_length_ms=20)

    silence = np.zeros(frame_size, dtype=np.int16)
    caller_speech = _tone(220, frame_size, sample_rate_hz, amplitude=5000)

    aec.on_far_end_frame(silence)
    output = aec.process(caller_speech)

    correlation = np.corrcoef(caller_speech.astype(np.float64), output.astype(np.float64))[0, 1]
    assert correlation > 0.99
