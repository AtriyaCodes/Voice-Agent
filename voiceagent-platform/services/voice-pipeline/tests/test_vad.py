import numpy as np

from voice_pipeline.vad import VadConfig, VoiceActivityDetector


def _frame(energy: float) -> np.ndarray:
    return np.full(320, energy, dtype=np.float32)


def test_vad_detects_speech_start_and_end():
    vad = VoiceActivityDetector(VadConfig(min_speech_frames=2, min_silence_frames_to_end=3))

    speech_frame = _frame(0.1)
    silence_frame = _frame(0.0)

    assert vad.process_frame(speech_frame) == (False, False)
    in_speech, ended = vad.process_frame(speech_frame)
    assert in_speech is True
    assert ended is False

    for _ in range(2):
        in_speech, ended = vad.process_frame(silence_frame)

    in_speech, ended = vad.process_frame(silence_frame)
    assert ended is True
