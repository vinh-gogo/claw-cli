from __future__ import annotations

import numpy as np

from gemma_stt.audio_capture import AudioBlock
from gemma_stt.segmenter import SpeechSegmenter
from gemma_stt.vad import RmsVAD


def _make_block(
    amplitude: float,
    captured_at: float,
    block_index: int,
    sample_rate: int = 16000,
    block_size: int = 320,
    dropped_before: int = 0,
) -> AudioBlock:
    samples = np.full(block_size, amplitude, dtype=np.float32)
    return AudioBlock(
        samples=samples,
        captured_at=captured_at,
        sample_rate=sample_rate,
        block_index=block_index,
        dropped_before=dropped_before,
    )


def test_segmenter_pre_roll_and_silence_emit() -> None:
    vad = RmsVAD(threshold=0.012)
    seg = SpeechSegmenter(
        vad=vad,
        sample_rate=16000,
        block_ms=20,
        pre_roll_ms=200,     # 10 blocks
        silence_ms=450,      # 22.5 -> 23 blocks (7200 samples)
        min_speech_ms=350,   # 17.5 -> 18 blocks (5600 samples)
        max_segment_ms=4000,
        overlap_ms=160,
    )

    t = 100.0
    idx = 0

    # 15 blocks of silence (only last 10 should be kept in pre-roll)
    for _ in range(15):
        assert seg.process_block(_make_block(0.001, t, idx)) is None
        t += 0.02
        idx += 1

    assert seg.state == "IDLE"

    # 25 blocks (500 ms) of speech (>= 350 ms min_speech_ms)
    last_speech_time = 0.0
    for _ in range(25):
        last_speech_time = t
        assert seg.process_block(_make_block(0.05, t, idx)) is None
        t += 0.02
        idx += 1

    assert seg.state == "RECORDING"
    # O(1) recorded_samples = 10 pre-roll blocks + 25 speech blocks = 35 * 320 = 11200
    assert seg.recorded_samples == 35 * 320

    # Feed trailing silence until emitted (450 ms = 7200 samples -> 23 blocks of 320 samples)
    emitted = None
    for _ in range(25):
        res = seg.process_block(_make_block(0.0, t, idx))
        t += 0.02
        idx += 1
        if res is not None:
            emitted = res
            break

    assert emitted is not None
    assert emitted.segment_id == 1
    assert emitted.emit_reason == "silence_timeout"
    assert emitted.is_forced_split is False
    # Audio includes 10 pre-roll + 25 speech + 23 silence = 58 blocks * 320 = 18560 samples
    assert emitted.audio.size == 58 * 320
    # Verify last_voice_at matches the final speech block timestamp, not the trailing silence end
    assert abs(emitted.last_voice_at - last_speech_time) < 1e-6
    assert emitted.capture_ended_at > emitted.last_voice_at
    assert seg.state == "IDLE"


def test_segmenter_discards_short_noise_burst() -> None:
    vad = RmsVAD(threshold=0.012)
    seg = SpeechSegmenter(
        vad=vad,
        sample_rate=16000,
        block_ms=20,
        pre_roll_ms=100,
        silence_ms=200,
        min_speech_ms=350,  # 5600 samples (~18 blocks)
        max_segment_ms=4000,
        overlap_ms=0,
    )

    t = 10.0
    # Only 5 blocks (100 ms) of voice -> below 350 ms min_speech_ms
    for i in range(5):
        assert seg.process_block(_make_block(0.05, t + i * 0.02, i)) is None

    # 15 blocks (300 ms) of silence -> triggers silence limit but should discard
    for i in range(5, 20):
        assert seg.process_block(_make_block(0.0, t + i * 0.02, i)) is None

    assert seg.state == "IDLE"
    assert seg.discarded_short_segments == 1
    assert seg.emitted_segments == 0


def test_segmenter_max_duration_cut_preserves_overlap() -> None:
    vad = RmsVAD(threshold=0.012)
    seg = SpeechSegmenter(
        vad=vad,
        sample_rate=16000,
        block_ms=20,
        pre_roll_ms=0,
        silence_ms=450,
        min_speech_ms=200,
        max_segment_ms=1000,  # 1.0s = 50 blocks (16000 samples)
        overlap_ms=160,       # 160ms = 8 blocks (2560 samples)
    )

    t = 0.0
    emitted_first = None
    for i in range(55):
        # Distinct amplitude per block so we can verify exact overlap samples
        amp = 0.02 + (i * 0.001)
        res = seg.process_block(_make_block(amp, t, i))
        t += 0.02
        if res is not None:
            emitted_first = res
            break

    assert emitted_first is not None
    assert emitted_first.segment_id == 1
    assert emitted_first.emit_reason == "max_duration"
    assert emitted_first.is_forced_split is True
    assert emitted_first.audio.size == 16000

    # Immediately after max_duration cut while still speaking, segmenter stays in RECORDING
    # with exactly overlap_samples (2560 samples) from the end of emitted_first.audio
    assert seg.state == "RECORDING"
    assert seg.recorded_samples == 2560
    np.testing.assert_allclose(seg._chunks[0], emitted_first.audio[-2560:])

    # Continue speaking 10 blocks then flush on shutdown
    for j in range(10):
        assert seg.process_block(_make_block(0.08, t, 100 + j)) is None
        t += 0.02

    flushed = seg.flush()
    assert flushed is not None
    assert flushed.segment_id == 2
    assert flushed.emit_reason == "flush"
    assert flushed.is_forced_split is True
    assert np.allclose(flushed.audio[:2560], emitted_first.audio[-2560:])
