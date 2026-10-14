from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from claw.config import STTConfig
from claw.voice.stt.base import Segment, Transcript

logger = logging.getLogger("claw.voice.stt")

HALLUCINATION_PATTERNS = [
    "cảm ơn các bạn đã xem",
    "cảm ơn các bạn đã theo dõi",
    "hãy like và subscribe",
    "chúc các bạn một ngày tốt lành",
    "subtitles by",
]


class FasterWhisperSTT:
    def __init__(self, cfg: STTConfig) -> None:
        self.cfg = cfg
        self._model: Any = None
        self._loading = False
        self._load_lock = asyncio.Lock()

    def _load_model_sync(self, force_cpu: bool = False) -> Any:
        from faster_whisper import WhisperModel

        device = "cpu" if force_cpu else self.cfg.device
        compute_type = "int8" if device == "cpu" else self.cfg.compute_type
        logger.info(f"Loading faster-whisper model '{self.cfg.model}' on {device} ({compute_type})...")
        try:
            return WhisperModel(
                self.cfg.model,
                device=device,
                compute_type=compute_type,
            )
        except Exception as e:
            if device != "cpu":
                logger.warning(f"CUDA load failed for faster-whisper ({e}); falling back to CPU (int8).")
                return WhisperModel(
                    self.cfg.model,
                    device="cpu",
                    compute_type="int8",
                )
            raise

    async def prewarm(self) -> None:
        """Prewarm model in background thread so first user utterance is fast."""
        if self._model is not None or self._loading:
            return
        async with self._load_lock:
            if self._model is None:
                self._loading = True
                try:
                    self._model = await asyncio.to_thread(self._load_model_sync)
                    logger.info("faster-whisper model prewarmed successfully.")
                except Exception as e:
                    logger.warning(f"Could not prewarm faster-whisper model: {e}")
                finally:
                    self._loading = False

    async def transcribe(self, pcm: np.ndarray, sample_rate: int = 16000, language: str = "vi") -> Transcript:
        """Transcribe a 16kHz int16 or float32 PCM array."""
        if self._model is None:
            await self.prewarm()

        if self._model is None:
            # If model still failed to load, return empty
            return Transcript(text="", language=language, confidence=0.0)

        # Convert int16 to float32 normalized [-1.0, 1.0] as faster_whisper expects
        if pcm.dtype == np.int16:
            audio_f32 = pcm.astype(np.float32) / 32768.0
        else:
            audio_f32 = pcm.astype(np.float32)

        def _do_transcribe() -> Transcript:
            try:
                segments_gen, info = self._model.transcribe(
                    audio_f32,
                    language=language or self.cfg.language,
                    initial_prompt=self.cfg.initial_prompt,
                    vad_filter=True,
                    beam_size=5,
                )
                raw_segments = list(segments_gen)
            except Exception as err:
                err_msg = str(err).lower()
                if any(k in err_msg for k in ("cublas", "cudnn", "cuda", ".dll", ".so")):
                    logger.warning(
                        f"CUDA runtime DLL missing during transcribe ({err}); reloading faster-whisper on CPU..."
                    )
                    self._model = self._load_model_sync(force_cpu=True)
                    segments_gen, info = self._model.transcribe(
                        audio_f32,
                        language=language or self.cfg.language,
                        initial_prompt=self.cfg.initial_prompt,
                        vad_filter=True,
                        beam_size=5,
                    )
                    raw_segments = list(segments_gen)
                else:
                    raise

            segments: list[Segment] = []
            text_parts: list[str] = []
            total_confidence = 0.0

            for s in raw_segments:
                clean_text = s.text.strip()
                # Hallucination filter
                if any(h in clean_text.lower() for h in HALLUCINATION_PATTERNS):
                    continue
                if s.no_speech_prob > 0.65:
                    continue

                conf = float(np.exp(s.avg_logprob)) if hasattr(np, "exp") else 0.8
                total_confidence += conf
                segments.append(
                    Segment(
                        start=s.start,
                        end=s.end,
                        text=clean_text,
                        avg_logprob=s.avg_logprob,
                        no_speech_prob=s.no_speech_prob,
                    )
                )
                text_parts.append(clean_text)

            full_text = " ".join(text_parts).strip()
            avg_conf = (total_confidence / len(segments)) if segments else 0.0
            return Transcript(
                text=full_text,
                language=info.language,
                confidence=round(avg_conf, 3),
                segments=segments,
            )

        return await asyncio.to_thread(_do_transcribe)
