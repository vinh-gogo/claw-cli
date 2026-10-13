"""TTS providers."""

from claw.voice.tts.base import TTSProvider, sanitize_text_for_speech
from claw.voice.tts.edge import EdgeTTSProvider
from claw.voice.tts.system import SystemTTSProvider

__all__ = ["EdgeTTSProvider", "SystemTTSProvider", "TTSProvider", "sanitize_text_for_speech"]
