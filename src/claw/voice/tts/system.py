from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from typing import AsyncIterator

from claw.voice.tts.base import sanitize_text_for_speech

logger = logging.getLogger("claw.voice.tts.system")


class SystemTTSProvider:
    """Fallback text-to-speech using native operating system synthesizers."""

    def __init__(self) -> None:
        pass

    async def speak_text(self, text: str) -> None:
        clean = sanitize_text_for_speech(text)
        if not clean:
            return

        def _speak_sync() -> None:
            if sys.platform == "win32":
                # PowerShell SAPI
                escaped = clean.replace("'", "''").replace('"', '""')
                cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"
                subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, check=False)
            elif sys.platform == "darwin":
                subprocess.run(["say", clean], capture_output=True, check=False)
            else:
                subprocess.run(["espeak-ng", clean], capture_output=True, check=False)

        await asyncio.to_thread(_speak_sync)

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        await self.speak_text(text)
        if False:
            yield b""

    async def synthesize(self, text: str) -> bytes:
        await self.speak_text(text)
        return b""
