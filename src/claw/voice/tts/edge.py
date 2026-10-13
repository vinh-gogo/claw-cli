from __future__ import annotations

import logging
from typing import AsyncIterator

import edge_tts

from claw.config import TTSConfig
from claw.voice.tts.base import sanitize_text_for_speech

logger = logging.getLogger("claw.voice.tts.edge")


class EdgeTTSProvider:
    def __init__(self, cfg: TTSConfig) -> None:
        self.cfg = cfg
        self.voice = cfg.voice or "vi-VN-HoaiMyNeural"

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        cleaned_text = sanitize_text_for_speech(text)
        if not cleaned_text:
            return

        communicate = edge_tts.Communicate(cleaned_text, self.voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def synthesize(self, text: str) -> bytes:
        chunks: list[bytes] = []
        async for chunk in self.synthesize_stream(text):
            chunks.append(chunk)
        return b"".join(chunks)
