from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np

from claw.config import LLMConfig, STTConfig
from claw.voice.stt.base import Transcript
from gemma_stt.config_schema import GemmaSTTConfig
from gemma_stt.model_runner import STTModelRunner, create_model_runner

logger = logging.getLogger("claw.voice.stt.gemma")


class Gemma4STTProvider:
    """Adapter integrating gemma_stt (Local Gemma 4 E2B or Remote /v1) into claw-cli."""

    def __init__(
        self,
        config_path: str | Path = "config.yaml",
        llm_cfg: LLMConfig | None = None,
        stt_cfg: STTConfig | None = None,
    ) -> None:
        self.cfg = GemmaSTTConfig.load(config_path)
        if llm_cfg is not None:
            self.cfg.remote_v1.base_url = llm_cfg.base_url
            self.cfg.remote_v1.api_key = llm_cfg.api_key
            self.cfg.remote_v1.extra_headers.update(llm_cfg.extra_headers)
        if stt_cfg is not None and stt_cfg.model and stt_cfg.model != "medium":
            self.cfg.remote_v1.model = stt_cfg.model
        self._runner: STTModelRunner | None = None
        self._load_lock = asyncio.Lock()

    async def prewarm(self) -> None:
        if self._runner is not None:
            return
        async with self._load_lock:
            if self._runner is None:
                try:
                    self._runner = await asyncio.to_thread(create_model_runner, self.cfg)
                except Exception as exc:
                    logger.debug("Could not prewarm Gemma4STTProvider: %s", exc)

    async def transcribe(
        self, pcm: np.ndarray, sample_rate: int = 16000, language: str = "vi"
    ) -> Transcript:
        if self._runner is None:
            async with self._load_lock:
                if self._runner is None:
                    self._runner = await asyncio.to_thread(create_model_runner, self.cfg)

        if pcm.dtype == np.int16:
            audio_f32 = pcm.astype(np.float32) / 32768.0
        else:
            audio_f32 = pcm.astype(np.float32)

        text, _vram_mb = await asyncio.to_thread(
            self._runner.transcribe, audio_f32, sample_rate
        )
        return Transcript(
            text=text.strip(),
            language=language,
            confidence=1.0 if text.strip() else 0.0,
        )
