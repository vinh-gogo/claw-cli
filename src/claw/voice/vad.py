from __future__ import annotations

import collections
import logging
from typing import Any

import numpy as np

logger = logging.getLogger("claw.voice.vad")


class SileroVAD:
    """Voice Activity Detector with Silero ONNX model and energy fallback."""

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        silence_ms: int = 900,
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
        self._h: np.ndarray | None = None
        self._c: np.ndarray | None = None
        self._model_ready = False
        self._init_silero()

    def _init_silero(self) -> None:
        try:
            # Check if silero-vad model exists locally or download if possible
            import urllib.request
            from pathlib import Path

            import onnxruntime as ort
            import platformdirs

            cache_dir = Path(platformdirs.user_cache_dir("claw", "claw-cli"))
            cache_dir.mkdir(parents=True, exist_ok=True)
            model_path = cache_dir / "silero_vad.onnx"

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
                self._session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
                self._reset_states()
                self._model_ready = True
        except Exception as e:
            logger.debug(f"Silero ONNX VAD initialization skipped: {e}. Using energy VAD fallback.")

    def _reset_states(self) -> None:
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def is_speech(self, frame: np.ndarray) -> float:
        """Return speech probability (0.0 to 1.0) for a 16kHz audio frame."""
        # Convert int16 to float32
        if frame.dtype == np.int16:
            audio_f32 = frame.astype(np.float32) / 32768.0
        else:
            audio_f32 = frame.astype(np.float32)

        if self._model_ready and self._session is not None:
            try:
                # Silero expects 512 samples for 16kHz
                if len(audio_f32) != 512:
                    if len(audio_f32) < 512:
                        audio_f32 = np.pad(audio_f32, (0, 512 - len(audio_f32)))
                    else:
                        audio_f32 = audio_f32[:512]

                inputs = {
                    "input": np.expand_dims(audio_f32, axis=0),
                    "sr": np.array(self.sample_rate, dtype=np.int64),
                    "h": self._h,
                    "c": self._c,
                }
                out, h, c = self._session.run(None, inputs)
                self._h = h
                self._c = c
                return float(out[0][0])
            except Exception:
                pass

        # Energy fallback
        rms = np.sqrt(np.mean(audio_f32**2))
        return 1.0 if rms > 0.015 else 0.0


class UtteranceDetector:
    """Processes a stream of PCM frames and detects complete utterances."""

    def __init__(self, vad: SileroVAD | None = None) -> None:
        self.vad = vad or SileroVAD()
        samples_per_ms = self.vad.sample_rate // 1000
        self.pre_roll_samples = self.vad.pre_roll_ms * samples_per_ms
        self.min_speech_samples = self.vad.min_speech_ms * samples_per_ms
        self.silence_limit_frames = int(self.vad.silence_ms / 32)  # ~32ms per 512 frame at 16k
        self.max_samples = self.vad.max_record_s * self.vad.sample_rate

        self.reset()

    def reset(self) -> None:
        self.vad._reset_states()
        self.pre_roll_buffer: collections.deque[np.ndarray] = collections.deque(maxlen=10)
        self.speech_frames: list[np.ndarray] = []
        self.in_speech = False
        self.silence_counter = 0

    def process_frame(self, frame: np.ndarray) -> np.ndarray | None:
        """Feed an audio frame (512 samples int16).

        Returns complete utterance PCM array if utterance completed, or None if still listening.
        """
        prob = self.vad.is_speech(frame)
        is_speech = prob >= self.vad.threshold

        if not self.in_speech:
            self.pre_roll_buffer.append(frame)
            if is_speech:
                self.in_speech = True
                self.speech_frames = list(self.pre_roll_buffer)
                self.silence_counter = 0
            return None
        else:
            self.speech_frames.append(frame)
            if is_speech:
                self.silence_counter = 0
            else:
                self.silence_counter += 1

            total_samples = sum(len(f) for f in self.speech_frames)

            # Check if silence duration reached or max length exceeded
            if self.silence_counter >= self.silence_limit_frames or total_samples >= self.max_samples:
                if total_samples >= self.min_speech_samples:
                    complete_audio = np.concatenate(self.speech_frames)
                    self.reset()
                    return complete_audio
                else:
                    # Too short, discard as noise
                    self.reset()
                    return None

        return None
