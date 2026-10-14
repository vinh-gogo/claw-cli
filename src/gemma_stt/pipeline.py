from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from gemma_stt.audio_capture import AudioBlock, MicrophoneCapture
from gemma_stt.config_schema import GemmaSTTConfig
from gemma_stt.metrics import TranscriptionResult
from gemma_stt.model_runner import STTModelRunner, pcm_float32_to_wav_bytes
from gemma_stt.output_writer import OutputWriter
from gemma_stt.segmenter import SpeechSegment, SpeechSegmenter
from gemma_stt.vad import create_vad

logger = logging.getLogger("gemma_stt.pipeline")


class NearRealtimeSTTPipeline:
    """Multi-threaded near-real-time speech-to-text pipeline (Sections D, E, F, G).

    Threads:
    1. Microphone callback thread (sounddevice) -> bounded audio queue.
    2. Segmenter worker thread -> reads audio blocks, runs VAD + SpeechSegmenter,
       enqueues SpeechSegments into bounded inference_queue according to policy.
    3. Inference worker thread -> dequeues SpeechSegments, runs STTModelRunner,
       computes 4-stage latency metrics, writes ordered results via OutputWriter.

    Guarantees:
    - Never silently drops audio or segments: all drops are logged and recorded in results.jsonl.
    - Graceful shutdown: stops mic, flushes trailing utterance, drains inference queue before exit.
    """

    def __init__(
        self,
        cfg: GemmaSTTConfig,
        model_runner: STTModelRunner,
        output_writer: OutputWriter | None = None,
        on_result: Callable[[TranscriptionResult], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.model_runner = model_runner
        self.output_writer = output_writer or OutputWriter(cfg.output, console_callback=on_result)

        self.vad = create_vad(
            engine=cfg.vad.engine,
            sample_rate=cfg.audio.sample_rate,
            rms_threshold=cfg.vad.threshold,
            silero_threshold=cfg.vad.silero_threshold,
        )
        self.segmenter = SpeechSegmenter(
            vad=self.vad,
            sample_rate=cfg.audio.sample_rate,
            block_ms=cfg.audio.block_ms,
            pre_roll_ms=cfg.vad.pre_roll_ms,
            silence_ms=cfg.vad.silence_ms,
            min_speech_ms=cfg.vad.min_speech_ms,
            max_segment_ms=cfg.vad.max_segment_ms,
            overlap_ms=cfg.vad.overlap_ms,
        )
        self.capture = MicrophoneCapture(
            sample_rate=cfg.audio.sample_rate,
            channels=cfg.audio.channels,
            block_ms=cfg.audio.block_ms,
            max_blocks=cfg.queue.audio_max_blocks,
            device=cfg.audio.device,
        )

        self.inference_queue: queue.Queue[SpeechSegment | None] = queue.Queue(
            maxsize=cfg.queue.inference_max_segments
        )
        self._stop_capture_event = threading.Event()
        self._abort_drain_event = threading.Event()
        self._segmenter_thread: threading.Thread | None = None
        self._inference_thread: threading.Thread | None = None

        # Telemetry counters
        self.queue_full_events: int = 0
        self.dropped_segments: int = 0
        self.completed_segments: int = 0

    def enqueue_segment(self, segment: SpeechSegment) -> bool:
        """Enqueue a SpeechSegment into inference_queue following configured queue policy.

        Returns True if enqueued without dropping, False if a segment was dropped.
        """
        segment.queued_at = time.monotonic()
        policy = self.cfg.queue.policy

        if policy == "preserve_segments":
            # Wait with backpressure logging until space is available or abort is signaled
            warned = False
            while not self._abort_drain_event.is_set():
                try:
                    self.inference_queue.put(segment, timeout=0.05)
                    return True
                except queue.Full:
                    if not warned:
                        self.queue_full_events += 1
                        warned = True
                        logger.warning(
                            "Inference queue full (max=%d) [preserve_segments]: applying backpressure for segment #%d.",
                            self.cfg.queue.inference_max_segments,
                            segment.segment_id,
                        )
            return False

        # policy == "ultra_low_latency": drop oldest queued segment to make room for newest
        try:
            self.inference_queue.put_nowait(segment)
            return True
        except queue.Full:
            self.queue_full_events += 1
            dropped_seg: SpeechSegment | None = None
            try:
                candidate = self.inference_queue.get_nowait()
                if candidate is not None:
                    dropped_seg = candidate
            except queue.Empty:
                pass

            if dropped_seg is not None:
                self.dropped_segments += 1
                now = time.monotonic()
                queue_age = max(0.0, now - dropped_seg.vad_emit_at)
                logger.warning(
                    "OVERLOAD [ultra_low_latency]: Dropped oldest segment #%d (duration=%.2fs, queue_age=%.2fs) to prioritize segment #%d.",
                    dropped_seg.segment_id,
                    dropped_seg.duration_s,
                    queue_age,
                    segment.segment_id,
                )
                drop_result = TranscriptionResult(
                    segment_id=dropped_seg.segment_id,
                    text="",
                    duration_s=dropped_seg.duration_s,
                    speech_duration_s=dropped_seg.speech_duration_s,
                    vad_delay_s=max(0.0, dropped_seg.vad_emit_at - dropped_seg.last_voice_at),
                    queue_wait_s=queue_age,
                    inference_s=0.0,
                    e2e_voice_end_s=max(0.0, now - dropped_seg.last_voice_at),
                    e2e_buffer_end_s=max(0.0, now - dropped_seg.capture_ended_at),
                    rtf=0.0,
                    peak_vram_mb=0.0,
                    dropped=True,
                    had_audio_drop=dropped_seg.had_audio_drop,
                    emit_reason=dropped_seg.emit_reason,
                    is_forced_split=dropped_seg.is_forced_split,
                    backend=self.model_runner.backend_name,
                )
                self.output_writer.write(drop_result)

            try:
                self.inference_queue.put_nowait(segment)
            except queue.Full:
                pass
            return False

    def process_segment_sync(self, segment: SpeechSegment) -> TranscriptionResult:
        """Run inference on a single SpeechSegment and record timing metrics."""
        if self.cfg.output.save_debug_wav:
            self._save_debug_wav(segment)

        infer_start = time.monotonic()
        text, peak_vram_mb = self.model_runner.transcribe(segment.audio, segment.sample_rate)
        result_ready = time.monotonic()

        vad_delay = max(0.0, segment.vad_emit_at - segment.last_voice_at)
        queue_wait = max(0.0, infer_start - segment.vad_emit_at)
        infer_latency = max(0.0, result_ready - infer_start)
        e2e_voice = max(0.0, result_ready - segment.last_voice_at)
        e2e_buffer = max(0.0, result_ready - segment.capture_ended_at)
        rtf = infer_latency / segment.duration_s if segment.duration_s > 0 else 0.0

        result = TranscriptionResult(
            segment_id=segment.segment_id,
            text=text,
            duration_s=segment.duration_s,
            speech_duration_s=segment.speech_duration_s,
            vad_delay_s=vad_delay,
            queue_wait_s=queue_wait,
            inference_s=infer_latency,
            e2e_voice_end_s=e2e_voice,
            e2e_buffer_end_s=e2e_buffer,
            rtf=rtf,
            peak_vram_mb=peak_vram_mb,
            dropped=False,
            had_audio_drop=segment.had_audio_drop,
            emit_reason=segment.emit_reason,
            is_forced_split=segment.is_forced_split,
            backend=self.model_runner.backend_name,
        )
        self.completed_segments += 1
        self.output_writer.write(result)
        return result

    def _save_debug_wav(self, segment: SpeechSegment) -> Path:
        self.cfg.output.debug_wav_dir.mkdir(parents=True, exist_ok=True)
        wav_path = self.cfg.output.debug_wav_dir / f"seg_{segment.segment_id:04d}.wav"
        wav_bytes = pcm_float32_to_wav_bytes(segment.audio, segment.sample_rate)
        wav_path.write_bytes(wav_bytes)
        return wav_path

    def _segmenter_loop(self) -> None:
        try:
            while not self._stop_capture_event.is_set():
                block: AudioBlock | None = self.capture.get_block(timeout=0.05)
                if block is None:
                    continue
                seg = self.segmenter.process_block(block)
                if seg is not None:
                    self.enqueue_segment(seg)
        except Exception as exc:
            logger.error("Segmenter worker error: %s", exc)
            self._stop_capture_event.set()
        finally:
            # Flush any trailing speech segment on shutdown
            if not self._abort_drain_event.is_set():
                final_seg = self.segmenter.flush()
                if final_seg is not None:
                    self.enqueue_segment(final_seg)
            # Send sentinel to inference thread
            while not self._abort_drain_event.is_set():
                try:
                    self.inference_queue.put(None, timeout=0.05)
                    break
                except queue.Full:
                    continue

    def _inference_loop(self) -> None:
        while not self._abort_drain_event.is_set():
            try:
                seg = self.inference_queue.get(timeout=0.05)
            except queue.Empty:
                if self._stop_capture_event.is_set() and self.inference_queue.empty():
                    # Wait briefly for segmenter thread to push sentinel
                    if self._segmenter_thread is not None and not self._segmenter_thread.is_alive():
                        break
                continue

            if seg is None:
                break

            try:
                self.process_segment_sync(seg)
            except Exception as exc:
                logger.error("Inference error on segment #%d: %s", seg.segment_id, exc)

    def start(self) -> None:
        """Start microphone stream, segmenter thread, and inference worker thread."""
        self._stop_capture_event.clear()
        self._abort_drain_event.clear()

        self._inference_thread = threading.Thread(
            target=self._inference_loop, name="GemmaSTT-InferenceWorker", daemon=False
        )
        self._segmenter_thread = threading.Thread(
            target=self._segmenter_loop, name="GemmaSTT-SegmenterWorker", daemon=False
        )

        self._inference_thread.start()
        self._segmenter_thread.start()
        self.capture.start()

    def stop(self, drain: bool = True, timeout: float = 30.0) -> None:
        """Gracefully stop capture, flush active utterance, and drain inference queue."""
        if not drain:
            self._abort_drain_event.set()

        self._stop_capture_event.set()
        self.capture.stop()

        if self._segmenter_thread is not None and self._segmenter_thread.is_alive():
            self._segmenter_thread.join(timeout=5.0)

        if self._inference_thread is not None and self._inference_thread.is_alive():
            self._inference_thread.join(timeout=timeout)

        self.output_writer.flush_remaining()
