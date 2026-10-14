from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np

from gemma_stt.audio_capture import AudioBlock
from gemma_stt.vad import VADDetector

logger = logging.getLogger("gemma_stt.segmenter")

SegmenterState = Literal["IDLE", "RECORDING"]
EmitReason = Literal["silence_timeout", "max_duration", "flush"]


@dataclass(slots=True)
class SpeechSegment:
    """A segmented chunk of speech ready for ASR inference."""

    segment_id: int
    audio: np.ndarray
    sample_rate: int
    capture_started_at: float
    speech_started_at: float
    last_voice_at: float
    capture_ended_at: float
    vad_emit_at: float
    queued_at: float = 0.0
    duration_s: float = 0.0
    speech_duration_s: float = 0.0
    emit_reason: EmitReason = "silence_timeout"
    is_forced_split: bool = False
    had_audio_drop: bool = False


class SpeechSegmenter:
    """VAD-driven state machine for near-real-time speech segmentation.

    State Machine (Section E3 & Section 14):
    - IDLE -> [VAD detects voice] -> RECORDING (prepends pre-roll buffer)
    - RECORDING -> [silence >= silence_ms] -> EMIT -> IDLE
    - RECORDING -> [duration >= max_segment_ms] -> EMIT -> RECORDING/IDLE (with dedicated overlap buffer)

    Maintains sample counts in O(1) time without summing chunk lengths repeatedly.
    """

    def __init__(
        self,
        vad: VADDetector,
        sample_rate: int = 16000,
        block_ms: int = 20,
        pre_roll_ms: int = 200,
        silence_ms: int = 450,
        min_speech_ms: int = 350,
        max_segment_ms: int = 4000,
        overlap_ms: int = 160,
    ) -> None:
        self.vad = vad
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.pre_roll_ms = pre_roll_ms
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_segment_ms = max_segment_ms
        self.overlap_ms = overlap_ms

        samples_per_ms = sample_rate // 1000
        self.pre_roll_max_blocks = max(1, pre_roll_ms // block_ms) if pre_roll_ms > 0 else 0
        self.silence_samples_limit = silence_ms * samples_per_ms
        self.min_speech_samples = min_speech_ms * samples_per_ms
        self.max_segment_samples = max_segment_ms * samples_per_ms
        self.overlap_samples = overlap_ms * samples_per_ms

        self.state: SegmenterState = "IDLE"
        self._next_segment_id: int = 1

        # O(1) maintained buffers and counters
        self._pre_roll: collections.deque[AudioBlock] = collections.deque(
            maxlen=self.pre_roll_max_blocks if self.pre_roll_max_blocks > 0 else 1
        )
        self._chunks: list[np.ndarray] = []
        self.recorded_samples: int = 0
        self.speech_samples: int = 0
        self.silence_samples: int = 0

        # Dedicated overlap buffer when max_segment_ms forces a cut
        self._overlap_buffer: np.ndarray | None = None
        self._overlap_timestamp: float = 0.0

        # Timestamps for current active segment
        self._capture_started_at: float = 0.0
        self._speech_started_at: float = 0.0
        self._last_voice_at: float = 0.0
        self._capture_ended_at: float = 0.0
        self._had_audio_drop: bool = False
        self._is_forced_continuation: bool = False

        # Telemetry counters
        self.emitted_segments: int = 0
        self.discarded_short_segments: int = 0
        self.forced_split_segments: int = 0

    def reset(self) -> None:
        """Reset segmenter state completely."""
        self.vad.reset()
        self.state = "IDLE"
        self._pre_roll.clear()
        self._clear_recording_buffers()
        self._overlap_buffer = None

    def _clear_recording_buffers(self) -> None:
        self._chunks = []
        self.recorded_samples = 0
        self.speech_samples = 0
        self.silence_samples = 0
        self._capture_started_at = 0.0
        self._speech_started_at = 0.0
        self._last_voice_at = 0.0
        self._capture_ended_at = 0.0
        self._had_audio_drop = False
        self._is_forced_continuation = False

    def process_block(self, block: AudioBlock) -> SpeechSegment | None:
        """Feed one AudioBlock into the state machine and return a SpeechSegment if emitted."""
        is_voice, _score = self.vad.is_speech(block.samples)
        n_samples = int(block.samples.size)
        if n_samples == 0:
            return None

        if self.state == "IDLE":
            if is_voice:
                self._start_recording(block, n_samples)
                # Edge case: if single block already exceeds max_segment_samples
                if self.recorded_samples >= self.max_segment_samples:
                    return self._handle_max_duration_cut(block, is_voice=True)
                return None
            else:
                if self.pre_roll_max_blocks > 0:
                    self._pre_roll.append(block)
                return None

        # State == "RECORDING"
        self._chunks.append(block.samples)
        self.recorded_samples += n_samples
        self._capture_ended_at = block.captured_at
        if block.dropped_before > 0:
            self._had_audio_drop = True

        if is_voice:
            self.speech_samples += n_samples
            self.silence_samples = 0
            self._last_voice_at = block.captured_at
        else:
            self.silence_samples += n_samples

        # Condition 1: Trailing silence reached silence_ms
        if self.silence_samples >= self.silence_samples_limit:
            return self._finalize_on_silence()

        # Condition 2: Segment length reached max_segment_ms
        if self.recorded_samples >= self.max_segment_samples:
            return self._handle_max_duration_cut(block, is_voice=is_voice)

        return None

    def _start_recording(self, trigger_block: AudioBlock, n_samples: int) -> None:
        self.state = "RECORDING"
        self._chunks = []
        self.recorded_samples = 0
        self.speech_samples = 0
        self.silence_samples = 0
        self._had_audio_drop = trigger_block.dropped_before > 0

        if self._overlap_buffer is not None and self._overlap_buffer.size > 0:
            self._chunks.append(self._overlap_buffer)
            self.recorded_samples += int(self._overlap_buffer.size)
            self._capture_started_at = self._overlap_timestamp
            self._overlap_buffer = None
        elif self.pre_roll_max_blocks > 0 and len(self._pre_roll) > 0:
            self._capture_started_at = self._pre_roll[0].captured_at
            for pr_block in self._pre_roll:
                self._chunks.append(pr_block.samples)
                self.recorded_samples += int(pr_block.samples.size)
                if pr_block.dropped_before > 0:
                    self._had_audio_drop = True
            self._pre_roll.clear()
        else:
            self._capture_started_at = trigger_block.captured_at

        self._chunks.append(trigger_block.samples)
        self.recorded_samples += n_samples
        self.speech_samples += n_samples
        self._speech_started_at = trigger_block.captured_at
        self._last_voice_at = trigger_block.captured_at
        self._capture_ended_at = trigger_block.captured_at

    def _finalize_on_silence(self) -> SpeechSegment | None:
        # Check minimum speech requirement
        if self.speech_samples < self.min_speech_samples:
            self.discarded_short_segments += 1
            logger.debug(
                "Discarded short segment (%d speech samples < %d min_speech_samples).",
                self.speech_samples,
                self.min_speech_samples,
            )
            self.state = "IDLE"
            self._clear_recording_buffers()
            return None

        segment = self._build_segment(
            emit_reason="silence_timeout",
            is_forced_split=self._is_forced_continuation,
        )
        self.state = "IDLE"
        self._clear_recording_buffers()
        return segment

    def _handle_max_duration_cut(self, current_block: AudioBlock, is_voice: bool) -> SpeechSegment | None:
        if self.speech_samples < self.min_speech_samples:
            self.discarded_short_segments += 1
            logger.debug("Discarded max-duration segment with insufficient voice samples.")
            self.state = "IDLE"
            self._clear_recording_buffers()
            return None

        self.forced_split_segments += 1
        segment = self._build_segment(
            emit_reason="max_duration",
            is_forced_split=True,
        )

        # Extract dedicated overlap tail from the emitted segment audio
        overlap_tail: np.ndarray | None = None
        if self.overlap_samples > 0 and segment.audio.size > 0:
            tail_len = min(self.overlap_samples, int(segment.audio.size))
            overlap_tail = segment.audio[-tail_len:].copy()

        # Transition: if user is still actively speaking, continue in RECORDING with overlap tail
        if is_voice:
            self.state = "RECORDING"
            self._chunks = []
            self.recorded_samples = 0
            self.speech_samples = 0
            self.silence_samples = 0
            self._had_audio_drop = False
            self._is_forced_continuation = True
            if overlap_tail is not None and overlap_tail.size > 0:
                self._chunks.append(overlap_tail)
                self.recorded_samples = int(overlap_tail.size)
                self.speech_samples = int(overlap_tail.size)
            self._capture_started_at = current_block.captured_at
            self._speech_started_at = current_block.captured_at
            self._last_voice_at = current_block.captured_at
            self._capture_ended_at = current_block.captured_at
        else:
            self.state = "IDLE"
            self._clear_recording_buffers()
            if overlap_tail is not None and overlap_tail.size > 0:
                self._overlap_buffer = overlap_tail
                self._overlap_timestamp = current_block.captured_at

        return segment

    def flush(self) -> SpeechSegment | None:
        """Flush any active recording when shutting down the application."""
        if self.state != "RECORDING" or not self._chunks:
            self.state = "IDLE"
            self._clear_recording_buffers()
            return None

        if self.speech_samples < self.min_speech_samples:
            self.discarded_short_segments += 1
            logger.debug(
                "Flush discarded short trailing segment (%d speech samples).",
                self.speech_samples,
            )
            self.state = "IDLE"
            self._clear_recording_buffers()
            return None

        segment = self._build_segment(
            emit_reason="flush",
            is_forced_split=self._is_forced_continuation,
        )
        self.state = "IDLE"
        self._clear_recording_buffers()
        return segment

    def _build_segment(
        self,
        emit_reason: EmitReason,
        is_forced_split: bool,
    ) -> SpeechSegment:
        full_audio = np.concatenate(self._chunks).astype(np.float32, copy=False)
        emit_time = time.monotonic()
        seg_id = self._next_segment_id
        self._next_segment_id += 1
        self.emitted_segments += 1

        duration_s = float(full_audio.size) / float(self.sample_rate)
        speech_duration_s = float(self.speech_samples) / float(self.sample_rate)
        last_voice = self._last_voice_at if self._last_voice_at > 0 else self._capture_ended_at

        return SpeechSegment(
            segment_id=seg_id,
            audio=full_audio,
            sample_rate=self.sample_rate,
            capture_started_at=self._capture_started_at,
            speech_started_at=self._speech_started_at,
            last_voice_at=last_voice,
            capture_ended_at=self._capture_ended_at,
            vad_emit_at=emit_time,
            queued_at=emit_time,
            duration_s=round(duration_s, 4),
            speech_duration_s=round(speech_duration_s, 4),
            emit_reason=emit_reason,
            is_forced_split=is_forced_split,
            had_audio_drop=self._had_audio_drop,
        )
