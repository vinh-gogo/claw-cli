from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from gemma_stt.audio_capture import MicrophoneCapture
from gemma_stt.config_schema import GemmaSTTConfig
from gemma_stt.output_writer import OutputWriter
from gemma_stt.pipeline import NearRealtimeSTTPipeline
from gemma_stt.segmenter import SpeechSegment


class SlowFakeRunner:
    backend_name = "slow_fake"

    def __init__(self, delay_s: float = 0.08) -> None:
        self.delay_s = delay_s
        self.calls: list[ int ] = []

    def load(self) -> None:
        pass

    def warmup(self, runs: int = 1) -> None:
        pass

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        time.sleep(self.delay_s)
        return (f"câu mẫu {len(audio)}", 512.0)


def _make_segment(seg_id: int) -> SpeechSegment:
    now = time.monotonic()
    return SpeechSegment(
        segment_id=seg_id,
        audio=np.full(3200, 0.05, dtype=np.float32),
        sample_rate=16000,
        capture_started_at=now - 0.5,
        speech_started_at=now - 0.4,
        last_voice_at=now - 0.1,
        capture_ended_at=now,
        vad_emit_at=now,
        duration_s=0.4,
        speech_duration_s=0.3,
    )


def test_preserve_segments_policy_drops_nothing(tmp_path: Path) -> None:
    cfg = GemmaSTTConfig()
    cfg.queue.inference_max_segments = 2
    cfg.queue.policy = "preserve_segments"
    cfg.output.transcript_path = tmp_path / "transcript.txt"
    cfg.output.results_path = tmp_path / "results.jsonl"
    cfg.output.metrics_path = tmp_path / "metrics.csv"

    runner = SlowFakeRunner(delay_s=0.04)
    writer = OutputWriter(cfg.output)
    pipeline = NearRealtimeSTTPipeline(cfg=cfg, model_runner=runner, output_writer=writer)

    # Start only the inference thread to test queue backpressure & draining
    import threading

    pipeline._inference_thread = threading.Thread(target=pipeline._inference_loop, daemon=False)
    pipeline._inference_thread.start()

    for i in range(1, 7):
        ok = pipeline.enqueue_segment(_make_segment(i))
        assert ok is True

    pipeline._stop_capture_event.set()
    pipeline.inference_queue.put(None)
    pipeline._inference_thread.join(timeout=5.0)
    writer.flush_remaining()

    assert pipeline.dropped_segments == 0
    assert len(writer.history) == 6
    assert [r.segment_id for r in writer.history] == [1, 2, 3, 4, 5, 6]
    assert all(not r.dropped for r in writer.history)


def test_ultra_low_latency_policy_logs_and_records_dropped_segments(tmp_path: Path) -> None:
    cfg = GemmaSTTConfig()
    cfg.queue.inference_max_segments = 2
    cfg.queue.policy = "ultra_low_latency"
    cfg.output.transcript_path = tmp_path / "transcript.txt"
    cfg.output.results_path = tmp_path / "results.jsonl"
    cfg.output.metrics_path = tmp_path / "metrics.csv"

    runner = SlowFakeRunner(delay_s=0.01)
    writer = OutputWriter(cfg.output)
    pipeline = NearRealtimeSTTPipeline(cfg=cfg, model_runner=runner, output_writer=writer)

    # Without starting consumer yet, push 4 segments into maxsize=2 queue
    assert pipeline.enqueue_segment(_make_segment(1)) is True
    assert pipeline.enqueue_segment(_make_segment(2)) is True
    # Segment 3 & 4 should evict oldest segments 1 & 2 and record them as dropped=True
    assert pipeline.enqueue_segment(_make_segment(3)) is False
    assert pipeline.enqueue_segment(_make_segment(4)) is False

    assert pipeline.dropped_segments == 2

    # Drain remaining segments 3 & 4
    while not pipeline.inference_queue.empty():
        seg = pipeline.inference_queue.get_nowait()
        if seg is not None:
            pipeline.process_segment_sync(seg)

    writer.flush_remaining()
    assert len(writer.history) == 4
    assert [r.segment_id for r in writer.history] == [1, 2, 3, 4]
    assert writer.history[0].dropped is True
    assert writer.history[1].dropped is True
    assert writer.history[2].dropped is False
    assert writer.history[3].dropped is False


def test_audio_capture_callback_never_silently_drops() -> None:
    cap = MicrophoneCapture(sample_rate=16000, channels=1, block_ms=20, max_blocks=10)
    cap._running = True
    dummy_indata = np.full((320, 1), 0.1, dtype=np.float32)

    # Push 13 blocks into maxsize=10 queue
    for _ in range(13):
        cap._audio_callback(dummy_indata, 320, None, None)

    assert cap.total_blocks_captured == 13
    assert cap.dropped_blocks == 3

    # Drain queue, then push 1 more block and verify dropped_before carries the 3 drops
    for _ in range(10):
        b = cap.get_block(timeout=0.01)
        assert b is not None

    cap._audio_callback(dummy_indata, 320, None, None)
    next_block = cap.get_block(timeout=0.01)
    assert next_block is not None
    assert next_block.dropped_before == 3
