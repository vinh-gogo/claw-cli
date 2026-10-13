from __future__ import annotations

import io
import wave

import numpy as np
from openai import AsyncOpenAI

from claw.config import LLMConfig, STTConfig
from claw.voice.stt.base import Transcript


class OpenAICompatibleSTT:
    def __init__(self, llm_cfg: LLMConfig, stt_cfg: STTConfig) -> None:
        self.llm_cfg = llm_cfg
        self.stt_cfg = stt_cfg
        self.client = AsyncOpenAI(
            base_url=llm_cfg.base_url.rstrip("/"),
            api_key=llm_cfg.api_key or "not-needed",
            default_headers=llm_cfg.extra_headers,
        )

    async def transcribe(self, pcm: np.ndarray, sample_rate: int = 16000, language: str = "vi") -> Transcript:
        # Convert PCM to in-memory WAV file
        if pcm.dtype != np.int16:
            pcm_int16 = (pcm * 32767).astype(np.int16)
        else:
            pcm_int16 = pcm

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_int16.tobytes())

        wav_buffer.seek(0)
        wav_buffer.name = "audio.wav"

        try:
            resp = await self.client.audio.transcriptions.create(
                model=self.stt_cfg.model or "whisper-1",
                file=wav_buffer,
                language=language or self.stt_cfg.language,
                prompt=self.stt_cfg.initial_prompt,
            )
            return Transcript(text=resp.text.strip(), language=language, confidence=1.0)
        except Exception:
            return Transcript(text="", language=language, confidence=0.0)
