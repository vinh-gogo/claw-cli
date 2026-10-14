from __future__ import annotations

from claw.agent.router import route_input
from claw.ui.status import UIStatus


def test_route_speech_on_and_off() -> None:
    assert route_input("/speech on").kind == "speech_on"
    assert route_input("  /SPEECH   ON  ").kind == "speech_on"
    assert route_input("bật giọng nói").kind == "speech_on"

    assert route_input("/speech off").kind == "speech_off"
    assert route_input("  /SPEECH   OFF ").kind == "speech_off"
    assert route_input("tắt giọng nói").kind == "speech_off"

    normal = route_input("kiểm tra thư mục hiện tại")
    assert normal.kind == "prompt"
    assert normal.cleaned_prompt == "kiểm tra thư mục hiện tại"


def test_ui_status_speech_mode_render() -> None:
    status = UIStatus()
    assert status.speech_mode == "hybrid"
    assert "Hỗn hợp" in status.render_bar().plain

    status.speech_mode = "on"
    assert "/speech on" in status.render_bar().plain

    status.speech_mode = "off"
    assert "/speech off" in status.render_bar().plain


def test_automatic_end_of_utterance_detection() -> None:
    import numpy as np

    from claw.voice.vad import SileroVAD, UtteranceDetector

    vad = SileroVAD(sample_rate=16000, silence_ms=600, min_speech_ms=250)
    detector = UtteranceDetector(vad)

    # Simulate 0.5s of speech followed by 0.7s of silence/background noise
    # Use synthetic speech-like signal or force vad._model_ready=False to test adaptive energy + EOU
    vad._model_ready = False
    speech_frame = (np.sin(np.linspace(0, 20 * np.pi, 512)) * 8000).astype(np.int16)
    silence_frame = np.zeros(512, dtype=np.int16)

    for _ in range(12):  # ~384ms speech (> min_speech_ms=250ms)
        assert detector.process_frame(speech_frame) is None

    detected: np.ndarray | None = None
    for _ in range(25):  # ~800ms silence (> silence_ms=600ms)
        res = detector.process_frame(silence_frame)
        if res is not None:
            detected = res
            break

    assert detected is not None
    assert len(detected) >= 12 * 512
