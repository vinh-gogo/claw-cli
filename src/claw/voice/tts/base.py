from __future__ import annotations

import re
from typing import AsyncIterator, Protocol


def sanitize_text_for_speech(text: str) -> str:
    """Prepare text for TTS: remove markdown formatting, code blocks, URLs, and simplify file paths."""
    # 1. Remove markdown code blocks ```...```
    clean = re.sub(r"```[\s\S]*?```", "", text)
    # 2. Remove inline code `...`
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    # 3. Remove URLs
    clean = re.sub(r"https?://\S+", "", clean)
    # 4. Remove markdown headers, list markers, quotes, bold/italic symbols
    clean = re.sub(r"^[#*>\-\+\d\.]+\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"[*_~]", "", clean)
    # 5. Clean extra whitespace
    clean = " ".join(clean.split())
    return clean


class TTSProvider(Protocol):
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        ...

    async def synthesize(self, text: str) -> bytes:
        ...
