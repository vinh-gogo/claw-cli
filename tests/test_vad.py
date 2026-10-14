from __future__ import annotations

import numpy as np

from gemma_stt.vad import RmsVAD, SileroOnnxVAD, compute_rms, create_vad


def test_compute_rms_silence_and_sine() -> None:
    silence = np.zeros(320, dtype=np.float32)
    assert compute_rms(silence) == 0.0

    # Full-scale sine wave of amplitude 0.1 has RMS ~ 0.1 / sqrt(2) = 0.07071
    t = np.linspace(0, 0.02, 320, endpoint=False, dtype=np.float32)
    sine = 0.1 * np.sin(2.0 * np.pi * 440.0 * t).astype(np.float32)
    rms = compute_rms(sine)
    assert abs(rms - (0.1 / np.sqrt(2.0))) < 1e-3


def test_rms_vad_threshold_classification() -> None:
    vad = RmsVAD(threshold=0.012)

    quiet_noise = np.full(320, 0.003, dtype=np.float32)
    is_voice, score = vad.is_speech(quiet_noise)
    assert is_voice is False
    assert abs(score - 0.003) < 1e-5

    loud_signal = np.full(320, 0.025, dtype=np.float32)
    is_voice_2, score_2 = vad.is_speech(loud_signal)
    assert is_voice_2 is True
    assert abs(score_2 - 0.025) < 1e-5


def test_silero_vad_accepts_20ms_blocks_and_resets() -> None:
    vad = SileroOnnxVAD(sample_rate=16000, threshold=0.5, rms_fallback_threshold=0.012)
    silence = np.zeros(320, dtype=np.float32)
    is_voice, prob = vad.is_speech(silence)
    assert is_voice is False
    assert 0.0 <= prob <= 1.0
    vad.reset()


def test_create_vad_factory() -> None:
    v_rms = create_vad("rms", rms_threshold=0.015)
    assert isinstance(v_rms, RmsVAD)
    assert v_rms.threshold == 0.015

    v_silero = create_vad("silero", silero_threshold=0.6)
    assert isinstance(v_silero, SileroOnnxVAD)
    assert v_silero.threshold == 0.6
