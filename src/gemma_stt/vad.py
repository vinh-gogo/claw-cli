from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger("gemma_stt.vad")


def compute_rms(audio_block: np.ndarray) -> float:
    """Compute Root Mean Square (RMS) energy of an audio block in float32."""
    if audio_block.size == 0:
        return 0.0
    arr = audio_block.astype(np.float32, copy=False)
    if audio_block.dtype == np.int16:
        arr = arr / 32768.0
    return float((arr**2).mean() ** 0.5)


class VADDetector(Protocol):
    """Protocol for Voice Activity Detectors."""

    def is_speech(self, audio_block: np.ndarray) -> tuple[bool, float]:
        """Return (is_voice, score) for a mono 16kHz audio block."""
        ...

    def reset(self) -> None:
        """Reset internal state between utterances."""
        ...


class RmsVAD:
    """Simple RMS-based Voice Activity Detector (Phase E1 MVP)."""

    def __init__(self, threshold: float = 0.012) -> None:
        self.threshold = float(threshold)

    def is_speech(self, audio_block: np.ndarray) -> tuple[bool, float]:
        rms = compute_rms(audio_block)
        return (rms >= self.threshold, rms)

    def reset(self) -> None:
        pass


class SileroOnnxVAD:
    """Silero ONNX Voice Activity Detector (Phase E4 upgrade) with RMS fallback.

    Accepts 20ms (320-sample) or 32ms (512-sample) 16kHz blocks by maintaining
    a rolling 512-sample window for the Silero ONNX model.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        rms_fallback_threshold: float = 0.012,
    ) -> None:
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.rms_fallback_threshold = rms_fallback_threshold
        self._session: Any = None
        self._use_v5_state: bool = False
        self._state: np.ndarray | None = None
        self._context: np.ndarray | None = None
        self._h: np.ndarray | None = None
        self._c: np.ndarray | None = None
        self._window = np.zeros(512, dtype=np.float32)
        self._model_ready = False
        self._init_onnx()

    def _init_onnx(self) -> None:
        try:
            import onnxruntime as ort
            import platformdirs

            cache_candidates = [
                Path(__file__).resolve().parents[2] / ".cache" / "silero_vad.onnx",
                Path("D:/claw-cli/.cache/silero_vad.onnx"),
                Path(platformdirs.user_cache_dir("claw", "claw-cli")) / "silero_vad.onnx",
            ]
            model_path: Path | None = next((p for p in cache_candidates if p.is_file()), None)

            if model_path is None:
                import os
                import urllib.request

                if os.environ.get("HF_HUB_OFFLINE") not in ("1", "true", "True"):
                    target = cache_candidates[0]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
                    try:
                        urllib.request.urlretrieve(url, target)
                        model_path = target
                    except Exception as dl_err:
                        logger.debug("Could not download silero_vad.onnx: %s", dl_err)

            if model_path is not None and model_path.is_file():
                opts = ort.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                self._session = ort.InferenceSession(
                    str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
                )
                input_names = {i.name for i in self._session.get_inputs()}
                self._use_v5_state = "state" in input_names
                self.reset()
                self._model_ready = True
                logger.info("Loaded Silero ONNX VAD from %s", model_path)
        except Exception as exc:
            logger.warning("Silero ONNX VAD unavailable (%s); falling back to RMS VAD.", exc)
            self._model_ready = False

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        ctx_size = 64 if self.sample_rate == 16000 else 32
        self._context = np.zeros((1, ctx_size), dtype=np.float32)
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
        self._window.fill(0.0)

    def is_speech(self, audio_block: np.ndarray) -> tuple[bool, float]:
        if audio_block.size == 0:
            return (False, 0.0)

        arr = audio_block.astype(np.float32, copy=False).reshape(-1)
        if audio_block.dtype == np.int16:
            arr = arr / 32768.0

        if self._model_ready and self._session is not None:
            try:
                n = len(arr)
                if n >= 512:
                    self._window[:] = arr[-512:]
                else:
                    self._window[:-n] = self._window[n:]
                    self._window[-n:] = arr

                x = np.expand_dims(self._window, axis=0)
                sr_arr = np.array(self.sample_rate, dtype=np.int64)

                if self._use_v5_state:
                    if self._context is None or self._state is None:
                        self.reset()
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
                    prob = float(out[0][0])
                    return (prob >= self.threshold, prob)
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
                    prob = float(out[0][0])
                    return (prob >= self.threshold, prob)
            except Exception as exc:
                logger.debug("Silero ONNX runtime error: %s", exc)

        rms = compute_rms(arr)
        return (rms >= self.rms_fallback_threshold, rms)


def create_vad(
    engine: str = "rms",
    sample_rate: int = 16000,
    rms_threshold: float = 0.012,
    silero_threshold: float = 0.5,
) -> VADDetector:
    if engine.lower() == "silero":
        return SileroOnnxVAD(
            sample_rate=sample_rate,
            threshold=silero_threshold,
            rms_fallback_threshold=rms_threshold,
        )
    return RmsVAD(threshold=rms_threshold)
