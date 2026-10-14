from __future__ import annotations

import collections
import logging
from typing import Any

import numpy as np

logger = logging.getLogger("claw.voice.vad")


class SileroVAD:
    """Voice Activity Detector with Silero ONNX model (v5 & v4 compatible) and adaptive energy fallback."""

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        silence_ms: int = 600,
        pre_roll_ms: int = 300,
        max_record_s: int = 30,
    ) -> None:
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms
        self.silence_ms = silence_ms
        self.pre_roll_ms = pre_roll_ms
        self.max_record_s = max_record_s

        self._session: Any = None
        self._use_v5_state: bool = False
        self._state: np.ndarray | None = None
        self._context: np.ndarray | None = None
        self._h: np.ndarray | None = None
        self._c: np.ndarray | None = None
        self._model_ready = False
        self._init_silero()

    def _init_silero(self) -> None:
        try:
            import urllib.request
            from pathlib import Path

            import onnxruntime as ort
            import platformdirs

            cache_dir = Path(platformdirs.user_cache_dir("claw", "claw-cli"))
            cache_dir.mkdir(parents=True, exist_ok=True)
            candidates = [
                cache_dir / "silero_vad.onnx",
                Path(__file__).resolve().parents[3] / ".cache" / "silero_vad.onnx",
            ]
            model_path = next((p for p in candidates if p.is_file()), candidates[0])

            if not model_path.is_file():
                url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
                try:
                    urllib.request.urlretrieve(url, model_path)
                except Exception as e:
                    logger.debug(f"Could not download silero model: {e}")

            if model_path.is_file():
                opts = ort.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                self._session = ort.InferenceSession(
                    str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
                )
                input_names = {i.name for i in self._session.get_inputs()}
                self._use_v5_state = "state" in input_names
                self._reset_states()
                self._model_ready = True
        except Exception as e:
            logger.debug(f"Silero ONNX VAD initialization skipped: {e}. Using energy VAD fallback.")

    def _reset_states(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        ctx_size = 64 if self.sample_rate == 16000 else 32
        self._context = np.zeros((1, ctx_size), dtype=np.float32)
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def is_speech(self, frame: np.ndarray) -> float:
        """Return speech probability (0.0 to 1.0) for a 16kHz audio frame."""
        if frame.dtype == np.int16:
            audio_f32 = frame.astype(np.float32) / 32768.0
        else:
            audio_f32 = frame.astype(np.float32)

        if self._model_ready and self._session is not None:
            try:
                if len(audio_f32) != 512:
                    if len(audio_f32) < 512:
                        audio_f32 = np.pad(audio_f32, (0, 512 - len(audio_f32)))
                    else:
                        audio_f32 = audio_f32[:512]

                x = np.expand_dims(audio_f32, axis=0)
                sr_arr = np.array(self.sample_rate, dtype=np.int64)

                if self._use_v5_state:
                    if self._context is None or self._state is None:
                        self._reset_states()
                    assert self._context is not None and self._state is not None
                    x_input = np.concatenate([self._context, x], axis=1)
                    self._context = x[:, -self._context.shape[1] :]
                    out, new_state = self._session.run(
                        None,
                        {
                            "input": x_input,
                            "state": self._state,
                            "sr": sr_arr,
                        },
                    )
                    self._state = new_state
                    return float(out[0][0])
                else:
                    inputs = {
                        "input": x,
                        "sr": sr_arr,
                        "h": self._h,
                        "c": self._c,
                    }
                    out, h, c = self._session.run(None, inputs)
                    self._h = h
                    self._c = c
                    return float(out[0][0])
            except Exception as e:
                logger.debug(f"Silero ONNX inference error: {e}")

        # Energy fallback
        rms = float(np.sqrt(np.mean(audio_f32**2))) if audio_f32.size > 0 else 0.0
        return 1.0 if rms > 0.015 else 0.0


class UtteranceDetector:
    """Processes a stream of PCM frames and automatically detects end-of-utterance (EOU)."""

    def __init__(self, vad: SileroVAD | None = None) -> None:
        self.vad = vad or SileroVAD()
        samples_per_ms = self.vad.sample_rate // 1000
        self.pre_roll_samples = self.vad.pre_roll_ms * samples_per_ms
        self.min_speech_samples = self.vad.min_speech_ms * samples_per_ms
        self.silence_limit_frames = max(1, int(self.vad.silence_ms / 32))  # ~32ms per 512 frame at 16k
        self.max_samples = self.vad.max_record_s * self.vad.sample_rate

        self._noise_rms: float = 0.005
        self.reset()

    def reset(self) -> None:
        self.vad._reset_states()
        self.pre_roll_buffer: collections.deque[np.ndarray] = collections.deque(maxlen=10)
        self.speech_frames: list[np.ndarray] = []
        self.in_speech = False
        self.silence_counter = 0
        self.peak_rms: float = 0.0

    @staticmethod
    def _frame_rms(frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        f32 = frame.astype(np.float32) / 32768.0 if frame.dtype == np.int16 else frame.astype(np.float32)
        return float(np.sqrt(np.mean(f32**2)))

    def process_frame(self, frame: np.ndarray) -> np.ndarray | None:
        """Feed an audio frame (512 samples int16).

        Returns complete utterance PCM array as soon as the speaker pauses after speaking,
        or None if still listening.
        """
        prob = self.vad.is_speech(frame)
        rms = self._frame_rms(frame)

        if not self.in_speech:
            self.pre_roll_buffer.append(frame)
            if prob >= self.vad.threshold:
                self.in_speech = True
                self.speech_frames = list(self.pre_roll_buffer)
                self.silence_counter = 0
                self.peak_rms = max(rms, 0.015)
            else:
                # Update adaptive background noise estimate slowly
                self._noise_rms = 0.95 * self._noise_rms + 0.05 * rms
            return None
        else:
            self.speech_frames.append(frame)
            if rms > self.peak_rms:
                self.peak_rms = rms

            # Hysteresis: end threshold is slightly lower than start threshold,
            # and also checks if energy has dropped sharply relative to peak speech energy
            # (handling noisy microphones when using energy fallback).
            end_threshold = max(0.25, self.vad.threshold * 0.7)
            energy_dropped = (not self.vad._model_ready) and (
                rms < max(self._noise_rms * 1.6, self.peak_rms * 0.22)
            )
            still_speaking = (prob >= end_threshold) and not energy_dropped

            if still_speaking:
                self.silence_counter = 0
            else:
                self.silence_counter += 1

            total_samples = sum(len(f) for f in self.speech_frames)

            # Check if silence duration reached (end of sentence) or max length exceeded
            if self.silence_counter >= self.silence_limit_frames or total_samples >= self.max_samples:
                if total_samples >= self.min_speech_samples:
                    complete_audio = np.concatenate(self.speech_frames)
                    self.reset()
                    return complete_audio
                else:
                    # Too short, discard as transient noise
                    self.reset()
                    return None

        return None
